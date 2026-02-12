"""Polymarket router package - Market discovery and search"""
from typing import Any, Dict, List

from fastapi import APIRouter, Query, HTTPException

from api.services.polymarket.market_service import PolymarketService
from core.camel_tools.polymarket_data_toolkit import PolymarketDataToolkit
from api.services.polymarket.logging_service import logging_service

router = APIRouter()
service = PolymarketService()
data_toolkit = PolymarketDataToolkit()
data_toolkit.initialize()


@router.get("/markets/trending")
async def get_trending_markets(hours: int = Query(24, ge=1, le=168)):
    """
    Get trending Polymarket markets
    
    Args:
        hours: Time window in hours (1-168)
    
    Returns:
        List of trending markets with prices and volume
    """
    result = service.get_trending_markets(timeframe=f"{hours}h", limit=10)
    logging_service.log_event("INFO", "Fetched trending markets", {"hours": hours})
    return result


@router.get("/markets/search")
async def search_markets(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False),
    category: str | None = Query(None),
):
    """
    Search Polymarket markets by keyword
    
    Args:
        q: Search query
        limit: Number of results
    
    Returns:
        List of matching markets
    """
    result = service.search_markets(
        query=q,
        limit=limit,
        offset=0,
        active_only=active_only,
        category=category,
    )
    logging_service.log_event(
        "INFO",
        "Searched markets",
        {"query": q, "limit": limit, "category": category},
    )
    return result


@router.post("/markets/{market_id}/analyze")
async def analyze_market(market_id: str):
    """
    Analyze a market for trading opportunity
    
    Args:
        market_id: Polymarket market ID
    
    Returns:
        Analysis results including signals and recommendations
    """
    result = service.calculate_opportunity(market_id=market_id)
    logging_service.log_event("INFO", "Analyzed market", {"market_id": market_id})
    return result


@router.get("/markets/categories")
async def get_market_categories():
    """
    Get available market categories
    
    Returns:
        List of market categories available on Polymarket
    """
    categories = ["crypto", "stock", "politics", "sports", "macro", "other"]
    return {"status": "success", "categories": categories}


@router.get("/markets/closing-soon")
async def get_closing_soon_markets(hours: int = Query(24, ge=1, le=168)):
    """
    Get markets closing soon
    
    Args:
        hours: Show markets closing within this many hours
    
    Returns:
        List of markets closing soon
    """
    # Best-effort: search without query and filter if closing_time present.
    result = service.search_markets(query="market", limit=50, offset=0)
    markets: List[Dict[str, Any]] = result.get("markets", []) if isinstance(result, dict) else []
    closing = []
    for m in markets:
        closing_time = m.get("close_time") or m.get("closing_time") or m.get("end_time")
        if closing_time:
            closing.append(m)
    return {
        "status": "success",
        "hours": hours,
        "count": len(closing),
        "markets": closing,
    }


@router.get("/markets/{market_id}")
async def get_market_details(market_id: str):
    """
    Get detailed information about a specific market
    
    Args:
        market_id: Polymarket market ID
    
    Returns:
        Market details including prices, volume, liquidity
    """
    result = data_toolkit.get_market_data(market_id=market_id)
    if result.get("status") != "success":
        raise HTTPException(status_code=404, detail=result.get("message", "Market not found"))
    logging_service.log_event("INFO", "Fetched market details", {"market_id": market_id})
    return result
