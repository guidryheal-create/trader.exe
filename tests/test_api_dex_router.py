import asyncio

from api.routers.dex import config as dex_config_router
from api.routers.dex import monitoring as dex_monitoring_router
from api.routers.dex import settings as dex_settings_router
from api.models.dex import DexConfigUpdateRequest, DexTriggerRequest, DexControlRequest


def test_dex_config_get_and_update(monkeypatch):
    monkeypatch.setattr(
        dex_config_router.dex_trader_service,
        "get_config",
        lambda: {
            "process": {
                "active_bot": "dex",
                "cycle_hours": 4,
                "watchlist_scan_seconds": 60,
                "watchlist_trigger_pct": 0.05,
                "watchlist_fast_trigger_pct": 0.1,
                "watchlist_global_roi_trigger_enabled": True,
                "watchlist_global_roi_trigger_pct": 0.04,
                "watchlist_global_roi_fast_trigger_pct": 0.08,
                "token_exploration_limit": 20,
                "wallet_review_cache_seconds": 3600,
                "strategy_hint_interval_hours": 6,
                "auto_enhancement_enabled": True,
            },
            "runtime": {
                "cycle_enabled": False,
                "watchlist_enabled": False,
                "auto_start_on_boot": True,
            },
            "last_updated": "2026-01-01T00:00:00+00:00",
        },
    )
    cfg = asyncio.run(dex_config_router.get_config())
    payload = cfg.model_dump() if hasattr(cfg, "model_dump") else cfg
    assert payload["status"] == "ok"
    assert payload["process"]["active_bot"] == "dex"

    monkeypatch.setattr(dex_config_router.dex_trader_service, "update_config", lambda payload: {
        "process": {**payload.get("process", {}), "active_bot": "dex"},
        "runtime": payload.get("runtime", {}),
        "last_updated": "2026-01-01T00:00:00+00:00",
    })
    updated = asyncio.run(
        dex_config_router.update_config(
            DexConfigUpdateRequest(
                process={"active_bot": "dex"},
                runtime={"cycle_enabled": True, "watchlist_enabled": True, "auto_start_on_boot": True},
            )
        )
    )
    updated_payload = updated.model_dump() if hasattr(updated, "model_dump") else updated
    assert updated_payload["status"] == "ok"


def test_dex_control_and_trigger(monkeypatch):
    async def _start(cycle_enabled: bool, watchlist_enabled: bool):
        return {"status": "ok", "cycle_enabled": cycle_enabled, "watchlist_enabled": watchlist_enabled}

    async def _trigger(mode: str, reason: str):
        return {"status": "accepted", "execution_id": "exec-1"}

    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "start", _start)
    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "trigger_cycle", _trigger)

    started = asyncio.run(dex_monitoring_router.start_trader(DexControlRequest(cycle_enabled=True, watchlist_enabled=False)))
    assert started["status"] == "ok"
    assert started["cycle_enabled"] is True
    assert started["watchlist_enabled"] is False

    trig = asyncio.run(dex_monitoring_router.trigger_cycle(DexTriggerRequest(mode="fast_decision", reason="test")))
    assert trig["status"] == "accepted"
    assert trig["execution_id"] == "exec-1"


def test_dex_dashboard_and_bot_mode(monkeypatch):
    async def _status():
        return {
            "status": "ok",
            "running": False,
            "cycle_enabled": False,
            "watchlist_enabled": False,
            "active_bot": "dex",
            "workforce": {},
            "wallet_state": {"open_position_count": 0},
            "metrics": {},
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    async def _dashboard():
        return {"status": "ok", "active_bot": "dex", "counts": {"logs": 0}}

    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "get_status", _status)
    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "get_dashboard_snapshot", _dashboard)
    monkeypatch.setattr(
        dex_config_router.dex_trader_service,
        "get_config",
        lambda: {"process": {"active_bot": "dex"}, "runtime": {}, "last_updated": "2026-01-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        dex_config_router.dex_trader_service,
        "update_config",
        lambda payload: {"process": {"active_bot": payload["process"]["active_bot"]}, "runtime": {}, "last_updated": "2026-01-01T00:00:00+00:00"},
    )

    dashboard = asyncio.run(dex_monitoring_router.get_dashboard())
    assert dashboard["status"] == "ok"

    mode = asyncio.run(dex_config_router.get_bot_mode())
    assert mode["active_bot"] == "dex"

    changed = asyncio.run(dex_config_router.set_bot_mode(active_bot="polymarket"))
    assert changed["active_bot"] == "polymarket"


def test_dex_executions_endpoints(monkeypatch):
    async def _list_executions(limit: int = 50):
        return [{"execution_id": "exec-1", "status": "running"}]

    async def _get_execution(execution_id: str):
        return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "list_executions", _list_executions)
    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "get_execution", _get_execution)

    listing = asyncio.run(dex_monitoring_router.list_executions(limit=10))
    assert listing["status"] == "ok"
    assert listing["count"] == 1

    one = asyncio.run(dex_monitoring_router.get_execution("exec-1"))
    assert one["status"] == "ok"
    assert one["item"]["execution_id"] == "exec-1"


def test_dex_trigger_settings_endpoints(monkeypatch):
    monkeypatch.setattr(
        dex_config_router.dex_trader_service,
        "list_trigger_specs",
        lambda: [{"pipeline": "dex", "trigger": "watchlist"}],
    )
    monkeypatch.setattr(
        dex_config_router.dex_trader_service,
        "get_trigger_settings",
        lambda trigger_name: {"trigger": trigger_name, "settings": {"enabled": True}},
    )
    monkeypatch.setattr(
        dex_config_router.dex_trader_service,
        "update_trigger_settings",
        lambda trigger_name, payload: {"trigger": trigger_name, "settings": payload},
    )

    listing = asyncio.run(dex_config_router.list_trigger_settings())
    assert listing["status"] == "ok"
    assert listing["count"] == 1

    one = asyncio.run(dex_config_router.get_trigger_settings("watchlist"))
    assert one["status"] == "ok"
    assert one["item"]["trigger"] == "watchlist"

    updated = asyncio.run(dex_config_router.update_trigger_settings("watchlist", {"enabled": False}))
    assert updated["status"] == "ok"
    assert updated["item"]["settings"]["enabled"] is False


def test_dex_workers_endpoint(monkeypatch):
    async def _status():
        return {
            "status": "ok",
            "pipeline": "dex",
            "system_name": "dex_trader",
            "workers": [{"worker_name": "cycle_interval"}],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "get_status", _status)
    payload = asyncio.run(dex_monitoring_router.get_workers())
    assert payload["status"] == "ok"
    assert payload["count"] == 1


def test_dex_task_flows_settings_endpoint(monkeypatch):
    async def _list_task_flows():
        return [{"task_id": "wallet_review", "enabled": True}]

    async def _update_task_flows(payload):
        return [{"task_id": "wallet_review", "enabled": bool(payload.get("wallet_review", True))}]

    monkeypatch.setattr(dex_settings_router.dex_trader_service, "list_task_flows", _list_task_flows)
    monkeypatch.setattr(dex_settings_router.dex_trader_service, "update_task_flows", _update_task_flows)

    listing = asyncio.run(dex_settings_router.get_task_flows())
    assert listing["status"] == "ok"
    assert listing["count"] == 1

    updated = asyncio.run(dex_settings_router.update_task_flows({"wallet_review": False}))
    assert updated["status"] == "ok"
    assert updated["items"][0]["enabled"] is False


def test_dex_task_flow_metadata_includes_handler(monkeypatch):
    async def _list_task_flows():
        return [{"task_id": "cycle_pipeline", "handler_name": "DexCyclePipelineTask", "enabled": True}]

    monkeypatch.setattr(dex_settings_router.dex_trader_service, "list_task_flows", _list_task_flows)
    payload = asyncio.run(dex_settings_router.get_task_flows())
    assert payload["status"] == "ok"
    assert payload["items"][0]["handler_name"] == "DexCyclePipelineTask"


def test_dex_trigger_flows_endpoint(monkeypatch):
    async def _status():
        return {
            "status": "ok",
            "pipeline": "dex",
            "system_name": "dex_trader",
            "trigger_flows": [{"trigger_id": "cycle", "handler_name": "DexCycleTriggerFlow"}],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    monkeypatch.setattr(dex_monitoring_router.dex_trader_service, "get_status", _status)
    payload = asyncio.run(dex_monitoring_router.get_trigger_flows())
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["items"][0]["trigger_id"] == "cycle"
