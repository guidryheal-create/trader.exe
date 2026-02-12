from __future__ import annotations

import pytest

from core.pipelines.dex_manager import DexManager, ReviewMode


class _FakeWorkforce:
    async def process_task_async(self, task):
        return {"ok": True, "task_type": getattr(task, "type", "unknown")}


class _FakeUviToolkit:
    def execute_watchlist_exit(self, position_id: str, trigger_type: str):
        return {"success": True, "tx_hash": "0xtx", "position_id": position_id, "trigger_type": trigger_type}

    def register_stop_loss_take_profit(self, **kwargs):
        return {"success": True, "position": kwargs}


class _FakeWatchlist:
    redis = None
    positions_key = "watchlist:positions"

    def evaluate_triggers(self):
        return {"success": True, "count": 0, "notifications": []}

    def evaluate_global_roi_trigger(self, threshold_pct=None, fast_threshold_pct=None, enabled=None):
        return {"success": True, "triggered": False}

    def list_positions(self, status="open"):
        return {
            "success": True,
            "positions": [
                {
                    "position_id": "p1",
                    "token_symbol": "ETH",
                    "quantity": 1.0,
                    "entry_price": 2000.0,
                    "wallet_address": "0xwallet",
                    "status": "open",
                }
            ],
        }

    def close_position(self, position_id: str, close_reason: str):
        return {"success": True, "position": {"position_id": position_id, "status": "closed", "close_reason": close_reason}}

    def add_position(self, **kwargs):
        return {"success": True, "position": kwargs}


class _FakeWallet:
    def get_wallet_feedback(self, wallet_address: str = ""):
        return {"success": True, "wallet_address": wallet_address, "feedback": []}

    def get_global_wallet_state(self, wallet_address: str = ""):
        return {
            "success": True,
            "wallet_address": wallet_address or "all",
            "global_invested": 1000.0,
            "global_current_value": 1050.0,
            "global_pnl": 50.0,
            "global_roi": 0.05,
            "per_token_investment": {"ETH": {"invested": 1000.0, "current_value": 1050.0, "pnl": 50.0, "roi": 0.05}},
            "open_position_count": 1,
        }


class _FakeEnhancement:
    def generate_feedback(self):
        return {"success": True, "feedback": {"improvements": []}}


@pytest.mark.asyncio
async def test_review_cycle_branching():
    worker = DexManager(
        workforce=_FakeWorkforce(),
        uviswap_toolkit=_FakeUviToolkit(),
        watchlist_toolkit=_FakeWatchlist(),
        wallet_toolkit=_FakeWallet(),
        enhancement_toolkit=_FakeEnhancement(),
    )

    long_res = await worker.run_trigger_flow(
        "watchlist_review",
        notification={"position_id": "p1", "wallet_address": "0xwallet"},
        mode=ReviewMode.LONG_STUDY,
    )
    assert long_res["success"] is True

    fast_res = await worker.run_trigger_flow(
        "watchlist_review",
        notification={"position_id": "p1", "wallet_address": "0xwallet"},
        mode=ReviewMode.FAST_DECISION,
    )
    assert fast_res["success"] is True
    assert fast_res["mode"] == "fast_decision"


@pytest.mark.asyncio
async def test_watchlist_notification_executes_exit():
    worker = DexManager(
        workforce=_FakeWorkforce(),
        uviswap_toolkit=_FakeUviToolkit(),
        watchlist_toolkit=_FakeWatchlist(),
        wallet_toolkit=_FakeWallet(),
        enhancement_toolkit=_FakeEnhancement(),
    )

    await worker.run_trigger_flow(
        "watchlist_notification",
        notification={
            "position_id": "p1",
            "token_symbol": "ETH",
            "trigger_type": "take_profit",
            "pct_change": 0.12,
            "entry_price": 2000.0,
            "current_price": 2240.0,
            "wallet_address": "0xwallet",
        },
    )


@pytest.mark.asyncio
async def test_global_roi_notification_triggers_main_cycle(monkeypatch):
    worker = DexManager(
        workforce=_FakeWorkforce(),
        uviswap_toolkit=_FakeUviToolkit(),
        watchlist_toolkit=_FakeWatchlist(),
        wallet_toolkit=_FakeWallet(),
        enhancement_toolkit=_FakeEnhancement(),
    )

    calls = {"reason": None}

    async def _fake_hub_run(*, trigger_type, context, flags, selected_task_ids):
        calls["reason"] = context.get("reason")
        return {"cycle_pipeline": {"success": True, "mode": context.get("mode").value, "reason": context.get("reason")}}

    monkeypatch.setattr(worker._task_flow_hub, "run", _fake_hub_run)

    await worker.run_trigger_flow(
        "watchlist_notification",
        notification={
            "trigger_type": "global_roi",
            "mode": "fast_decision",
            "roi_delta": 0.12,
        },
    )

    assert calls["reason"] == "watchlist_global_roi_trigger"
