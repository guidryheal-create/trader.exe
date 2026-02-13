"""UviSwap client for Uniswap Universal Router workflows.

This module replaces prototype-style code with structured runtime logic,
project-standard logging, typed validation, and tool-ready integrations.
"""

from __future__ import annotations

from typing import Any

import httpx
from eth_account import Account
from redis import Redis
from web3 import Web3

from core.clients.uviswap.gas import GasManager
from core.models.uviswap import MarketContextModel
from core.clients.uviswap.permit2 import Permit2Client
from core.clients.uviswap.pool_spy import PoolSpy
from core.clients.uviswap.quote import Quoter
from core.clients.uviswap.routeur import Router
from core.clients.uviswap.rpc import RPC
from core.clients.uviswap.simulation import simulate_transaction
from core.clients.uviswap.swap import SwapPlan, SwapRequest, compute_min_out
from core.settings.config import (
    CHAIN_BY_ID,
    DEFAULT_PERMIT2,
    ROUTER_ADDRESSES,
    UNIVERSAL_ROUTER_EXECUTE_ABI,
    V3_QUOTER_ABI,
    get_chain_config,
    settings,
)
from core.logging import log

DEFAULT_POLYWHALER_URL = "https://www.polywhaler.com/api/market-data"


class UviSwapClientError(Exception):
    """Raised for UviSwap client failures."""


class UviSwapClient:
    """Production-safe Uniswap universal-router client."""

    def __init__(
        self,
        private_key: str | None = None,
        rpc_url: str | None = None,
        chain: str | None = None,
        router_address: str | None = None,
        quoter_address: str | None = None,
        pool_manager_address: str | None = None,
        permit2_address: str | None = None,
        uniswap_subgraph_url: str | None = None,
        polywhaler_url: str | None = None,
    ) -> None:
        resolved_private_key = private_key or settings.private_key
        if not resolved_private_key:
            raise UviSwapClientError("Missing private key: provide private_key or set PRIVATE_KEY in .env")

        resolved_rpc = rpc_url or settings.eth_rpc_url
        if not resolved_rpc:
            raise UviSwapClientError("Missing RPC URL: provide rpc_url or set ETH_RPC_URL in .env")

        self.account = Account.from_key(resolved_private_key)
        self.address = Web3.to_checksum_address(self.account.address)

        self.rpc = RPC(resolved_rpc)
        self.w3 = self.rpc.w3

        self.chain = self._resolve_chain(chain)
        self.chain_config = get_chain_config(self.chain)
        log.info(f"Resolved chain name chain={self.chain} chain_id={self.rpc.chain_id}")
        resolved_router = router_address or (
            self.chain_config.universal_router if self.chain_config else ROUTER_ADDRESSES.get(self.chain)
        )
        if not resolved_router:
            raise UviSwapClientError(f"Unsupported chain '{self.chain}' and no router provided")
        log.info(f"Using router address chain={self.chain} router={resolved_router}")

        self.router_address = Web3.to_checksum_address(resolved_router)
        self.router = Router(
            self.w3.eth.contract(address=self.router_address, abi=UNIVERSAL_ROUTER_EXECUTE_ABI)
        )

        self.quoter = None
        resolved_quoter = quoter_address or (self.chain_config.quoter if self.chain_config else None)
        if resolved_quoter:
            q_addr = Web3.to_checksum_address(resolved_quoter)
            q_contract = self.w3.eth.contract(address=q_addr, abi=V3_QUOTER_ABI)
            self.quoter = Quoter(self.w3, q_contract)

        resolved_permit2 = permit2_address or (
            self.chain_config.permit2 if self.chain_config else DEFAULT_PERMIT2
        )
        self.permit2 = Permit2Client(self.w3, resolved_permit2)
        self.gas = GasManager(self.w3)
        self._redis = self._init_redis()
        resolved_pool_manager = pool_manager_address or (self.chain_config.pool_manager if self.chain_config else None)
        self.pool_spy = PoolSpy(
            self.w3,
            resolved_pool_manager,
            subgraph_url=uniswap_subgraph_url or settings.uniswap_subgraph_url,
            redis_client=self._redis,
        )
        self.polywhaler_url = polywhaler_url or settings.polywhaler_market_data_url or DEFAULT_POLYWHALER_URL

        log.info(
            f"UviSwapClient initialized chain={self.chain} chain_id={self.rpc.chain_id} "
            f"wallet={self.address} router={self.router_address}"
        )
        self._validate_operation_support()

    def _resolve_chain(self, chain: str | None) -> str:
        if chain:
            return chain.strip().lower()
        inferred = CHAIN_BY_ID.get(self.rpc.chain_id)
        if inferred:
            log.info(f"Inferred chain from chain_id chain_id={self.rpc.chain_id} chain={inferred}")
            return inferred
        log.warning(f"Unsupported chain_id={self.rpc.chain_id}; defaulting chain=ethereum")
        return "ethereum"

    def _init_redis(self):
        try:
            client = Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
            )
            client.ping()
            return client
        except Exception as exc:
            log.warning(f"UviSwapClient Redis unavailable: {exc}")
            return None

    def _validate_operation_support(self) -> None:
        if not self.chain_config:
            log.warning(f"No chain config registered for chain={self.chain}; feature validation is limited")
            return
        if not self.chain_config.pool_manager:
            log.warning(f"No pool_manager configured for chain={self.chain}; pool discovery may be limited")
        if not self.chain_config.quoter and not self.quoter:
            log.warning(f"No quoter configured for chain={self.chain}; quoting APIs will be disabled")
        if not self.chain_config.explorer_base_url:
            log.warning(f"No explorer configured for chain={self.chain}; explorer URLs will be unavailable")

    def get_explorer_tx_url(self, tx_hash: str) -> str | None:
        if not self.chain_config:
            return None
        return self.chain_config.explorer_tx_url(tx_hash)

    def get_explorer_address_url(self, address: str | None = None) -> str | None:
        if not self.chain_config:
            return None
        target_address = address or self.address
        return self.chain_config.explorer_address_url(target_address)

    def quote_exact_in(self, token_in: str, token_out: str, amount_in: int, fee: int = 3_000) -> int:
        if not self.quoter:
            raise UviSwapClientError(
                f"Quoter not configured for chain={self.chain}. "
                "Pass quoter_address to client or register chain quoter in core/models/chain.py."
            )
        amount_out = self.quoter.quote_exact_in(token_in, token_out, amount_in, fee=fee)
        log.debug(
            f"Quote token_in={token_in} token_out={token_out} "
            f"amount_in={amount_in} amount_out={amount_out}"
        )
        return amount_out

    def discover_trade_pools(self, symbols: list[str], limit: int = 100) -> dict[str, Any]:
        if not self.chain_config or not self.chain_config.pool_manager:
            log.warning(
                f"Pool discovery running without configured pool_manager chain={self.chain}; "
                "results may depend entirely on subgraph fallback."
            )
        data = self.pool_spy.discover_and_index_pools(symbols=symbols, limit=limit)
        log.info(f"Discovered {data.get('pool_count', 0)} pools for symbols={symbols}")
        return data

    def resolve_trade_pool(self, token_in_symbol: str, token_out_symbol: str) -> dict[str, Any]:
        pool = self.pool_spy.resolve_best_pool(token_in_symbol=token_in_symbol, token_out_symbol=token_out_symbol)
        if not pool:
            self.discover_trade_pools(symbols=[token_in_symbol, token_out_symbol], limit=100)
            pool = self.pool_spy.resolve_best_pool(token_in_symbol=token_in_symbol, token_out_symbol=token_out_symbol)
        if not pool:
            return {
                "success": False,
                "error": f"No pool found for {token_in_symbol}/{token_out_symbol}",
            }
        return {
            "success": True,
            "pool": pool.model_dump(),
        }

    def get_trade_pool_context(self, token_in_symbol: str, token_out_symbol: str) -> dict[str, Any]:
        pool_result = self.resolve_trade_pool(token_in_symbol=token_in_symbol, token_out_symbol=token_out_symbol)
        in_context = self.get_market_context(token_symbol=token_in_symbol)
        out_context = self.get_market_context(token_symbol=token_out_symbol)
        return {
            "success": bool(pool_result.get("success")),
            "pool": pool_result.get("pool"),
            "pool_error": pool_result.get("error"),
            "token_in_context": in_context,
            "token_out_context": out_context,
        }

    def _get_last_polymarket_bet(self, token_symbol: str) -> dict[str, Any] | None:
        try:
            from api.services.polymarket.decision_service import decision_service

            symbol = token_symbol.upper()
            for decision in decision_service.list_decisions(limit=500):
                market_name = str(decision.get("market_name", "")).upper()
                asset = str(decision.get("asset", "")).upper()
                if symbol == asset or symbol in market_name:
                    return decision
        except Exception as exc:
            log.debug(f"Polymarket decision lookup unavailable: {exc}")
        return None

    def _get_polywhaler_snapshot(self, token_symbol: str) -> dict[str, Any]:
        key = token_symbol.strip().lower()
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.get(self.polywhaler_url)
                response.raise_for_status()
                payload = response.json()

            asset_data = payload.get(key) or {}
            timestamp = payload.get("timestamp")
            return {
                "token": key,
                "price": asset_data.get("price"),
                "change24h": asset_data.get("change24h"),
                "trend": asset_data.get("trend"),
                "timestamp": timestamp,
            }
        except Exception as exc:
            log.warning(f"Polywhaler snapshot fetch failed for symbol={token_symbol}: {exc}")
            return {}

    def get_market_context(self, token_symbol: str) -> dict[str, Any]:
        context = MarketContextModel(
            symbol=token_symbol.upper(),
            polywhaler=self._get_polywhaler_snapshot(token_symbol),
            last_polymarket_bet=self._get_last_polymarket_bet(token_symbol),
        )
        return context.model_dump()

    def build_swap_plan(
        self,
        request: SwapRequest,
        commands: bytes,
        inputs: list[bytes],
        deadline_seconds: int = 300,
        simulate: bool = True,
    ) -> SwapPlan:
        expected_out = 0
        if self.quoter:
            expected_out = self.quote_exact_in(
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=request.amount_in,
                fee=request.fee,
            )

        min_out = compute_min_out(expected_out=expected_out, slippage_bps=request.slippage_bps)

        deadline = int(self.w3.eth.get_block("latest")["timestamp"]) + int(deadline_seconds)
        calldata = self.router.encode_execute(commands=commands, inputs=inputs, deadline=deadline)

        nonce = self.rpc.nonce(self.address)
        gas_quote = self.gas.aggressive_fast(request.estimated_gas_limit)
        if not self.gas.has_balance_for_gas(self.address, gas_quote):
            raise UviSwapClientError("Insufficient native token balance for gas")

        tx = self.router.build_swap_tx(
            sender=self.address,
            calldata=calldata,
            nonce=nonce,
            gas_params=gas_quote.to_tx_params(),
            value=request.value,
            chain_id=self.rpc.chain_id,
        )

        sim_ok = True
        sim_result: Any = None
        if simulate:
            sim = simulate_transaction(self.rpc, tx)
            sim_ok = bool(sim.ok)
            sim_result = sim.result

        plan = SwapPlan(
            request=request,
            expected_out=expected_out,
            min_out=min_out,
            nonce=nonce,
            calldata=calldata,
            tx=tx,
            simulation_ok=sim_ok,
            simulation_result=sim_result,
        )

        log.info(
            f"Built swap plan token_in={request.token_in} token_out={request.token_out} "
            f"amount_in={request.amount_in} min_out={min_out} sim_ok={sim_ok}"
        )
        return plan

    def execute_plan(self, plan: SwapPlan, require_simulation_success: bool = True) -> str:
        if require_simulation_success and not plan.simulation_ok:
            raise UviSwapClientError(f"Simulation failed: {plan.simulation_result}")

        signed = self.w3.eth.account.sign_transaction(plan.tx, private_key=self.account.key)
        raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction", None)
        if raw_tx is None:
            raise UviSwapClientError("Signed transaction has no raw payload")
        tx_hash = self.rpc.send_raw(raw_tx)
        tx_hex = tx_hash.hex()

        log.info(f"Broadcasted swap tx hash={tx_hex} nonce={plan.nonce}")
        explorer_url = self.get_explorer_tx_url(tx_hex)
        if explorer_url:
            log.info(f"Swap tx explorer url={explorer_url}")
        return tx_hex

    def approve_permit2_if_needed(self, token: str, min_allowance: int | None = None) -> str | None:
        needs_approval = self.permit2.needs_erc20_approval(
            owner=self.address,
            token=token,
            min_allowance=min_allowance,
        )
        if not needs_approval:
            return None

        nonce = self.rpc.nonce(self.address)
        gas_quote = self.gas.aggressive_fast(80_000)
        tx = self.permit2.build_erc20_approve_tx(
            token=token,
            owner=self.address,
            nonce=nonce,
            gas_params=gas_quote.to_tx_params(),
            chain_id=self.rpc.chain_id,
        )

        signed = self.w3.eth.account.sign_transaction(tx, private_key=self.account.key)
        raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction", None)
        if raw_tx is None:
            raise UviSwapClientError("Signed approval transaction has no raw payload")
        tx_hash = self.rpc.send_raw(raw_tx)
        tx_hex = tx_hash.hex()
        log.info(f"Broadcasted Permit2 ERC20 approval tx hash={tx_hex} token={token}")
        return tx_hex

    def inspect_pool(self, pool_address: str) -> dict[str, Any]:
        return self.pool_spy.inspect_with_fallback(pool_address)


UniswapV4Client = UviSwapClient
