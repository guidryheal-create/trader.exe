"""DEX router: history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.services.dex import dex_manager_service

# Backward compatibility alias.
dex_trader_service = dex_manager_service

router = APIRouter()


@router.get("/history/trades")
async def list_trades(limit: int = Query(100, ge=1, le=2000)):
    items = dex_manager_service.list_trade_history(limit=limit)
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/history/cycles")
async def list_cycles(limit: int = Query(100, ge=1, le=2000)):
    items = dex_manager_service.list_cycle_history(limit=limit)
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/history/tasks")
async def list_tasks(limit: int = Query(200, ge=1, le=5000)):
    items = dex_manager_service.list_task_history(limit=limit)
    return {"status": "ok", "count": len(items), "items": items}

