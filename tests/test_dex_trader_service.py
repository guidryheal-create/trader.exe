from api.services.dex.trader_service import DexTraderService
import asyncio


def test_dex_trader_service_in_memory_logs_and_config():
    service = DexTraderService()
    service._redis = None
    service._in_memory_logs = []

    updated = service.update_config(
        {
            "process": {"active_bot": "dex", "cycle_hours": 8},
            "runtime": {"cycle_enabled": True, "watchlist_enabled": True, "auto_start_on_boot": True},
        }
    )
    assert updated["process"]["cycle_hours"] == 8
    assert updated["runtime"]["cycle_enabled"] is True

    service._record_event("info", "DEX cycle started", {"mode": "long_study"})
    service._record_event("info", "DEX task started", {"task_type": "decision_gateway"})
    service._record_event("info", "DEX task completed", {"task_type": "decision_gateway"})

    logs = service.list_logs(limit=10)
    assert len(logs) >= 3
    assert any("cycle started" in e["message"].lower() for e in logs)


def test_dex_trader_service_trigger_cycle_returns_execution_id(monkeypatch):
    service = DexTraderService()
    service._redis = None

    class _FakeTrader:
        def launch_execution(self, mode, reason):
            return "exec-123"

    async def _ensure_trader():
        return _FakeTrader()

    monkeypatch.setattr(service, "ensure_trader", _ensure_trader)
    result = asyncio.run(service.trigger_cycle(mode="long_study", reason="unit_test"))
    assert result["status"] == "accepted"
    assert result["execution_id"] == "exec-123"
