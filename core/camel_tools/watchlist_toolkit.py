"""Watchlist toolkit for tracking positions and trigger notifications."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from redis import Redis

from core.camel_tools.async_wrapper import CAMEL_TOOLS_AVAILABLE, create_function_tool
from core.config import settings
from core.logging import log


class WatchlistToolkit:
    """Track positions and emit notifications on percentage-change triggers."""

    def __init__(self, redis_client: Redis | None = None) -> None:
        self.redis = redis_client or self._init_redis()
        self.positions_key = "watchlist:positions"
        self.prices_key = "watchlist:prices"
        self.notifications_key = "watchlist:notifications"
        self.global_roi_key = "watchlist:global_roi:last"

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
            log.warning(f"WatchlistToolkit Redis unavailable: {exc}")
            return None

    def _require_redis(self) -> Redis:
        if not self.redis:
            raise RuntimeError("Redis not available")
        return self.redis

    def add_position(
        self,
        token_symbol: str,
        token_address: str,
        quantity: float,
        entry_price: float,
        wallet_address: str,
        stop_loss_pct: float = -0.07,
        take_profit_pct: float = 0.12,
        mode: str = "fast_decision",
        exit_to_symbol: str = "USDC",
        exit_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        redis_client = self._require_redis()
        position_id = str(uuid.uuid4())
        payload = {
            "position_id": position_id,
            "token_symbol": token_symbol.upper(),
            "token_address": token_address,
            "quantity": float(quantity),
            "entry_price": float(entry_price),
            "wallet_address": wallet_address,
            "stop_loss_pct": float(stop_loss_pct),
            "take_profit_pct": float(take_profit_pct),
            "mode": mode,
            "exit_to_symbol": exit_to_symbol.upper(),
            "exit_plan": exit_plan or {},
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        redis_client.hset(self.positions_key, position_id, json.dumps(payload))
        return {"success": True, "position": payload}

    def get_position(self, position_id: str) -> dict[str, Any]:
        redis_client = self._require_redis()
        raw = redis_client.hget(self.positions_key, position_id)
        if not raw:
            return {"success": False, "error": f"position not found: {position_id}"}
        try:
            position = json.loads(raw)
        except Exception:
            return {"success": False, "error": "invalid position payload"}
        return {"success": True, "position": position}

    def update_exit_plan(self, position_id: str, exit_plan: dict[str, Any], exit_to_symbol: str = "USDC") -> dict[str, Any]:
        fetched = self.get_position(position_id)
        if not fetched.get("success"):
            return fetched
        position = fetched["position"]
        position["exit_plan"] = exit_plan
        position["exit_to_symbol"] = exit_to_symbol.upper()
        position["updated_at"] = datetime.now(timezone.utc).isoformat()
        redis_client = self._require_redis()
        redis_client.hset(self.positions_key, position_id, json.dumps(position))
        return {"success": True, "position": position}

    def update_price(self, token_symbol: str, price: float) -> dict[str, Any]:
        redis_client = self._require_redis()
        redis_client.hset(self.prices_key, token_symbol.upper(), str(float(price)))
        return {"success": True, "token_symbol": token_symbol.upper(), "price": float(price)}

    def list_positions(self, status: str = "open") -> dict[str, Any]:
        redis_client = self._require_redis()
        values = redis_client.hgetall(self.positions_key)
        positions: list[dict[str, Any]] = []
        for raw in values.values():
            try:
                position = json.loads(raw)
            except Exception:
                continue
            if status and position.get("status") != status:
                continue
            positions.append(position)
        return {"success": True, "count": len(positions), "positions": positions}

    def close_position(self, position_id: str, close_reason: str) -> dict[str, Any]:
        redis_client = self._require_redis()
        raw = redis_client.hget(self.positions_key, position_id)
        if not raw:
            return {"success": False, "error": f"position not found: {position_id}"}

        position = json.loads(raw)
        position["status"] = "closed"
        position["close_reason"] = close_reason
        position["updated_at"] = datetime.now(timezone.utc).isoformat()
        redis_client.hset(self.positions_key, position_id, json.dumps(position))
        return {"success": True, "position": position}

    def evaluate_triggers(self) -> dict[str, Any]:
        redis_client = self._require_redis()
        price_map = redis_client.hgetall(self.prices_key)
        values = redis_client.hgetall(self.positions_key)

        notifications: list[dict[str, Any]] = []
        for position_id, raw in values.items():
            try:
                position = json.loads(raw)
            except Exception:
                continue

            if position.get("status") != "open":
                continue

            symbol = str(position.get("token_symbol", "")).upper()
            if symbol not in price_map:
                continue

            current_price = float(price_map[symbol])
            entry_price = float(position.get("entry_price", 0) or 0)
            if entry_price <= 0:
                continue

            pct_change = (current_price - entry_price) / entry_price
            stop_loss_pct = float(position.get("stop_loss_pct", -0.07))
            take_profit_pct = float(position.get("take_profit_pct", 0.12))

            trigger_type = None
            if pct_change <= stop_loss_pct:
                trigger_type = "stop_loss"
            elif pct_change >= take_profit_pct:
                trigger_type = "take_profit"

            if not trigger_type:
                continue

            notification = {
                "notification_id": str(uuid.uuid4()),
                "position_id": position_id,
                "token_symbol": symbol,
                "wallet_address": position.get("wallet_address"),
                "trigger_type": trigger_type,
                "pct_change": pct_change,
                "entry_price": entry_price,
                "current_price": current_price,
                "mode": position.get("mode", "fast_decision"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            redis_client.lpush(self.notifications_key, json.dumps(notification))
            notifications.append(notification)

        if notifications:
            redis_client.ltrim(self.notifications_key, 0, 500)

        return {"success": True, "count": len(notifications), "notifications": notifications}

    def evaluate_global_roi_trigger(
        self,
        threshold_pct: float | None = None,
        fast_threshold_pct: float | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        redis_client = self._require_redis()
        is_enabled = settings.watchlist_global_roi_trigger_enabled if enabled is None else bool(enabled)
        if not is_enabled:
            return {"success": True, "enabled": False, "triggered": False}

        threshold = (
            settings.watchlist_global_roi_trigger_pct
            if threshold_pct is None
            else float(threshold_pct)
        )
        fast_threshold = (
            settings.watchlist_global_roi_fast_trigger_pct
            if fast_threshold_pct is None
            else float(fast_threshold_pct)
        )

        values = redis_client.hgetall(self.positions_key)
        price_map = redis_client.hgetall(self.prices_key)

        total_invested = 0.0
        total_current_value = 0.0
        for raw in values.values():
            try:
                position = json.loads(raw)
            except Exception:
                continue
            if position.get("status") != "open":
                continue
            symbol = str(position.get("token_symbol", "")).upper()
            quantity = float(position.get("quantity", 0) or 0)
            entry_price = float(position.get("entry_price", 0) or 0)
            current_price = float(price_map.get(symbol, entry_price) or entry_price)

            total_invested += quantity * entry_price
            total_current_value += quantity * current_price

        global_roi = 0.0
        if total_invested > 0:
            global_roi = (total_current_value - total_invested) / total_invested

        previous_raw = redis_client.get(self.global_roi_key)
        previous_roi = float(previous_raw) if previous_raw is not None else global_roi
        delta = global_roi - previous_roi
        redis_client.set(self.global_roi_key, str(global_roi))

        triggered = abs(delta) >= float(threshold)
        mode = "fast_decision" if abs(delta) >= float(fast_threshold) else "long_study"
        notification = None
        if triggered:
            notification = {
                "notification_id": str(uuid.uuid4()),
                "trigger_type": "global_roi",
                "global_roi": global_roi,
                "previous_global_roi": previous_roi,
                "roi_delta": delta,
                "mode": mode,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            redis_client.lpush(self.notifications_key, json.dumps(notification))
            redis_client.ltrim(self.notifications_key, 0, 500)

        return {
            "success": True,
            "enabled": True,
            "triggered": triggered,
            "global_roi": global_roi,
            "previous_global_roi": previous_roi,
            "roi_delta": delta,
            "threshold_pct": threshold,
            "fast_threshold_pct": fast_threshold,
            "notification": notification,
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
                self.add_position,
                explicit_schema=self._schema(
                    "watchlist_add_position",
                    "Register a position in watchlist with stop-loss/take-profit thresholds.",
                    {
                        "token_symbol": {"type": "string"},
                        "token_address": {"type": "string"},
                        "quantity": {"type": "number"},
                        "entry_price": {"type": "number"},
                        "wallet_address": {"type": "string"},
                        "stop_loss_pct": {"type": "number"},
                        "take_profit_pct": {"type": "number"},
                        "mode": {"type": "string"},
                        "exit_to_symbol": {"type": "string"},
                        "exit_plan": {"type": "object"},
                    },
                    ["token_symbol", "token_address", "quantity", "entry_price", "wallet_address"],
                ),
            ),
            create_function_tool(
                self.get_position,
                explicit_schema=self._schema(
                    "watchlist_get_position",
                    "Get a watchlist position by id.",
                    {
                        "position_id": {"type": "string"},
                    },
                    ["position_id"],
                ),
            ),
            create_function_tool(
                self.update_exit_plan,
                explicit_schema=self._schema(
                    "watchlist_update_exit_plan",
                    "Attach or update on-chain exit plan for a watchlist position.",
                    {
                        "position_id": {"type": "string"},
                        "exit_plan": {"type": "object"},
                        "exit_to_symbol": {"type": "string"},
                    },
                    ["position_id", "exit_plan"],
                ),
            ),
            create_function_tool(
                self.update_price,
                explicit_schema=self._schema(
                    "watchlist_update_price",
                    "Update latest token price for watchlist evaluations.",
                    {
                        "token_symbol": {"type": "string"},
                        "price": {"type": "number"},
                    },
                    ["token_symbol", "price"],
                ),
            ),
            create_function_tool(
                self.list_positions,
                explicit_schema=self._schema(
                    "watchlist_list_positions",
                    "List tracked watchlist positions.",
                    {
                        "status": {"type": "string"},
                    },
                    [],
                ),
            ),
            create_function_tool(
                self.evaluate_triggers,
                explicit_schema=self._schema(
                    "watchlist_evaluate_triggers",
                    "Evaluate stop-loss and take-profit triggers and emit notifications.",
                    {},
                    [],
                ),
            ),
            create_function_tool(
                self.evaluate_global_roi_trigger,
                explicit_schema=self._schema(
                    "watchlist_evaluate_global_roi_trigger",
                    "Evaluate global portfolio ROI delta trigger and emit notification for review/decision flow.",
                    {
                        "threshold_pct": {"type": "number"},
                        "fast_threshold_pct": {"type": "number"},
                        "enabled": {"type": "boolean"},
                    },
                    [],
                ),
            ),
        ]
