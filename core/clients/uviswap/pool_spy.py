"""Pool discovery and inspection helpers for Uniswap pools."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import httpx
from web3 import Web3

from core.clients.uviswap.models import PoolModel, PoolSelectionModel
from core.logging import log


V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {"inputs": [], "name": "liquidity", "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token1", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "fee", "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "tickSpacing", "outputs": [{"internalType": "int24", "name": "", "type": "int24"}], "stateMutability": "view", "type": "function"},
]


class PoolSpy:
    """Read-only pool inspection + discovery utility."""

    def __init__(
        self,
        w3: Web3,
        pool_manager_address: str | None = None,
        subgraph_url: str | None = None,
        redis_client: Any | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.w3 = w3
        self.pool_manager_address = (
            Web3.to_checksum_address(pool_manager_address)
            if pool_manager_address
            else None
        )
        self.subgraph_url = subgraph_url
        self.redis_client = redis_client
        self.timeout_seconds = timeout_seconds
        self._pool_index: dict[str, list[PoolSelectionModel]] = {}
        self._redis_pair_prefix = "uviswap:pools:pair:"
        self._redis_symbol_prefix = "uviswap:pools:symbol:"

    def inspect_v3_pool(self, pool_address: str) -> dict[str, Any]:
        pool = self.w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=V3_POOL_ABI)
        slot0 = pool.functions.slot0().call()
        liquidity = int(pool.functions.liquidity().call())
        token0 = str(pool.functions.token0().call())
        token1 = str(pool.functions.token1().call())
        fee = int(pool.functions.fee().call())
        tick_spacing = int(pool.functions.tickSpacing().call())

        return {
            "pool": str(pool.address),
            "token0": token0,
            "token1": token1,
            "fee": fee,
            "tick_spacing": tick_spacing,
            "sqrt_price_x96": int(slot0[0]),
            "tick": int(slot0[1]),
            "liquidity": liquidity,
        }

    def inspect_with_fallback(self, pool_address: str) -> dict[str, Any]:
        try:
            return self.inspect_v3_pool(pool_address)
        except Exception as exc:
            log.warning(f"PoolSpy failed to inspect pool {pool_address}: {exc}")
            return {
                "pool": pool_address,
                "error": str(exc),
            }

    def fetch_pools(self, symbols: list[str], limit: int = 100) -> list[PoolModel]:
        if not self.subgraph_url:
            log.warning("PoolSpy subgraph_url not configured; returning empty pool list")
            return []

        normalized_symbols = [s.upper() for s in symbols if s]
        if not normalized_symbols:
            return []

        graphql_query = {
            "query": """
            query PoolsBySymbols($symbols: [String!], $first: Int!) {
              pools(
                first: $first,
                orderBy: totalValueLockedUSD,
                orderDirection: desc,
                where: {
                  and: [
                    { token0_: { symbol_in: $symbols } },
                    { token1_: { symbol_in: $symbols } }
                  ]
                }
              ) {
                id
                createdAtTimestamp
                createdAtBlockNumber
                txCount
                volumeUSD
                totalValueLockedUSD
                token0 { id symbol }
                token1 { id symbol }
              }
            }
            """,
            "variables": {"symbols": normalized_symbols, "first": int(limit)},
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(self.subgraph_url, json=graphql_query)
                response.raise_for_status()
                payload = response.json()

            raw_pools = (payload.get("data") or {}).get("pools") or []
            pools = [PoolModel.model_validate(pool) for pool in raw_pools]
            return pools
        except Exception as exc:
            log.warning(f"PoolSpy fetch_pools failed: {exc}")
            return []

    @staticmethod
    def format_pool_report(pools: list[PoolModel]) -> str:
        output = ""
        for pool in pools:
            timestamp = datetime.fromtimestamp(int(pool.createdAtTimestamp)).strftime("%Y-%m-%d %H:%M:%S")
            volume_usd = float(pool.volumeUSD)
            tvl_usd = float(pool.totalValueLockedUSD)
            output += (
                f"Pool Address: {pool.id}\n"
                f"Tokens: {pool.token0.symbol}/{pool.token1.symbol}\n"
                f"Created At: {timestamp}\n"
                f"Block Number: {pool.createdAtBlockNumber}\n"
                f"Transaction Count: {pool.txCount}\n"
                f"Volume (USD): {volume_usd:.2f}\n"
                f"Total Value Locked (USD): {tvl_usd:.2f}\n\n"
            )
        return output

    def build_pool_index(self, pools: list[PoolModel]) -> dict[str, list[PoolSelectionModel]]:
        index: dict[str, list[PoolSelectionModel]] = {}

        for pool in pools:
            selection = PoolSelectionModel(
                pair=pool.pair_symbol,
                pool_address=pool.id,
                token0_symbol=pool.token0.symbol.upper(),
                token0_address=pool.token0.id,
                token1_symbol=pool.token1.symbol.upper(),
                token1_address=pool.token1.id,
                tvl_usd=float(pool.totalValueLockedUSD),
                volume_usd=float(pool.volumeUSD),
                tx_count=int(pool.txCount),
                created_at=pool.created_at_iso,
            )

            keys = {
                pool.pair_symbol,
                f"{selection.token1_symbol}/{selection.token0_symbol}",
                selection.token0_symbol,
                selection.token1_symbol,
            }
            for key in keys:
                index.setdefault(key, []).append(selection)

        for key in index:
            index[key].sort(key=lambda x: (x.tvl_usd, x.volume_usd, x.tx_count), reverse=True)

        self._pool_index = index
        self._persist_pool_index(index)
        return index

    def _persist_pool_index(self, index: dict[str, list[PoolSelectionModel]]) -> None:
        if not self.redis_client:
            return
        try:
            for key, selections in index.items():
                payload = json.dumps([item.model_dump() for item in selections])
                redis_key = (
                    f"{self._redis_pair_prefix}{key}"
                    if "/" in key
                    else f"{self._redis_symbol_prefix}{key}"
                )
                self.redis_client.set(redis_key, payload)
        except Exception as exc:
            log.warning(f"Failed to persist pool index to Redis: {exc}")

    def _load_index_candidates_from_redis(self, key: str) -> list[PoolSelectionModel]:
        if not self.redis_client:
            return []
        redis_key = (
            f"{self._redis_pair_prefix}{key}"
            if "/" in key
            else f"{self._redis_symbol_prefix}{key}"
        )
        try:
            raw = self.redis_client.get(redis_key)
            if not raw:
                return []
            data = json.loads(raw)
            return [PoolSelectionModel.model_validate(item) for item in data]
        except Exception as exc:
            log.debug(f"Failed loading pool candidates from Redis for key={key}: {exc}")
            return []

    def discover_and_index_pools(self, symbols: list[str], limit: int = 100) -> dict[str, Any]:
        pools = self.fetch_pools(symbols=symbols, limit=limit)
        index = self.build_pool_index(pools)
        return {
            "pools": [pool.model_dump() for pool in pools],
            "pool_count": len(pools),
            "index_keys": sorted(index.keys()),
            "formatted": self.format_pool_report(pools),
        }

    def resolve_best_pool(self, token_in_symbol: str, token_out_symbol: str) -> PoolSelectionModel | None:
        pair = f"{token_in_symbol.upper()}/{token_out_symbol.upper()}"
        candidates = self._pool_index.get(pair)
        if not candidates:
            candidates = self._load_index_candidates_from_redis(pair)
        if candidates:
            return candidates[0]

        reverse_pair = f"{token_out_symbol.upper()}/{token_in_symbol.upper()}"
        candidates = self._pool_index.get(reverse_pair)
        if not candidates:
            candidates = self._load_index_candidates_from_redis(reverse_pair)
        if candidates:
            return candidates[0]

        return None
