"""Polymarket router package - ROI and result analysis."""
from fastapi import APIRouter, Query

from api.models.polymarket import ResultsSummaryResponse, ResultsRecentTradesResponse
from api.services.polymarket.logging_service import logging_service
from core.services.polymarket_trade_service import PolymarketTradeService

router = APIRouter()
trade_service = PolymarketTradeService()


@router.get("/results/summary", response_model=ResultsSummaryResponse)
async def get_results_summary():
    """Get summary of trade results (UI-friendly)."""
    summary = trade_service.get_summary()
    logging_service.log_event("INFO", "Fetched results summary", summary)
    return ResultsSummaryResponse(status="ok", summary=summary)


@router.get("/results/trades", response_model=ResultsRecentTradesResponse)
async def get_recent_trades(limit: int = Query(50, ge=1, le=500)):
    """Get recent trades for UI."""
    trades = trade_service.list_trades(limit=limit)
    payload = {"count": len(trades), "trades": trades, "limit": limit}
    logging_service.log_event("INFO", "Fetched recent trades", {"count": len(trades)})
    return ResultsRecentTradesResponse(status="ok", **payload)
