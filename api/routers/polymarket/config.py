"""Polymarket router package - Process configuration"""
from fastapi import APIRouter

from api.models.polymarket import ConfigUpdateRequest
from api.services.polymarket.config_service import process_config_service
from api.services.polymarket.logging_service import logging_service

router = APIRouter()


@router.get("/config")
async def get_config():
    """Get current runtime configuration."""
    return process_config_service.get_config()


@router.post("/config")
async def update_config(payload: ConfigUpdateRequest):
    """Update runtime configuration and trading controls."""
    updated = process_config_service.update_config(payload.model_dump(exclude_none=True))
    logging_service.log_event("INFO", "Updated config", updated)
    return updated
