"""DEX router: monitoring and runtime controls."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.models.dex import DexControlRequest, DexStatusResponse, DexTriggerRequest
from api.services.dex import dex_manager_service

# Backward compatibility alias.
dex_trader_service = dex_manager_service

router = APIRouter()


@router.post("/start")
async def start_trader(payload: DexControlRequest):
    dex_manager_service.log_event(
        "INFO",
        "DEX start requested",
        {"cycle_enabled": payload.cycle_enabled, "watchlist_enabled": payload.watchlist_enabled},
    )
    return await dex_manager_service.start(
        cycle_enabled=payload.cycle_enabled,
        watchlist_enabled=payload.watchlist_enabled,
    )


@router.post("/stop")
async def stop_trader():
    dex_manager_service.log_event("INFO", "DEX stop requested", {})
    return await dex_manager_service.stop()


@router.post("/trigger")
async def trigger_cycle(payload: DexTriggerRequest, wait: bool = Query(default=False)):
    if wait:
        return await dex_manager_service.trigger_cycle_sync(mode=payload.mode, reason=payload.reason)
    return await dex_manager_service.trigger_cycle(mode=payload.mode, reason=payload.reason)


@router.get("/status", response_model=DexStatusResponse)
async def get_status():
    return DexStatusResponse(**(await dex_manager_service.get_status()))


@router.get("/wallet/state")
async def get_wallet_state():
    status = await dex_manager_service.get_status()
    return {
        "status": "ok",
        "wallet_state": status.get("wallet_state", {}),
        "timestamp": status.get("timestamp"),
    }


@router.get("/metrics")
async def get_metrics():
    return {"status": "ok", "metrics": dex_manager_service.get_metrics()}


@router.get("/dashboard")
async def get_dashboard():
    return await dex_manager_service.get_dashboard_snapshot()


@router.get("/workers")
async def get_workers():
    status = await dex_manager_service.get_status()
    dex_manager_service.log_event("INFO", "DEX workers fetched", {"count": len(status.get("workers", []))})
    return {
        "status": "ok",
        "pipeline": status.get("pipeline", "dex"),
        "system_name": status.get("system_name", "dex_manager"),
        "count": len(status.get("workers", [])),
        "items": status.get("workers", []),
        "timestamp": status.get("timestamp"),
    }


@router.get("/task-flows")
async def get_task_flows():
    status = await dex_manager_service.get_status()
    dex_manager_service.log_event("INFO", "DEX monitoring task flows fetched", {"count": len(status.get("task_flows", []))})
    return {
        "status": "ok",
        "pipeline": status.get("pipeline", "dex"),
        "system_name": status.get("system_name", "dex_manager"),
        "count": len(status.get("task_flows", [])),
        "items": status.get("task_flows", []),
        "timestamp": status.get("timestamp"),
    }


@router.get("/trigger-flows")
async def get_trigger_flows():
    status = await dex_manager_service.get_status()
    items = status.get("trigger_flows", [])
    dex_manager_service.log_event("INFO", "DEX trigger flows fetched", {"count": len(items)})
    return {
        "status": "ok",
        "pipeline": status.get("pipeline", "dex"),
        "system_name": status.get("system_name", "dex_manager"),
        "count": len(items),
        "items": items,
        "timestamp": status.get("timestamp"),
    }


@router.get("/executions")
async def list_executions(limit: int = Query(default=50, ge=1, le=500)):
    items = await dex_manager_service.list_executions(limit=limit)
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str):
    item = await dex_manager_service.get_execution(execution_id)
    return {"status": "ok", "item": item}
