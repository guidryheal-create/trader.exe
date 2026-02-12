from __future__ import annotations

import asyncio

import pytest

from core.pipelines.dex.execution_tracker import ExecutionTracker
from core.pipelines.dex.types import ReviewMode


@pytest.mark.asyncio
async def test_execution_tracker_launch_and_complete():
    tracker = ExecutionTracker(lambda payload, _max_len: str(payload))

    async def _run(_execution_id: str):
        await asyncio.sleep(0.01)
        return {"success": True}

    execution_id = tracker.launch(mode=ReviewMode.LONG_STUDY, reason="test", run_fn=_run)
    await asyncio.sleep(0.05)

    state = tracker.get_status(execution_id)
    assert state["execution_id"] == execution_id
    assert state["status"] == "completed"


@pytest.mark.asyncio
async def test_execution_tracker_failure_state():
    tracker = ExecutionTracker(lambda payload, _max_len: str(payload))

    async def _run(_execution_id: str):
        raise RuntimeError("boom")

    execution_id = tracker.launch(mode=ReviewMode.FAST_DECISION, reason="test", run_fn=_run)
    await asyncio.sleep(0.02)

    state = tracker.get_status(execution_id)
    assert state["status"] == "failed"
    assert "boom" in state.get("error", "")

