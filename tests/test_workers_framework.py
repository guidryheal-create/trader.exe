from __future__ import annotations

import asyncio

import pytest

from core.pipelines.workers.conditional import ConditionalCallbackWorker
from core.pipelines.workers.feed_threshold import FeedCacheThresholdWorker
from core.pipelines.workers.hybrid import HybridWorker
from core.pipelines.workers.interval import IntervalWorker


@pytest.mark.asyncio
async def test_interval_worker_runs_callback():
    called = {"n": 0}
    running = {"on": True}

    async def _cb():
        called["n"] += 1
        if called["n"] >= 2:
            running["on"] = False

    worker = IntervalWorker(callback=_cb, interval_seconds=1, min_interval_seconds=0)
    await worker.run_loop(is_running=lambda: running["on"])
    assert called["n"] >= 2


@pytest.mark.asyncio
async def test_conditional_callback_worker_filters_items():
    seen: list[int] = []

    async def _on_item(item: int):
        seen.append(item)

    worker = ConditionalCallbackWorker(
        fetch_items=lambda: [1, 2, 3, 4],
        on_item=_on_item,
        condition=lambda item: item % 2 == 0,
    )
    processed = await worker.run_once()
    assert processed == 2
    assert seen == [2, 4]


def test_feed_cache_threshold_worker_threshold_and_mark_processed():
    worker = FeedCacheThresholdWorker(
        key_fn=lambda item: str(item.get("id", "")),
        entry_builder=lambda item, existing, now: {
            "id": item["id"],
            "first_seen": (existing or {}).get("first_seen", now),
            "last_seen": now,
            "exhausted": item.get("exhausted", False),
            "data": item,
        },
        is_entry_active=lambda entry: not entry.get("exhausted", False),
        max_cache=10,
        threshold=2,
    )
    worker.update([{"id": "a"}, {"id": "b"}])
    assert worker.ready() is True
    assert len(worker.pending_items()) == 2
    worker.mark_processed([{"id": "a"}])
    assert len(worker.pending_items()) == 1


@pytest.mark.asyncio
async def test_hybrid_worker_start_stop():
    running = {"a": True, "b": True}
    ticks = {"a": 0, "b": 0}

    async def _runner_a():
        while running["a"]:
            ticks["a"] += 1
            await asyncio.sleep(0.001)

    async def _runner_b():
        while running["b"]:
            ticks["b"] += 1
            await asyncio.sleep(0.001)

    hybrid = HybridWorker()
    hybrid.add_runner("a", _runner_a)
    hybrid.add_runner("b", _runner_b)
    hybrid.start()
    await asyncio.sleep(0.01)
    running["a"] = False
    running["b"] = False
    await hybrid.stop()
    assert ticks["a"] > 0
    assert ticks["b"] > 0

