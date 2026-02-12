"""DEX router: configuration and bot mode."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from api.models.dex import DexConfigResponse, DexConfigUpdateRequest
from api.services.dex import dex_manager_service
from api.system_registry import get_bot_system, list_bot_system_ids, list_bot_systems

router = APIRouter()

# Backward compatibility alias.
dex_trader_service = dex_manager_service


@router.get("/config", response_model=DexConfigResponse)
async def get_config():
    cfg = dex_manager_service.get_config()
    dex_manager_service.log_event("INFO", "DEX config fetched", {})
    return DexConfigResponse(**cfg)


@router.post("/config", response_model=DexConfigResponse)
async def update_config(payload: DexConfigUpdateRequest):
    updated = dex_manager_service.update_config(payload.model_dump(exclude_none=True))
    return DexConfigResponse(**updated)


@router.get("/bot-mode")
async def get_bot_mode():
    cfg = dex_manager_service.get_config()
    active_bot = cfg.get("process", {}).get("active_bot", "dex")
    systems = list_bot_systems()
    selected = get_bot_system(active_bot) or get_bot_system("dex")
    return {
        "status": "ok",
        "active_bot": active_bot,
        "active_ui_path": selected.ui_path if selected else "/ui",
        "available_bots": list_bot_system_ids(),
        "systems": [
            {
                "system_id": system.system_id,
                "label": system.label,
                "ui_path": system.ui_path,
                "description": system.description,
            }
            for system in systems
        ],
    }


@router.post("/bot-mode")
async def set_bot_mode(active_bot: str = Query(...)):
    system = get_bot_system(active_bot)
    if not system:
        raise HTTPException(status_code=400, detail=f"Unknown bot system: {active_bot}")
    cfg = dex_manager_service.update_config({"process": {"active_bot": active_bot}})
    return {
        "status": "ok",
        "active_bot": cfg.get("process", {}).get("active_bot", "dex"),
        "active_ui_path": system.ui_path,
    }


@router.get("/triggers")
async def list_trigger_settings():
    return {
        "status": "ok",
        "count": len(dex_manager_service.list_trigger_specs()),
        "items": dex_manager_service.list_trigger_specs(),
    }


@router.get("/triggers/{trigger_name}")
async def get_trigger_settings(trigger_name: str):
    try:
        item = dex_manager_service.get_trigger_settings(trigger_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown DEX trigger: {trigger_name}") from exc
    return {"status": "ok", "item": item}


@router.patch("/triggers/{trigger_name}")
async def update_trigger_settings(trigger_name: str, payload: dict[str, Any] = Body(default={})):
    try:
        item = dex_manager_service.update_trigger_settings(trigger_name, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown DEX trigger: {trigger_name}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "item": item}
