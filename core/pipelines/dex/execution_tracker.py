"""Async execution state tracking for pipeline runs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from core.pipelines.dex.types import ReviewMode


class ExecutionTracker:
    """Track queued/running/completed pipeline executions."""

    def __init__(self, summarize_payload: Callable[[dict[str, Any], int], str]) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._state: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._summarize_payload = summarize_payload

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def set_state(self, execution_id: str, **updates: Any) -> None:
        state = self._state.get(execution_id, {})
        state.update(updates)
        state["updated_at"] = self._now_iso()
        self._state[execution_id] = state

    def launch(
        self,
        mode: ReviewMode,
        reason: str,
        run_fn: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> str:
        execution_id = str(uuid4())
        now = self._now_iso()
        self._state[execution_id] = {
            "execution_id": execution_id,
            "mode": mode.value,
            "reason": reason,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }
        self._order.insert(0, execution_id)
        self._order = self._order[:500]

        async def _runner() -> None:
            self.set_state(execution_id, status="running")
            try:
                result = await run_fn(execution_id)
                self.set_state(
                    execution_id,
                    status="completed",
                    result=self._summarize_payload(result, 4000),
                )
            except Exception as exc:
                self.set_state(execution_id, status="failed", error=str(exc))
            finally:
                self._tasks.pop(execution_id, None)

        self._tasks[execution_id] = asyncio.create_task(_runner())
        return execution_id

    def get_status(self, execution_id: str) -> dict[str, Any]:
        return self._state.get(execution_id, {"execution_id": execution_id, "status": "not_found"})

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for execution_id in self._order[: max(1, int(limit))]:
            item = self._state.get(execution_id)
            if item:
                items.append(item)
        return items

    async def cancel_all(self) -> None:
        for execution_id, task in list(self._tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.set_state(execution_id, status="cancelled")
        self._tasks.clear()

