"""Watchlist trigger worker for DEX runtime."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from core.logging import log
from core.pipelines.workers.conditional import ConditionalCallbackWorker


class WatchlistWorker:
    """Process watchlist triggers and dispatch notifications."""

    def __init__(
        self,
        watchlist_toolkit: Any,
        on_notification: Callable[[dict[str, Any]], Awaitable[None]],
        evaluate_global_roi: Callable[[], dict[str, Any]],
    ) -> None:
        self.watchlist_toolkit = watchlist_toolkit
        self.on_notification = on_notification
        self.evaluate_global_roi = evaluate_global_roi
        self._trigger_worker = ConditionalCallbackWorker(
            fetch_items=self._fetch_trigger_notifications,
            on_item=self.on_notification,
        )

    def _fetch_trigger_notifications(self) -> list[dict[str, Any]]:
        trigger_result = self.watchlist_toolkit.evaluate_triggers()
        return list(trigger_result.get("notifications", []))

    async def run_once(self) -> int:
        processed = await self._trigger_worker.run_once()

        global_roi_result = self.evaluate_global_roi()
        if global_roi_result.get("triggered"):
            notification = global_roi_result.get("notification") or {}
            await self.on_notification(notification)
            processed += 1

        return processed

    async def run_loop(self, is_running: Callable[[], bool], scan_seconds: int) -> None:
        while is_running():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error(f"Watchlist loop error: {exc}", exc_info=True)
            await asyncio.sleep(max(5, int(scan_seconds)))
