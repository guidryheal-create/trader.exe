"""Auto-enhancement toolkit for iterative trading process improvements."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from redis import Redis

from core.camel_tools.async_wrapper import CAMEL_TOOLS_AVAILABLE, create_function_tool
from core.settings.config import settings
from core.logging import log


class AutoEnhancementToolkit:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self.redis = redis_client or self._init_redis()
        self.feedback_key = "dex:auto_enhancement:feedback"

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
            log.warning(f"AutoEnhancementToolkit Redis unavailable: {exc}")
            return None

    def _require_redis(self) -> Redis:
        if not self.redis:
            raise RuntimeError("Redis not available")
        return self.redis

    def generate_feedback(self) -> dict[str, Any]:
        redis_client = self._require_redis()
        trade_history = redis_client.lrange("dex:trade_history", 0, 300)
        positions = redis_client.hgetall("watchlist:positions")

        total_trades = len(trade_history)
        closed_positions = 0
        losing_closed = 0
        for raw in positions.values():
            try:
                p = json.loads(raw)
            except Exception:
                continue
            if p.get("status") != "closed":
                continue
            closed_positions += 1
            pnl = float(p.get("realized_pnl", 0) or 0)
            if pnl < 0:
                losing_closed += 1

        improvements: list[str] = []
        if total_trades < 5:
            improvements.append("Increase sample size before tuning strategy aggressively.")
        if closed_positions > 0 and losing_closed / max(closed_positions, 1) > 0.5:
            improvements.append("Loss ratio is high: reduce position size and tighten stop-loss.")
        if not improvements:
            improvements.append("Performance stable: keep current strategy and monitor drift.")

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_trades": total_trades,
            "closed_positions": closed_positions,
            "losing_closed": losing_closed,
            "improvements": improvements,
        }
        redis_client.set(self.feedback_key, json.dumps(payload))
        return {"success": True, "feedback": payload}

    def get_latest_feedback(self) -> dict[str, Any]:
        redis_client = self._require_redis()
        raw = redis_client.get(self.feedback_key)
        if not raw:
            return {"success": True, "feedback": None}
        try:
            return {"success": True, "feedback": json.loads(raw)}
        except Exception:
            return {"success": False, "error": "invalid feedback payload"}

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
                self.generate_feedback,
                explicit_schema=self._schema(
                    "generate_trader_feedback",
                    "Analyze wallet/trade history and generate process improvements.",
                    {},
                    [],
                ),
            ),
            create_function_tool(
                self.get_latest_feedback,
                explicit_schema=self._schema(
                    "get_latest_trader_feedback",
                    "Get latest auto-enhancement feedback for next trader cycle.",
                    {},
                    [],
                ),
            ),
        ]
