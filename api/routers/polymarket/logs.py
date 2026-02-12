"""Polymarket router package - Logging"""
from fastapi import APIRouter, Query

from api.models.polymarket import LogEvent
from api.services.polymarket.logging_service import logging_service

router = APIRouter()


@router.get("/logs")
async def list_logs(limit: int = Query(100, ge=1, le=1000)):
    events = logging_service.list_events(limit=limit)
    return {"events": events, "count": len(events)}


@router.post("/logs")
async def add_log(event: LogEvent):
    return logging_service.log_event(event.level, event.message, event.context)


@router.delete("/logs")
async def clear_logs():
    logging_service.clear()
    return {"cleared": True}
