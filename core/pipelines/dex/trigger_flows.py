"""Class-based DEX trigger flows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.pipelines.dex.types import ReviewMode
from core.pipelines.triggers import BaseTriggerFlow


class DexCycleTriggerFlow(BaseTriggerFlow):
    trigger_id = "cycle"
    pipeline = "dex"
    system_name = "dex_manager"
    scheduler_type = "interval"
    description = "Run one DEX decision cycle pipeline."
    input_schema = {
        "type": "object",
        "required": ["mode", "reason"],
        "properties": {
            "mode": {"type": "string"},
            "reason": {"type": "string"},
            "execution_id": {"type": ["string", "null"]},
        },
    }

    async def resolve(self, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        mode = kwargs.get("mode", ReviewMode.LONG_STUDY)
        reason = str(kwargs.get("reason", "manual_trigger"))
        execution_id = kwargs.get("execution_id")
        flow_results = await runtime._task_flow_hub.run(
            trigger_type=reason,
            context={"mode": mode, "reason": reason, "execution_id": execution_id},
            flags=runtime._task_flow_flags,
            selected_task_ids=["cycle_pipeline"],
        )
        result = flow_results.get("cycle_pipeline", {})
        if isinstance(result, dict):
            sanitized = {k: v for k, v in result.items() if k != "task_flows"}
            sanitized["task_flows"] = {
                "cycle_pipeline": {
                    "status": "completed" if result.get("success") else "failed",
                    "task_id": "cycle_pipeline",
                }
            }
            return sanitized
        return {"success": False, "task_flows": flow_results, "error": "cycle_pipeline_failed"}


class DexWatchlistReviewTriggerFlow(BaseTriggerFlow):
    trigger_id = "watchlist_review"
    pipeline = "dex"
    system_name = "dex_manager"
    scheduler_type = "event"
    description = "Run review flow for watchlist triggers."
    input_schema = {
        "type": "object",
        "required": ["notification", "mode"],
        "properties": {
            "notification": {"type": "object"},
            "mode": {"type": "string"},
        },
    }

    async def resolve(self, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        notification = kwargs.get("notification", {}) or {}
        mode = kwargs.get("mode", ReviewMode.LONG_STUDY)
        if mode == ReviewMode.FAST_DECISION:
            return await runtime.run_trigger_flow(
                "cycle",
                mode=mode,
                reason="watchlist_fast_trigger",
            )

        flow_results = await runtime._task_flow_hub.run(
            trigger_type="watchlist_review_only",
            context={"notification": notification},
            flags=runtime._task_flow_flags,
            selected_task_ids=["watchlist_review_pipeline"],
        )
        result = flow_results.get("watchlist_review_pipeline", {})
        if isinstance(result, dict):
            return result
        return {"success": False, "error": "watchlist_review_pipeline_failed"}


class DexWatchlistNotificationTriggerFlow(BaseTriggerFlow):
    trigger_id = "watchlist_notification"
    pipeline = "dex"
    system_name = "dex_manager"
    scheduler_type = "event"
    description = "Handle watchlist notifications and dispatch decision/review flows."
    input_schema = {
        "type": "object",
        "required": ["notification"],
        "properties": {
            "notification": {"type": "object"},
        },
    }

    async def resolve(self, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        notification: dict[str, Any] = kwargs.get("notification", {}) or {}
        runtime._emit("INFO", "Watchlist notification received", notification)

        if str(notification.get("trigger_type")) == "global_roi":
            mode = ReviewMode.FAST_DECISION if str(notification.get("mode")) == "fast_decision" else ReviewMode.LONG_STUDY
            return await runtime.run_trigger_flow(
                "cycle",
                mode=mode,
                reason="watchlist_global_roi_trigger",
            )

        symbol = str(notification.get("token_symbol", "")).upper()
        position_id = str(notification.get("position_id", ""))
        positions = runtime.watchlist_toolkit.list_positions(status="open").get("positions", [])
        position = next((p for p in positions if p.get("position_id") == position_id), None)
        if not position:
            return {"success": False, "reason": "position_not_found", "position_id": position_id}

        quantity = float(position.get("quantity", 0) or 0)
        if quantity > 0:
            sell_result = runtime.uviswap_toolkit.execute_watchlist_exit(
                position_id=position_id,
                trigger_type=str(notification.get("trigger_type", "trigger")),
            )
            runtime._record_trade_history(
                {
                    "side": "SELL",
                    "reason": notification.get("trigger_type"),
                    "symbol": symbol,
                    "quantity": quantity,
                    "result": sell_result,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            current_price = float(notification.get("current_price", 0) or 0)
            entry_price = float(notification.get("entry_price", 0) or 0)
            realized_pnl = (current_price - entry_price) * quantity
            close = runtime.watchlist_toolkit.close_position(
                position_id,
                close_reason=notification.get("trigger_type", "trigger"),
            )
            if close.get("success"):
                closed = close.get("position", {})
                closed["realized_pnl"] = realized_pnl
                if runtime.watchlist_toolkit.redis:
                    runtime.watchlist_toolkit.redis.hset(
                        runtime.watchlist_toolkit.positions_key,
                        position_id,
                        json.dumps(closed),
                    )

        change_abs = abs(float(notification.get("pct_change", 0.0)))
        mode = ReviewMode.FAST_DECISION if change_abs >= runtime.config.watchlist_fast_trigger_pct else ReviewMode.LONG_STUDY
        review_result = await runtime.run_trigger_flow(
            "watchlist_review",
            notification=notification,
            mode=mode,
        )
        return {"success": True, "mode": mode.value, "review": review_result}


def build_dex_trigger_flows(runtime: Any) -> list[BaseTriggerFlow]:
    return [
        DexCycleTriggerFlow(runtime),
        DexWatchlistReviewTriggerFlow(runtime),
        DexWatchlistNotificationTriggerFlow(runtime),
    ]
