"""DEX UI routes (Jinja2)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.services.dex import dex_manager_service

# Backward compatibility alias.
dex_trader_service = dex_manager_service
from api.routers.polymarket.ui import get_ui_context

templates = Jinja2Templates(directory="frontend/templates")
router = APIRouter()


@router.get("/ui/dex", response_class=HTMLResponse)
async def ui_dex_dashboard(request: Request):
    context = get_ui_context(request, system_id="dex")
    context["dex_config"] = dex_manager_service.get_config()
    return templates.TemplateResponse("dex_dashboard.html", context)
