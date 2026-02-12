from __future__ import annotations

import pytest

from core.pipelines.dex.watchlist_worker import WatchlistWorker


class _FakeWatchlist:
    def evaluate_triggers(self):
        return {
            "notifications": [
                {"trigger_type": "take_profit", "position_id": "p1"},
                {"trigger_type": "stop_loss", "position_id": "p2"},
            ]
        }


@pytest.mark.asyncio
async def test_watchlist_worker_run_once_dispatches_notifications():
    received: list[dict] = []

    async def _on_notification(notification: dict):
        received.append(notification)

    worker = WatchlistWorker(
        watchlist_toolkit=_FakeWatchlist(),
        on_notification=_on_notification,
        evaluate_global_roi=lambda: {
            "triggered": True,
            "notification": {"trigger_type": "global_roi", "mode": "fast_decision"},
        },
    )

    count = await worker.run_once()
    assert count == 3
    assert len(received) == 3
    assert any(item.get("trigger_type") == "global_roi" for item in received)

