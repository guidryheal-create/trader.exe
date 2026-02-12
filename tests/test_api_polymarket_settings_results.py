import asyncio

from api.routers.polymarket import settings as settings_router
from api.routers.polymarket import results as results_router
from api.routers.polymarket import monitoring as monitoring_router
from api.models.polymarket import SettingsUpdateRequest


def test_settings_get_and_update():
    data = asyncio.run(settings_router.get_settings())
    payload = data.model_dump() if hasattr(data, "model_dump") else data
    assert payload["status"] == "ok"
    assert "config" in payload

    update_payload = {
        "process": {
            "active_flux": "polymarket_rss_flux",
            "trade_frequency_hours": 6,
            "max_ai_weighted_daily": 0.8,
            "max_ai_weighted_per_trade": 0.5,
        }
    }
    updated = asyncio.run(settings_router.update_settings(SettingsUpdateRequest(**update_payload)))
    updated_payload = updated.model_dump() if hasattr(updated, "model_dump") else updated
    assert updated_payload["status"] == "ok"
    assert updated_payload["config"]["active_flux"] == "polymarket_rss_flux"


def test_results_summary_and_trades(monkeypatch):
    monkeypatch.setattr(results_router.trade_service, "get_summary", lambda: {"total_trades": 0})
    monkeypatch.setattr(results_router.trade_service, "list_trades", lambda limit=50, status=None, asset=None: [])

    summary = asyncio.run(results_router.get_results_summary())
    summary_payload = summary.model_dump() if hasattr(summary, "model_dump") else summary
    assert summary_payload["status"] == "ok"
    assert "summary" in summary_payload

    trades = asyncio.run(results_router.get_recent_trades(limit=10))
    trades_payload = trades.model_dump() if hasattr(trades, "model_dump") else trades
    assert trades_payload["status"] == "ok"
    assert trades_payload["count"] == 0


def test_polymarket_trigger_settings_endpoints(monkeypatch):
    monkeypatch.setattr(
        settings_router.process_config_service,
        "list_trigger_specs",
        lambda: [{"pipeline": "polymarket", "trigger": "interval"}],
    )
    monkeypatch.setattr(
        settings_router.process_config_service,
        "get_trigger_settings",
        lambda trigger_name: {"trigger": trigger_name, "settings": {"interval_hours": 4}},
    )
    monkeypatch.setattr(
        settings_router.process_config_service,
        "update_trigger_settings",
        lambda trigger_name, payload: {"trigger": trigger_name, "settings": payload},
    )

    listing = asyncio.run(settings_router.list_trigger_settings())
    assert listing["status"] == "ok"
    assert listing["count"] == 1

    one = asyncio.run(settings_router.get_trigger_settings("interval"))
    assert one["status"] == "ok"
    assert one["item"]["trigger"] == "interval"

    updated = asyncio.run(settings_router.update_trigger_settings("interval", {"interval_hours": 6}))
    assert updated["status"] == "ok"
    assert updated["item"]["settings"]["interval_hours"] == 6


def test_polymarket_workers_endpoint(monkeypatch):
    class _Flux:
        def get_status(self):
            return {
                "pipeline": "polymarket",
                "system_name": "polymarket_rss_flux",
                "workers": [{"worker_name": "interval"}],
                "timestamp": "2026-01-01T00:00:00+00:00",
            }

    monkeypatch.setattr("api.routers.polymarket.rss_flux.get_rss_flux", lambda: _Flux())
    payload = asyncio.run(monitoring_router.get_workers())
    assert payload["status"] == "ok"
    assert payload["count"] == 1


def test_polymarket_task_flows_settings_endpoint(monkeypatch):
    class _Flux:
        def list_task_flows(self):
            return [{"task_id": "batch_orchestration", "handler_name": "PolymarketBatchOrchestrationTask", "enabled": True}]

        def update_task_flows(self, payload):
            return [
                {
                    "task_id": "batch_orchestration",
                    "handler_name": "PolymarketBatchOrchestrationTask",
                    "enabled": bool(payload.get("batch_orchestration", True)),
                }
            ]

    async def _ensure_rss_flux():
        return _Flux()

    monkeypatch.setattr("api.routers.polymarket.rss_flux.ensure_rss_flux", _ensure_rss_flux)
    monkeypatch.setattr(
        settings_router.process_config_service,
        "get_config",
        lambda: {"task_flows": {"batch_orchestration": True}, "last_updated": "2026-01-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        settings_router.process_config_service,
        "update_config",
        lambda payload: {"task_flows": payload.get("task_flows", {}), "last_updated": "2026-01-01T00:00:00+00:00"},
    )

    listing = asyncio.run(settings_router.get_task_flows())
    assert listing["status"] == "ok"
    assert listing["count"] == 1
    assert listing["items"][0]["handler_name"] == "PolymarketBatchOrchestrationTask"


def test_polymarket_trigger_flows_endpoint(monkeypatch):
    class _Flux:
        def get_status(self):
            return {
                "pipeline": "polymarket",
                "system_name": "polymarket_manager",
                "trigger_flows": [{"trigger_id": "market_batch", "handler_name": "PolymarketBatchTriggerFlow"}],
                "timestamp": "2026-01-01T00:00:00+00:00",
            }

    monkeypatch.setattr("api.routers.polymarket.rss_flux.get_rss_flux", lambda: _Flux())
    payload = asyncio.run(monitoring_router.get_trigger_flows())
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["items"][0]["trigger_id"] == "market_batch"
