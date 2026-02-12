"""Polymarket router package - Settings for UI and workflow."""
from typing import Any

from fastapi import APIRouter
from fastapi import Body, HTTPException

from api.models.polymarket import SettingsResponse, SettingsUpdateRequest
from api.services.polymarket.config_service import process_config_service
from api.services.polymarket.logging_service import logging_service

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get UI-friendly settings and workflow configuration."""
    config = process_config_service.get_config()
    task_flows = dict(config.get("task_flows", {}))
    try:
        from api.routers.polymarket.rss_flux import ensure_polymarket_manager

        flux = await ensure_polymarket_manager()
        task_flow_rows = flux.list_task_flows()
    except Exception:
        task_flow_rows = [
            {
                "task_id": task_id,
                "pipeline": "polymarket",
                "system_name": "polymarket_manager",
                "enabled": bool(enabled),
            }
            for task_id, enabled in task_flows.items()
        ]
    response = SettingsResponse(
        status="ok",
        config={
            **config,
            "pipeline": "polymarket",
            "system_name": "polymarket_manager",
            "triggers": process_config_service.list_trigger_specs(),
            "task_flows": task_flow_rows,
        },
        ui={
            "polymarket_only": True,
            "uses_env_defaults": True,
            "manager_trigger_types": ["manual", "interval"],
            "manager_default_interval_hours": config.get("trigger_config", {}).get("interval_hours", 4),
            "flux_trigger_types": ["manual", "interval"],
            "flux_default_interval_hours": config.get("trigger_config", {}).get("interval_hours", 4),
            "features": [
                "market_search",
                "market_details",
                "trade_propose_execute",
                "decision_history",
                "logs",
                "results_summary",
            ],
            "deprecated": [],
        },
        timestamp=config.get("last_updated", ""),
    )
    return response


@router.post("/settings", response_model=SettingsResponse)
async def update_settings(payload: SettingsUpdateRequest):
    """Update workflow settings for UI and trading controls."""
    updated = process_config_service.update_config(payload.model_dump(exclude_none=True))
    logging_service.log_event("INFO", "Updated settings", updated)
    task_flows = dict(updated.get("task_flows", {}))
    try:
        from api.routers.polymarket.rss_flux import ensure_polymarket_manager

        flux = await ensure_polymarket_manager()
        task_flow_rows = flux.update_task_flows({str(k): bool(v) for k, v in task_flows.items()})
    except Exception:
        task_flow_rows = [
            {
                "task_id": task_id,
                "pipeline": "polymarket",
                "system_name": "polymarket_manager",
                "enabled": bool(enabled),
            }
            for task_id, enabled in task_flows.items()
        ]
    response = SettingsResponse(
        status="ok",
        config={
            **updated,
            "pipeline": "polymarket",
            "system_name": "polymarket_manager",
            "triggers": process_config_service.list_trigger_specs(),
            "task_flows": task_flow_rows,
        },
        ui={
            "polymarket_only": True,
            "features": [
                "market_search",
                "market_details",
                "trade_propose_execute",
                "decision_history",
                "logs",
                "results_summary",
            ],
            "deprecated": [],
        },
        timestamp=updated.get("last_updated", ""),
    )
    return response


@router.get("/settings/triggers")
async def list_trigger_settings():
    items = process_config_service.list_trigger_specs()
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/settings/triggers/{trigger_name}")
async def get_trigger_settings(trigger_name: str):
    try:
        item = process_config_service.get_trigger_settings(trigger_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown Polymarket trigger: {trigger_name}") from exc
    return {"status": "ok", "item": item}


@router.patch("/settings/triggers/{trigger_name}")
async def update_trigger_settings(trigger_name: str, payload: dict[str, Any] = Body(default={})):
    try:
        item = process_config_service.update_trigger_settings(trigger_name, payload)
        logging_service.log_event("INFO", "Updated trigger settings", {"trigger": trigger_name, "settings": item.get("settings", {})})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown Polymarket trigger: {trigger_name}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "item": item}


@router.get("/settings/task-flows")
async def get_task_flows():
    config = process_config_service.get_config()
    task_flows = dict(config.get("task_flows", {}))
    try:
        from api.routers.polymarket.rss_flux import ensure_polymarket_manager

        flux = await ensure_polymarket_manager()
        rows = flux.list_task_flows()
    except Exception:
        rows = [
            {
                "task_id": task_id,
                "pipeline": "polymarket",
                "system_name": "polymarket_manager",
                "enabled": bool(enabled),
            }
            for task_id, enabled in task_flows.items()
        ]
    payload = {
        "status": "ok",
        "pipeline": "polymarket",
        "system_name": "polymarket_manager",
        "count": len(rows),
        "items": rows,
    }
    logging_service.log_event("INFO", "Polymarket task flows fetched", {"count": len(rows)})
    return payload


@router.patch("/settings/task-flows")
async def update_task_flows(payload: dict[str, bool] = Body(default={})):
    current = process_config_service.get_config()
    merged = dict(current.get("task_flows", {}))
    for task_id, enabled in payload.items():
        merged[str(task_id)] = bool(enabled)
    process_config_service.update_config({"task_flows": merged})
    try:
        from api.routers.polymarket.rss_flux import ensure_polymarket_manager

        flux = await ensure_polymarket_manager()
        rows = flux.update_task_flows({str(k): bool(v) for k, v in merged.items()})
    except Exception:
        rows = [
            {
                "task_id": task_id,
                "pipeline": "polymarket",
                "system_name": "polymarket_manager",
                "enabled": bool(enabled),
            }
            for task_id, enabled in merged.items()
        ]
    response = {
        "status": "ok",
        "pipeline": "polymarket",
        "system_name": "polymarket_manager",
        "count": len(rows),
        "items": rows,
    }
    logging_service.log_event("INFO", "Polymarket task flows updated", {"count": len(rows), "payload": payload})
    return response
