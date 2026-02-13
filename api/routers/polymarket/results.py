"""Polymarket router package - ROI and result analysis."""
from fastapi import APIRouter, Query

from api.models.polymarket import ResultsSummaryResponse, ResultsRecentTradesResponse
from api.services.polymarket.logging_service import logging_service
from core.clients.polymarket_client import PolymarketClient

router = APIRouter()
client = PolymarketClient()


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_notional(trade: dict) -> float:
    if "total_value" in trade:
        return _to_float(trade.get("total_value"), 0.0)
    price = _to_float(trade.get("price") or trade.get("execution_price"), 0.0)
    size = _to_float(
        trade.get("size")
        or trade.get("quantity")
        or trade.get("amount")
        or trade.get("shares"),
        0.0,
    )
    return price * size


def _summarize_trades(trades: list[dict]) -> dict:
    summary = {
        "total_trades": len(trades),
        "filled": 0,
        "rejected": 0,
        "cancelled": 0,
        "failed": 0,
        "pending": 0,
        "buy_trades": 0,
        "sell_trades": 0,
        "total_buy_value": 0.0,
        "total_sell_value": 0.0,
        "net_value": 0.0,
        "assets": {},
    }
    for trade in trades:
        status = str(trade.get("status") or trade.get("state") or "filled").lower()
        if status in summary:
            summary[status] += 1
        side = str(trade.get("side") or trade.get("maker_side") or "").upper()
        notional = _trade_notional(trade)
        market_key = str(trade.get("market") or trade.get("market_id") or "unknown")
        asset_bucket = summary["assets"].setdefault(
            market_key,
            {"count": 0, "buy_value": 0.0, "sell_value": 0.0},
        )
        asset_bucket["count"] += 1
        if side == "BUY":
            summary["buy_trades"] += 1
            summary["total_buy_value"] += notional
            asset_bucket["buy_value"] += notional
        elif side == "SELL":
            summary["sell_trades"] += 1
            summary["total_sell_value"] += notional
            asset_bucket["sell_value"] += notional
    summary["net_value"] = summary["total_sell_value"] - summary["total_buy_value"]
    summary["total_buy_value"] = round(summary["total_buy_value"], 6)
    summary["total_sell_value"] = round(summary["total_sell_value"], 6)
    summary["net_value"] = round(summary["net_value"], 6)
    return summary


@router.get("/results/summary", response_model=ResultsSummaryResponse)
async def get_results_summary():
    """Get summary of trade results (UI-friendly)."""
    client.refresh_from_env()
    if client.is_authenticated:
        trades = await client.get_trades()
        summary = _summarize_trades(trades)
    else:
        summary = {
            "total_trades": 0,
            "filled": 0,
            "rejected": 0,
            "cancelled": 0,
            "failed": 0,
            "pending": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "total_buy_value": 0.0,
            "total_sell_value": 0.0,
            "net_value": 0.0,
            "assets": {},
            "auth_required": True,
            "diagnostics": client.auth_diagnostics(),
        }
    logging_service.log_event("INFO", "Fetched results summary", summary)
    return ResultsSummaryResponse(status="ok", summary=summary)


@router.get("/results/trades", response_model=ResultsRecentTradesResponse)
async def get_recent_trades(limit: int = Query(50, ge=1, le=500)):
    """Get recent trades for UI."""
    client.refresh_from_env()
    if client.is_authenticated:
        trades = (await client.get_trades())[:limit]
    else:
        trades = []
    payload = {"count": len(trades), "trades": trades, "limit": limit}
    logging_service.log_event("INFO", "Fetched recent trades", {"count": len(trades)})
    return ResultsRecentTradesResponse(status="ok", **payload)
