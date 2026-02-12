"""Hybrid worker that composes multiple worker loops."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


class HybridWorker:
    """Start and stop multiple async loop runners as a single unit."""

    def __init__(self) -> None:
        self._runners: dict[str, Callable[[], Awaitable[None]]] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def add_runner(self, name: str, runner: Callable[[], Awaitable[None]]) -> None:
        self._runners[name] = runner

    def start(self) -> None:
        for name, runner in self._runners.items():
            if name in self._tasks:
                continue
            self._tasks[name] = asyncio.create_task(runner())

    async def stop(self) -> None:
        for name, task in list(self._tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._tasks.pop(name, None)

