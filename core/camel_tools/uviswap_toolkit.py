"""UviSwap Toolkit for CAMEL agents.

This toolkit intentionally uses explicit OpenAI tool schemas to avoid CAMEL
schema-generation edge cases and keep behavior stable.
"""

from __future__ import annotations

from typing import Any

from core.camel_tools.async_wrapper import CAMEL_TOOLS_AVAILABLE, create_function_tool
from core.camel_tools.watchlist_toolkit import WatchlistToolkit
from core.clients.uviswap import SwapPlan, SwapRequest, UviSwapClient
from core.config import settings
from core.logging import log


class UviSwapToolkit:
    """Toolkit facade around :class:`UviSwapClient`."""

    def __init__(
        self,
        client: UviSwapClient | None = None,
        watchlist_toolkit: WatchlistToolkit | None = None,
    ) -> None:
        self.client = client or UviSwapClient()
        self.watchlist_toolkit = watchlist_toolkit or WatchlistToolkit()

    @staticmethod
    def _decode_router_payload(commands_hex: str, inputs_hex: list[str]) -> tuple[bytes, list[bytes]]:
        commands = bytes.fromhex(commands_hex.removeprefix("0x"))
        inputs = [bytes.fromhex(item.removeprefix("0x")) for item in inputs_hex]
        return commands, inputs

    def _build_plan(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        commands_hex: str,
        inputs_hex: list[str],
        slippage_bps: int,
        fee: int,
        gas_limit: int,
        value: int,
        deadline_seconds: int,
        simulate: bool,
    ) -> SwapPlan:
        request = SwapRequest(
            token_in=token_in,
            token_out=token_out,
            amount_in=int(amount_in),
            slippage_bps=int(slippage_bps),
            fee=int(fee),
            estimated_gas_limit=int(gas_limit),
            value=int(value),
        )
        commands, inputs = self._decode_router_payload(commands_hex, inputs_hex)
        return self.client.build_swap_plan(
            request=request,
            commands=commands,
            inputs=inputs,
            deadline_seconds=int(deadline_seconds),
            simulate=bool(simulate),
        )

    def quote_exact_in(self, token_in: str, token_out: str, amount_in: int, fee: int = 3_000) -> dict[str, Any]:
        amount_out = self.client.quote_exact_in(
            token_in=token_in,
            token_out=token_out,
            amount_in=int(amount_in),
            fee=int(fee),
        )
        return {
            "success": True,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": int(amount_in),
            "amount_out": int(amount_out),
            "fee": int(fee),
        }

    def inspect_pool(self, pool_address: str) -> dict[str, Any]:
        data = self.client.inspect_pool(pool_address)
        return {"success": "error" not in data, "pool": data}

    def discover_trade_pools(self, symbols: list[str], limit: int = 100) -> dict[str, Any]:
        return self.client.discover_trade_pools(symbols=symbols, limit=int(limit))

    def resolve_trade_pool(self, token_in_symbol: str, token_out_symbol: str) -> dict[str, Any]:
        return self.client.resolve_trade_pool(token_in_symbol=token_in_symbol, token_out_symbol=token_out_symbol)

    def get_market_context(self, token_symbol: str) -> dict[str, Any]:
        return self.client.get_market_context(token_symbol=token_symbol)

    def get_trade_pool_context(self, token_in_symbol: str, token_out_symbol: str) -> dict[str, Any]:
        return self.client.get_trade_pool_context(
            token_in_symbol=token_in_symbol,
            token_out_symbol=token_out_symbol,
        )

    def approve_permit2_if_needed(self, token: str, min_allowance: int | None = None) -> dict[str, Any]:
        tx_hash = self.client.approve_permit2_if_needed(token=token, min_allowance=min_allowance)
        return {
            "success": True,
            "token": token,
            "approval_sent": bool(tx_hash),
            "tx_hash": tx_hash,
        }

    def register_stop_loss_take_profit(
        self,
        token_symbol: str,
        token_address: str,
        quantity: float,
        entry_price: float,
        stop_loss_pct: float = -0.07,
        take_profit_pct: float = 0.12,
        exit_to_symbol: str = "USDC",
        exit_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        wallet_address = settings.wallet_address or self.client.address
        return self.watchlist_toolkit.add_position(
            token_symbol=token_symbol,
            token_address=token_address,
            quantity=quantity,
            entry_price=entry_price,
            wallet_address=wallet_address,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            mode="fast_decision",
            exit_to_symbol=exit_to_symbol,
            exit_plan=exit_plan,
        )

    def execute_watchlist_exit(self, position_id: str, trigger_type: str) -> dict[str, Any]:
        fetched = self.watchlist_toolkit.get_position(position_id)
        if not fetched.get("success"):
            return {"success": False, "error": fetched.get("error", "position not found")}

        position = fetched["position"]
        exit_plan = position.get("exit_plan") or {}
        if not exit_plan:
            return {"success": False, "error": "missing_exit_plan"}

        try:
            result = self.execute_swap(
                token_in=str(exit_plan["token_in"]),
                token_out=str(exit_plan.get("token_out", "")),
                amount_in=int(exit_plan["amount_in"]),
                commands_hex=str(exit_plan["commands_hex"]),
                inputs_hex=list(exit_plan["inputs_hex"]),
                slippage_bps=int(exit_plan.get("slippage_bps", 35)),
                fee=int(exit_plan.get("fee", 3_000)),
                gas_limit=int(exit_plan.get("gas_limit", 300_000)),
                value=int(exit_plan.get("value", 0)),
                deadline_seconds=int(exit_plan.get("deadline_seconds", 300)),
                require_simulation_success=True,
            )
        except KeyError as exc:
            return {"success": False, "error": f"exit_plan missing field: {exc}"}

        if not result.get("success"):
            return result

        close = self.watchlist_toolkit.close_position(position_id=position_id, close_reason=trigger_type)
        return {
            "success": True,
            "trigger_type": trigger_type,
            "tx_hash": result.get("tx_hash"),
            "position": close.get("position"),
        }

    def build_swap_plan(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        commands_hex: str,
        inputs_hex: list[str],
        slippage_bps: int = 25,
        fee: int = 3_000,
        gas_limit: int = 300_000,
        value: int = 0,
        deadline_seconds: int = 300,
        simulate: bool = True,
    ) -> dict[str, Any]:
        plan = self._build_plan(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            commands_hex=commands_hex,
            inputs_hex=inputs_hex,
            slippage_bps=slippage_bps,
            fee=fee,
            gas_limit=gas_limit,
            value=value,
            deadline_seconds=deadline_seconds,
            simulate=simulate,
        )

        return {
            "success": True,
            "simulation_ok": bool(plan.simulation_ok),
            "simulation_result": plan.simulation_result,
            "expected_out": int(plan.expected_out),
            "min_out": int(plan.min_out),
            "nonce": int(plan.nonce),
            "tx": plan.tx,
            "calldata": plan.calldata,
        }

    def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        commands_hex: str,
        inputs_hex: list[str],
        slippage_bps: int = 25,
        fee: int = 3_000,
        gas_limit: int = 300_000,
        value: int = 0,
        deadline_seconds: int = 300,
        require_simulation_success: bool = True,
    ) -> dict[str, Any]:
        plan = self._build_plan(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            commands_hex=commands_hex,
            inputs_hex=inputs_hex,
            slippage_bps=slippage_bps,
            fee=fee,
            gas_limit=gas_limit,
            value=value,
            deadline_seconds=deadline_seconds,
            simulate=True,
        )

        if require_simulation_success and not plan.simulation_ok:
            return {
                "success": False,
                "error": f"Simulation failed: {plan.simulation_result}",
            }

        tx_hash = self.client.execute_plan(
            plan=plan,
            require_simulation_success=require_simulation_success,
        )
        log.info(f"UviSwapToolkit executed swap tx={tx_hash}")

        return {
            "success": True,
            "tx_hash": tx_hash,
        }

    @staticmethod
    def _schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def get_all_tools(self) -> list[Any]:
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL function tools not installed")

        tools: list[Any] = []
        tools.append(
            create_function_tool(
                self.quote_exact_in,
                explicit_schema=self._schema(
                    "quote_exact_in",
                    "Get exact-input quote for a token pair.",
                    {
                        "token_in": {"type": "string", "description": "Input token address."},
                        "token_out": {"type": "string", "description": "Output token address."},
                        "amount_in": {"type": "integer", "description": "Input amount in token smallest unit."},
                        "fee": {"type": "integer", "description": "Pool fee tier, e.g. 3000."},
                    },
                    ["token_in", "token_out", "amount_in"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.inspect_pool,
                explicit_schema=self._schema(
                    "inspect_pool",
                    "Inspect a specific pool address on-chain.",
                    {
                        "pool_address": {"type": "string", "description": "Pool contract address."},
                    },
                    ["pool_address"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.discover_trade_pools,
                explicit_schema=self._schema(
                    "discover_trade_pools",
                    "Discover and index pools by token symbols via subgraph data.",
                    {
                        "symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Token symbols to search (e.g., [\"ETH\", \"USDC\"]).",
                        },
                        "limit": {"type": "integer", "description": "Max pools to fetch."},
                    },
                    ["symbols"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.resolve_trade_pool,
                explicit_schema=self._schema(
                    "resolve_trade_pool",
                    "Resolve best pool for a token symbol pair from indexed pool data.",
                    {
                        "token_in_symbol": {"type": "string", "description": "Input token symbol."},
                        "token_out_symbol": {"type": "string", "description": "Output token symbol."},
                    },
                    ["token_in_symbol", "token_out_symbol"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.get_market_context,
                explicit_schema=self._schema(
                    "get_market_context",
                    "Get market context from Polywhaler and latest Polymarket decision for a symbol.",
                    {
                        "token_symbol": {"type": "string", "description": "Token symbol like BTC or ETH."},
                    },
                    ["token_symbol"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.get_trade_pool_context,
                explicit_schema=self._schema(
                    "get_trade_pool_context",
                    "Get best trade pool and combined token market context (Polymarket + Polywhaler).",
                    {
                        "token_in_symbol": {"type": "string", "description": "Input token symbol."},
                        "token_out_symbol": {"type": "string", "description": "Output token symbol."},
                    },
                    ["token_in_symbol", "token_out_symbol"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.approve_permit2_if_needed,
                explicit_schema=self._schema(
                    "approve_permit2_if_needed",
                    "Approve ERC20 token for Permit2 if allowance is insufficient.",
                    {
                        "token": {"type": "string", "description": "Token address."},
                        "min_allowance": {"type": "integer", "description": "Minimum desired allowance."},
                    },
                    ["token"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.register_stop_loss_take_profit,
                explicit_schema=self._schema(
                    "register_stop_loss_take_profit",
                    "Register stop-loss/take-profit watchlist controls for a token position.",
                    {
                        "token_symbol": {"type": "string"},
                        "token_address": {"type": "string"},
                        "quantity": {"type": "number"},
                        "entry_price": {"type": "number"},
                        "stop_loss_pct": {"type": "number"},
                        "take_profit_pct": {"type": "number"},
                        "exit_to_symbol": {"type": "string"},
                        "exit_plan": {"type": "object"},
                    },
                    ["token_symbol", "token_address", "quantity", "entry_price"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.execute_watchlist_exit,
                explicit_schema=self._schema(
                    "execute_watchlist_exit",
                    "Execute on-chain exit to USDC for a watchlist-triggered position.",
                    {
                        "position_id": {"type": "string"},
                        "trigger_type": {"type": "string"},
                    },
                    ["position_id", "trigger_type"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.build_swap_plan,
                explicit_schema=self._schema(
                    "build_swap_plan",
                    "Build and optionally simulate a swap plan.",
                    {
                        "token_in": {"type": "string"},
                        "token_out": {"type": "string"},
                        "amount_in": {"type": "integer"},
                        "commands_hex": {"type": "string"},
                        "inputs_hex": {"type": "array", "items": {"type": "string"}},
                        "slippage_bps": {"type": "integer"},
                        "fee": {"type": "integer"},
                        "gas_limit": {"type": "integer"},
                        "value": {"type": "integer"},
                        "deadline_seconds": {"type": "integer"},
                        "simulate": {"type": "boolean"},
                    },
                    ["token_in", "token_out", "amount_in", "commands_hex", "inputs_hex"],
                ),
            )
        )
        tools.append(
            create_function_tool(
                self.execute_swap,
                explicit_schema=self._schema(
                    "execute_swap",
                    "Execute a swap via universal router after simulation.",
                    {
                        "token_in": {"type": "string"},
                        "token_out": {"type": "string"},
                        "amount_in": {"type": "integer"},
                        "commands_hex": {"type": "string"},
                        "inputs_hex": {"type": "array", "items": {"type": "string"}},
                        "slippage_bps": {"type": "integer"},
                        "fee": {"type": "integer"},
                        "gas_limit": {"type": "integer"},
                        "value": {"type": "integer"},
                        "deadline_seconds": {"type": "integer"},
                        "require_simulation_success": {"type": "boolean"},
                    },
                    ["token_in", "token_out", "amount_in", "commands_hex", "inputs_hex"],
                ),
            )
        )

        return tools

    def get_tools(self) -> list[Any]:
        """Compatibility alias used by some CAMEL registries."""
        return self.get_all_tools()
