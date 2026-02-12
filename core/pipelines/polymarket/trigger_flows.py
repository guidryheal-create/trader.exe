"""Class-based Polymarket trigger flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.logging import log
from core.pipelines.triggers import BaseTriggerFlow


class PolymarketBatchTriggerFlow(BaseTriggerFlow):
    trigger_id = "market_batch"
    pipeline = "polymarket"
    system_name = "polymarket_manager"
    scheduler_type = "event"
    description = "Scan/fetch/filter markets and run one batch orchestration pipeline."
    input_schema = {
        "type": "object",
        "properties": {
            "trigger_type": {"type": "string"},
            "verify_positions": {"type": "boolean"},
            "enforce_limits": {"type": "boolean"},
        },
    }

    async def resolve(self, **kwargs: Any) -> dict[str, Any]:
        runtime = self.runtime
        trigger_type = str(kwargs.get("trigger_type", "interval"))
        verify_positions = bool(kwargs.get("verify_positions", True))
        enforce_limits = bool(kwargs.get("enforce_limits", True))

        if runtime._scan_lock.locked():
            return {
                "status": "in_progress",
                "triggered": False,
                "reason": "scan_in_progress",
                "trigger_type": trigger_type,
            }

        now = datetime.now(timezone.utc)
        if now.date() > runtime._trade_day:
            runtime._trade_day = now.date()
            runtime._trades_today = 0
        use_cache = trigger_type != "manual"
        check_threshold = trigger_type != "manual"
        if trigger_type == "manual":
            verify_positions = False
            enforce_limits = False
        if (
            trigger_type == "interval"
            and runtime._last_interval_trigger_at
            and (now - runtime._last_interval_trigger_at).total_seconds() < runtime.scan_interval
        ):
            return {
                "status": "skipped",
                "triggered": False,
                "reason": "interval_throttle",
                "trigger_type": trigger_type,
            }

        async with runtime._scan_lock:
            if callable(runtime._event_logger):
                try:
                    runtime._event_logger(
                        "INFO",
                        "RSS flux scan started",
                        {"trigger_type": trigger_type},
                    )
                except Exception:
                    pass
            runtime._last_trigger_at = now
            runtime._last_trigger_type = trigger_type
            if trigger_type == "interval":
                runtime._last_interval_trigger_at = now

            batch_id = f"batch_{int(datetime.now(timezone.utc).timestamp())}"
            log.info("[POLYMARKET MANAGER] Processing batch %s (%s)", batch_id, trigger_type)

            try:
                if verify_positions:
                    await runtime._refresh_active_positions()

                markets = await runtime._fetch_latest_markets()
                if not markets:
                    log.debug("[POLYMARKET MANAGER] No markets found in scan")
                    return {"batch_id": batch_id, "markets_found": 0, "analyzed": 0}

                pending_markets = []
                if use_cache:
                    runtime._update_feed_cache(markets)
                    pending_markets = runtime._feed_runtime.pending_items()
                    if check_threshold and not runtime._feed_runtime.ready():
                        runtime._save_cache()
                        return {
                            "batch_id": batch_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "markets_scanned": len(markets),
                            "pending_review": len(pending_markets),
                            "threshold": runtime.review_threshold,
                            "trigger_type": trigger_type,
                        }

                if use_cache:
                    filtered = runtime._filter_markets([m["data"] for m in pending_markets])
                else:
                    filtered = markets[: runtime.batch_size]
                if not filtered:
                    return {
                        "batch_id": batch_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "markets_scanned": len(markets),
                        "opportunities_filtered": 0,
                        "trigger_type": trigger_type,
                    }

                before_positions = set(runtime._active_positions.keys())
                workforce_result = await runtime._run_batch_task(
                    filtered,
                    trigger_type=trigger_type,
                    enforce_limits=enforce_limits,
                )
                if verify_positions:
                    await runtime._refresh_active_positions()
                after_positions = set(runtime._active_positions.keys())
                new_positions = list(after_positions - before_positions)
                if enforce_limits:
                    runtime._trades_today += len(new_positions)

                if use_cache:
                    runtime._feed_runtime.mark_processed(filtered)
                    runtime._feed_cache = runtime._feed_runtime.cache
                    runtime._save_cache()

                summary = {
                    "batch_id": batch_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "markets_scanned": len(markets),
                    "opportunities_filtered": len(filtered),
                    "trades_executed": len(new_positions),
                    "new_positions": new_positions,
                    "positions_active": len(runtime._active_positions),
                    "pending_review": len(runtime._feed_cache) if use_cache else 0,
                    "trigger_type": trigger_type,
                    "workforce_result": workforce_result,
                }
                if callable(runtime._event_logger):
                    try:
                        runtime._event_logger(
                            "INFO",
                            "RSS flux scan completed",
                            {
                                "batch_id": batch_id,
                                "trigger_type": trigger_type,
                                "markets_scanned": summary.get("markets_scanned"),
                                "opportunities_filtered": summary.get("opportunities_filtered"),
                                "trades_executed": summary.get("trades_executed"),
                                "pending_review": summary.get("pending_review"),
                            },
                        )
                    except Exception:
                        pass
                return summary
            except Exception as exc:
                log.error("[POLYMARKET MANAGER] Batch processing failed: %s", exc, exc_info=True)
                if callable(runtime._event_logger):
                    try:
                        runtime._event_logger(
                            "ERROR",
                            "RSS flux scan failed",
                            {"batch_id": batch_id, "error": str(exc), "trigger_type": trigger_type},
                        )
                    except Exception:
                        pass
                return {
                    "batch_id": batch_id,
                    "error": str(exc),
                    "status": "failed",
                    "trigger_type": trigger_type,
                }


def build_polymarket_trigger_flows(runtime: Any) -> list[BaseTriggerFlow]:
    return [PolymarketBatchTriggerFlow(runtime)]
