"""Main UI menu routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.routers.polymarket.ui import get_ui_context
from api.system_registry import get_bot_system, list_bot_systems

templates = Jinja2Templates(directory="frontend/templates")
router = APIRouter()


@router.get("/ui", response_class=HTMLResponse)
async def ui_menu(request: Request):
    context = get_ui_context(request, system_id="polymarket")
    return templates.TemplateResponse("ui_menu.html", context)


@router.get("/api/systems")
async def api_systems():
    items = [
        {
            "system_id": system.system_id,
            "label": system.label,
            "ui_path": system.ui_path,
            "description": system.description,
        }
        for system in list_bot_systems()
    ]
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/ui/{system_id}/", include_in_schema=False)
async def ui_system_slash(system_id: str):
    system = get_bot_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown UI system: {system_id}")
    return RedirectResponse(url=system.ui_path, status_code=307)


@router.get("/ui/{system_id}/settings", response_class=HTMLResponse)
async def ui_system_settings(request: Request, system_id: str):
    system = get_bot_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown UI system: {system_id}")
    context = get_ui_context(request, system_id=system.system_id)
    return templates.TemplateResponse("settings.html", context)


@router.get("/ui/{system_id}/workforce", response_class=HTMLResponse)
async def ui_system_workforce(request: Request, system_id: str):
    system = get_bot_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown UI system: {system_id}")
    context = get_ui_context(request, system_id=system.system_id)
    return templates.TemplateResponse("workforce.html", context)
