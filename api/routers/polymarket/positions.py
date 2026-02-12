"""Polymarket router package - Position management (native client limited)."""
from fastapi import APIRouter, Path, Query

from api.services.polymarket.logging_service import logging_service
from api.models.polymarket import PositionCreateRequest, PositionUpdateRequest

router = APIRouter()


@router.get("/positions")
async def list_positions(user_address: str = Query(..., min_length=4)):
    """
    List all current positions
    
    Returns:
        List of open positions with P&L
    """
    result = {
        "status": "not_supported",
        "message": "Positions are not available via native client yet.",
        "positions": [],
        "user_address": user_address,
    }
    logging_service.log_event("INFO", "Positions not supported", {"user_address": user_address})
    return result


@router.get("/positions/{position_id}")
async def get_position(position_id: str = Path(...), user_address: str = Query(..., min_length=4)):
    """
    Get details of a specific position
    
    Args:
        position_id: Position identifier
    
    Returns:
        Position details including current P&L and metrics
    """
    return {
        "status": "not_supported",
        "message": "Positions are not available via native client yet.",
        "position_id": position_id,
        "user_address": user_address,
    }


@router.get("/positions/performance")
async def get_positions_performance(user_address: str = Query(..., min_length=4)):
    """
    Get performance metrics for all positions
    
    Returns:
        Performance statistics (ROI, win rate, etc)
    """
    result = {
        "status": "not_supported",
        "message": "Portfolio P&L is not available via native client yet.",
        "user_address": user_address,
    }
    logging_service.log_event("INFO", "Positions P&L not supported", {"user_address": user_address})
    return result


@router.post("/positions")
async def create_position(position_data: PositionCreateRequest):
    """
    Create a new position (paper trading by default)
    
    Args:
        position_data: Market ID, side, shares, entry price
    
    Returns:
        Created position details
    """
    result = {
        "status": "not_supported",
        "message": "Direct position creation is not supported via native client yet.",
        "market_id": position_data.market_id,
        "outcome": position_data.side.value,
    }
    logging_service.log_event("INFO", "Position create not supported", {"market_id": position_data.market_id})
    return result


@router.patch("/positions/{position_id}")
async def update_position(position_id: str = Path(...), update_data: PositionUpdateRequest | None = None):
    """
    Update an existing position (e.g., stop loss)
    
    Args:
        position_id: Position identifier
        update_data: Fields to update
    
    Returns:
        Updated position details
    """
    return {
        "status": "not_supported",
        "position_id": position_id,
        "updated": update_data.dict() if update_data else {},
        "message": "Position update is not supported via native client yet.",
    }


@router.delete("/positions/{position_id}")
async def close_position(position_id: str = Path(...), user_address: str = Query(..., min_length=4), side: str = Query("yes")):
    """
    Close a position (exit trade)
    
    Args:
        position_id: Position identifier
    
    Returns:
        Closed position details with final P&L
    """
    result = {
        "status": "not_supported",
        "message": "Position closure is not supported via native client yet.",
        "position_id": position_id,
        "user_address": user_address,
        "outcome": side,
    }
    logging_service.log_event("INFO", "Position close not supported", {"position_id": position_id})
    return result
