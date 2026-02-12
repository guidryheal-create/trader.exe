"""DEX router: logs."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query

from api.services.dex import dex_manager_service

# Backward compatibility alias.
dex_trader_service = dex_manager_service

router = APIRouter()


@router.get("/logs")
async def list_logs(limit: int = Query(100, ge=1, le=1000)):
    events = dex_manager_service.list_logs(limit=limit)
    return {"status": "ok", "count": len(events), "events": events}


@router.post("/logs")
async def add_log(level: str = Query("INFO"), message: str = Query(...), context: str = Query("{}")):
    try:
        parsed_context = json.loads(context)
        if not isinstance(parsed_context, dict):
            parsed_context = {}
    except Exception:
        parsed_context = {}
    return dex_manager_service.log_event(level, message, parsed_context)


@router.delete("/logs")
async def clear_logs():
    dex_manager_service.clear_logs()
    return {"status": "ok", "cleared": True}

