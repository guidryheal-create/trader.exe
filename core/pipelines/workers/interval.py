"""Interval-based worker primitive."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from core.logging import log


class IntervalWorker:
    """Execute an async callback on a fixed interval while running."""

    def __init__(
        self,
        callback: Callable[[], Awaitable[Any]],
        interval_seconds: int,
        *,
        name: str = "interval_worker",
        min_interval_seconds: int = 1,
    ) -> None:
        self.callback = callback
        self.interval_seconds = int(interval_seconds)
        self.name = name
        self.min_interval_seconds = int(min_interval_seconds)

    async def run_loop(self, is_running: Callable[[], bool]) -> None:
        while is_running():
            try:
                await self.callback()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("[%s] run loop error: %s", self.name, exc, exc_info=True)
            await asyncio.sleep(max(self.min_interval_seconds, self.interval_seconds))

