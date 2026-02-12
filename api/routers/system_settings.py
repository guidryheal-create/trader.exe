"""Generic system settings API.

Provides unified endpoints to fetch and update settings bundles for each bot
system so UI can render dynamic forms without hardcoded routes per system.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from api.models.dex import DexProcessConfigUpdate, DexRuntimeConfigUpdate
from api.models.polymarket import ProcessConfigUpdate
from api.routers.polymarket.rss_flux import ensure_polymarket_manager
from api.services.dex import dex_manager_service
from api.services.polymarket.config_service import process_config_service
from api.system_registry import get_bot_system, list_bot_systems

router = APIRouter()


def _format_system_list() -> list[dict[str, Any]]:
    return [
        {
            "system_id": item.system_id,
            "label": item.label,
            "ui_path": item.ui_path,
            "description": item.description,
        }
        for item in list_bot_systems()
    ]


@router.get("/api/systems/settings")
async def list_system_settings() -> dict[str, Any]:
    return {"status": "ok", "count": len(_format_system_list()), "items": _format_system_list()}


@router.get("/api/systems/{system_id}/settings/bundle")
async def get_system_settings_bundle(system_id: str) -> dict[str, Any]:
    system = get_bot_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown system: {system_id}")

    if system.system_id == "dex":
        cfg = dex_manager_service.get_config()
        task_flows = await dex_manager_service.list_task_flows()
        trigger_specs = dex_manager_service.list_trigger_specs()
        trigger_settings = []
        for spec in trigger_specs:
            name = spec.get("trigger")
            if not name:
                continue
            try:
                trigger_settings.append(dex_manager_service.get_trigger_settings(name))
            except Exception:
                continue
        sections = [
            {
                "id": "process",
                "label": "Process",
                "schema": DexProcessConfigUpdate.model_json_schema(),
                "value": cfg.get("process", {}),
            },
            {
                "id": "runtime",
                "label": "Runtime",
                "schema": DexRuntimeConfigUpdate.model_json_schema(),
                "value": cfg.get("runtime", {}),
            },
        ]
        return {
            "status": "ok",
            "system_id": system.system_id,
            "bundle": {
                "config": cfg,
                "sections": sections,
                "task_flows": task_flows,
                "trigger_specs": trigger_specs,
                "trigger_settings": trigger_settings,
            },
        }

    if system.system_id == "polymarket":
        cfg = process_config_service.get_config()
        try:
            manager = await ensure_polymarket_manager()
            task_flows = manager.list_task_flows()
        except Exception:
            raw = dict(cfg.get("task_flows", {}))
            task_flows = [
                {
                    "task_id": task_id,
                    "pipeline": "polymarket",
                    "system_name": "polymarket_manager",
                    "enabled": bool(enabled),
                }
                for task_id, enabled in raw.items()
            ]
        trigger_specs = process_config_service.list_trigger_specs()
        trigger_settings = []
        for spec in trigger_specs:
            name = spec.get("trigger")
            if not name:
                continue
            try:
                trigger_settings.append(process_config_service.get_trigger_settings(name))
            except Exception:
                continue
        sections = [
            {
                "id": "process",
                "label": "Process",
                "schema": ProcessConfigUpdate.model_json_schema(),
                "value": {
                    "active_flux": cfg.get("active_flux"),
                    "trade_frequency_hours": cfg.get("trade_frequency_hours"),
                    "max_ai_weighted_daily": cfg.get("max_ai_weighted_daily"),
                    "max_ai_weighted_per_trade": cfg.get("max_ai_weighted_per_trade"),
                },
            },
            {
                "id": "trading_controls",
                "label": "Trading Controls",
                "schema": {
                    "type": "object",
                    "properties": {
                        key: {"type": "number" if isinstance(value, (int, float)) else "boolean" if isinstance(value, bool) else "string"}
                        for key, value in dict(cfg.get("trading_controls", {})).items()
                    },
                },
                "value": dict(cfg.get("trading_controls", {})),
            },
            {
                "id": "trigger_config",
                "label": "Trigger Config",
                "schema": {
                    "type": "object",
                    "properties": {
                        key: {"type": "number" if isinstance(value, (int, float)) else "boolean" if isinstance(value, bool) else "string"}
                        for key, value in dict(cfg.get("trigger_config", {})).items()
                    },
                },
                "value": dict(cfg.get("trigger_config", {})),
            },
        ]
        return {
            "status": "ok",
            "system_id": system.system_id,
            "bundle": {
                "config": cfg,
                "sections": sections,
                "task_flows": task_flows,
                "trigger_specs": trigger_specs,
                "trigger_settings": trigger_settings,
            },
        }

    raise HTTPException(status_code=400, detail=f"Unsupported system: {system.system_id}")


@router.patch("/api/systems/{system_id}/settings")
async def patch_system_settings(system_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    system = get_bot_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown system: {system_id}")
    if system.system_id == "dex":
        cfg = dex_manager_service.update_config(payload)
        return {"status": "ok", "system_id": system.system_id, "config": cfg}
    if system.system_id == "polymarket":
        cfg = process_config_service.update_config(payload)
        return {"status": "ok", "system_id": system.system_id, "config": cfg}
    raise HTTPException(status_code=400, detail=f"Unsupported system: {system.system_id}")


@router.patch("/api/systems/{system_id}/task-flows")
async def patch_system_task_flows(system_id: str, payload: dict[str, bool] = Body(default={})) -> dict[str, Any]:
    system = get_bot_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown system: {system_id}")
    if system.system_id == "dex":
        rows = await dex_manager_service.update_task_flows(payload)
        return {"status": "ok", "system_id": system.system_id, "count": len(rows), "items": rows}
    if system.system_id == "polymarket":
        manager = await ensure_polymarket_manager()
        rows = manager.update_task_flows(payload)
        current = process_config_service.get_config()
        merged = dict(current.get("task_flows", {}))
        for key, value in payload.items():
            merged[str(key)] = bool(value)
        process_config_service.update_config({"task_flows": merged})
        return {"status": "ok", "system_id": system.system_id, "count": len(rows), "items": rows}
    raise HTTPException(status_code=400, detail=f"Unsupported system: {system.system_id}")


@router.patch("/api/systems/{system_id}/triggers/{trigger_name}")
async def patch_system_trigger_settings(
    system_id: str,
    trigger_name: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    system = get_bot_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown system: {system_id}")
    if system.system_id == "dex":
        try:
            item = dex_manager_service.update_trigger_settings(trigger_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown DEX trigger: {trigger_name}") from exc
        return {"status": "ok", "system_id": system.system_id, "item": item}
    if system.system_id == "polymarket":
        try:
            item = process_config_service.update_trigger_settings(trigger_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown Polymarket trigger: {trigger_name}") from exc
        return {"status": "ok", "system_id": system.system_id, "item": item}
    raise HTTPException(status_code=400, detail=f"Unsupported system: {system.system_id}")
