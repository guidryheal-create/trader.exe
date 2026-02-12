"""UI routes for Polymarket dashboard (Jinja2)."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.config import settings
from api.routers.polymarket.clob import client as polymarket_client
from api.services.dex import dex_manager_service
from api.system_registry import list_bot_systems

templates = Jinja2Templates(directory="frontend/templates")
router = APIRouter()


def get_ui_context(request: Request, system_id: str = "polymarket") -> dict:
    """Get base context for all UI routes."""
    is_authenticated = polymarket_client.is_authenticated
    wallet_address = None
    if is_authenticated:
        # The client's get_address() method might exist on the underlying clob_client
        if hasattr(polymarket_client._clob_client, 'get_address'):
            wallet_address = polymarket_client._clob_client.get_address()
        else:
            # Fallback to the address from settings if available
            wallet_address = settings.polygon_address
            
    dex_cfg = dex_manager_service.get_config()
    bot_panels = [
        {
            "system_id": system.system_id,
            "label": system.label,
            "ui_path": system.ui_path,
            "description": system.description,
        }
        for system in list_bot_systems()
    ]

    return {
        "request": request,
        "is_authenticated": is_authenticated,
        "wallet_address": wallet_address,
        "active_bot": dex_cfg.get("process", {}).get("active_bot", "dex"),
        "active_system_id": system_id,
        "bot_panels": bot_panels,
    }


@router.get("/ui/polymarket", response_class=HTMLResponse)
async def ui_home(request: Request):
    context = get_ui_context(request)
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/ui/polymarket/markets", response_class=HTMLResponse)
async def ui_markets(request: Request):
    context = get_ui_context(request)
    return templates.TemplateResponse("markets.html", context)


@router.get("/ui/polymarket/workforce", response_class=HTMLResponse)
async def ui_workforce(request: Request):
    context = get_ui_context(request)
    return templates.TemplateResponse("workforce.html", context)


@router.get("/ui/polymarket/results", response_class=HTMLResponse)
async def ui_results(request: Request):
    context = get_ui_context(request)
    return templates.TemplateResponse("results.html", context)


@router.get("/ui/polymarket/settings", response_class=HTMLResponse)
async def ui_settings(request: Request):
    context = get_ui_context(request)
    return templates.TemplateResponse("settings.html", context)


@router.get("/ui/polymarket/chat", response_class=HTMLResponse)
async def ui_chat(request: Request):
    context = get_ui_context(request)
    return templates.TemplateResponse("chat.html", context)


@router.get("/ui/polymarket/orders", response_class=HTMLResponse)
async def ui_orders(request: Request):
    context = get_ui_context(request)
    return templates.TemplateResponse("orders.html", context)


# Legacy redirects
@router.get("/ui/markets", include_in_schema=False)
async def ui_markets_legacy():
    return RedirectResponse(url="/ui/polymarket/markets", status_code=307)


@router.get("/ui/workforce", include_in_schema=False)
async def ui_workforce_legacy():
    return RedirectResponse(url="/ui/polymarket/workforce", status_code=307)


@router.get("/ui/results", include_in_schema=False)
async def ui_results_legacy():
    return RedirectResponse(url="/ui/polymarket/results", status_code=307)


@router.get("/ui/settings", include_in_schema=False)
async def ui_settings_legacy():
    return RedirectResponse(url="/ui/polymarket/settings", status_code=307)


@router.get("/ui/chat", include_in_schema=False)
async def ui_chat_legacy():
    return RedirectResponse(url="/ui/polymarket/chat", status_code=307)


@router.get("/ui/orders", include_in_schema=False)
async def ui_orders_legacy():
    return RedirectResponse(url="/ui/polymarket/orders", status_code=307)
