"""Wallet analysis toolkit for trader and review workflows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from redis import Redis

from core.camel_tools.async_wrapper import CAMEL_TOOLS_AVAILABLE, create_function_tool
from core.settings.config import settings
from core.logging import log


class WalletAnalysisToolkit:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self.redis = redis_client or self._init_redis()

    @staticmethod
    def _init_redis() -> Redis | None:
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
            log.warning(f"WalletAnalysisToolkit Redis unavailable: {exc}")
            return None

    def _require_redis(self) -> Redis:
        if not self.redis:
            raise RuntimeError("Redis not available")
        return self.redis

    def get_wallet_state(self, wallet_address: str = "") -> dict[str, Any]:
        redis_client = self._require_redis()
        positions_raw = redis_client.hgetall("watchlist:positions")
        prices = redis_client.hgetall("watchlist:prices")
        trade_history = redis_client.lrange("dex:trade_history", 0, 199)

        open_positions = []
        unrealized_pnl = 0.0
        for raw in positions_raw.values():
            try:
                pos = json.loads(raw)
            except Exception:
                continue
            if wallet_address and str(pos.get("wallet_address", "")).lower() != wallet_address.lower():
                continue
            if pos.get("status") != "open":
                continue
            symbol = str(pos.get("token_symbol", "")).upper()
            current = float(prices.get(symbol, pos.get("entry_price", 0) or 0))
            entry = float(pos.get("entry_price", 0) or 0)
            quantity = float(pos.get("quantity", 0) or 0)
            pnl = (current - entry) * quantity
            unrealized_pnl += pnl
            open_positions.append({**pos, "current_price": current, "unrealized_pnl": pnl})

        return {
            "success": True,
            "wallet_address": wallet_address or "all",
            "open_positions": open_positions,
            "open_position_count": len(open_positions),
            "unrealized_pnl": unrealized_pnl,
            "recent_trade_count": len(trade_history),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_global_wallet_state(self, wallet_address: str = "") -> dict[str, Any]:
        """Return global ROI and per-token investment allocation for open positions."""
        state = self.get_wallet_state(wallet_address=wallet_address)
        if not state.get("success"):
            return state

        open_positions = state.get("open_positions", [])
        per_token: dict[str, dict[str, float]] = {}
        total_invested = 0.0
        total_current_value = 0.0

        for pos in open_positions:
            symbol = str(pos.get("token_symbol", "")).upper()
            quantity = float(pos.get("quantity", 0) or 0)
            entry_price = float(pos.get("entry_price", 0) or 0)
            current_price = float(pos.get("current_price", entry_price) or entry_price)

            invested = quantity * entry_price
            current_value = quantity * current_price
            total_invested += invested
            total_current_value += current_value

            token_bucket = per_token.setdefault(
                symbol,
                {
                    "invested": 0.0,
                    "current_value": 0.0,
                    "pnl": 0.0,
                    "roi": 0.0,
                },
            )
            token_bucket["invested"] += invested
            token_bucket["current_value"] += current_value

        for token_data in per_token.values():
            token_data["pnl"] = token_data["current_value"] - token_data["invested"]
            if token_data["invested"] > 0:
                token_data["roi"] = token_data["pnl"] / token_data["invested"]

        global_pnl = total_current_value - total_invested
        global_roi = (global_pnl / total_invested) if total_invested > 0 else 0.0

        return {
            "success": True,
            "wallet_address": wallet_address or "all",
            "global_invested": total_invested,
            "global_current_value": total_current_value,
            "global_pnl": global_pnl,
            "global_roi": global_roi,
            "per_token_investment": per_token,
            "open_position_count": state.get("open_position_count", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_wallet_feedback(self, wallet_address: str = "") -> dict[str, Any]:
        state = self.get_wallet_state(wallet_address=wallet_address)
        if not state.get("success"):
            return state

        open_position_count = int(state.get("open_position_count", 0))
        unrealized_pnl = float(state.get("unrealized_pnl", 0.0))

        feedback = []
        if open_position_count == 0:
            feedback.append("No open positions. Consider scanning for fresh opportunities.")
        elif open_position_count > 12:
            feedback.append("High position count detected. Consider reducing exposure concentration.")

        if unrealized_pnl < 0:
            feedback.append("Wallet unrealized PnL is negative. Tighten stop-loss thresholds.")
        elif unrealized_pnl > 0:
            feedback.append("Wallet unrealized PnL is positive. Consider trailing take-profit strategy.")

        return {
            "success": True,
            "wallet_address": wallet_address or "all",
            "feedback": feedback,
            "state": state,
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

    def get_tools(self) -> list[Any]:
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL function tools not installed")

        return [
            create_function_tool(
                self.get_wallet_state,
                explicit_schema=self._schema(
                    "get_wallet_state",
                    "Analyze current wallet state, open positions, and unrealized PnL.",
                    {"wallet_address": {"type": "string"}},
                    [],
                ),
            ),
            create_function_tool(
                self.get_wallet_feedback,
                explicit_schema=self._schema(
                    "get_wallet_feedback",
                    "Return actionable feedback for wallet risk and position health.",
                    {"wallet_address": {"type": "string"}},
                    [],
                ),
            ),
            create_function_tool(
                self.get_global_wallet_state,
                explicit_schema=self._schema(
                    "get_global_wallet_state",
                    "Return global ROI and per-token investment distribution for open positions.",
                    {"wallet_address": {"type": "string"}},
                    [],
                ),
            ),
        ]
