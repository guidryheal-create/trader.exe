"""DEX router: UI settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.models.dex import DexConfigUpdateRequest
from api.services.dex import dex_manager_service
from api.system_registry import list_bot_system_ids

router = APIRouter()

# Backward compatibility alias.
dex_trader_service = dex_manager_service


@router.get("/settings")
async def get_settings():
    cfg = dex_manager_service.get_config()
    task_flows = await dex_manager_service.list_task_flows()
    dex_manager_service.log_event("INFO", "DEX settings fetched", {"task_flow_count": len(task_flows)})
    return {
        "status": "ok",
        "pipeline": "dex",
        "system_name": "dex_manager",
        "config": cfg,
        "triggers": dex_manager_service.list_trigger_specs(),
        "task_flows": task_flows,
        "ui": {
            "bot_panels": list_bot_system_ids(),
            "active_bot": cfg.get("process", {}).get("active_bot", "dex"),
            "features": [
                "wallet_state",
                "trade_history",
                "cycle_history",
                "task_state",
                "watchlist_trigger",
                "runtime_controls",
            ],
        },
        "timestamp": cfg.get("last_updated"),
    }


@router.post("/settings")
async def update_settings(payload: DexConfigUpdateRequest):
    updated = dex_manager_service.update_config(payload.model_dump(exclude_none=True))
    task_flows = await dex_manager_service.list_task_flows()
    dex_manager_service.log_event("INFO", "DEX settings updated", {"task_flow_count": len(task_flows)})
    return {
        "status": "ok",
        "pipeline": "dex",
        "system_name": "dex_manager",
        "config": updated,
        "triggers": dex_manager_service.list_trigger_specs(),
        "task_flows": task_flows,
        "timestamp": updated.get("last_updated"),
    }


@router.get("/settings/task-flows")
async def get_task_flows():
    flows = await dex_manager_service.list_task_flows()
    dex_manager_service.log_event("INFO", "DEX task flows fetched", {"count": len(flows)})
    return {
        "status": "ok",
        "pipeline": "dex",
        "system_name": "dex_manager",
        "count": len(flows),
        "items": flows,
    }


@router.patch("/settings/task-flows")
async def update_task_flows(payload: dict[str, bool]):
    flows = await dex_manager_service.update_task_flows(payload)
    dex_manager_service.log_event("INFO", "DEX task flows updated", {"count": len(flows), "payload": payload})
    return {
        "status": "ok",
        "pipeline": "dex",
        "system_name": "dex_manager",
        "count": len(flows),
        "items": flows,
    }
