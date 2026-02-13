"""Polymarket router package - Trade execution"""
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Query, HTTPException

from api.models.polymarket import (
    CreateLimitOrderRequest,
    CreateMarketOrderRequest,
    TradeProposalRequest,
    TradeExecuteRequest,
)
from api.services.polymarket.logging_service import logging_service
from api.services.polymarket.decision_service import decision_service
from api.services.polymarket.config_service import process_config_service
from core.clients.polymarket_client import PolymarketClient
from core.camel_tools.polymarket_data_toolkit import PolymarketDataToolkit

router = APIRouter()
client = PolymarketClient()
data_toolkit = PolymarketDataToolkit()
data_toolkit.initialize()


def _require_auth() -> None:
    client.refresh_from_env()
    if not client.is_authenticated:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Polymarket client not authenticated. Set POLYGON_PRIVATE_KEY and CLOB credentials.",
                "diagnostics": client.auth_diagnostics(),
            },
        )


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_notional(trade: Dict[str, Any]) -> float:
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


def _trade_side(trade: Dict[str, Any]) -> str:
    return str(trade.get("side") or trade.get("maker_side") or "").upper()


def _summarize_trades(trades: list[Dict[str, Any]]) -> Dict[str, Any]:
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
        side = _trade_side(trade)
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


async def _resolve_token_id(market_id: str, outcome: str) -> str:
    token_ids = await client.get_outcome_token_ids(market_id=market_id)
    if not token_ids:
        raise HTTPException(status_code=404, detail=f"No outcome token IDs found for market {market_id}")
    key = "YES" if outcome.lower() == "yes" else "NO"
    token_id = token_ids.get(key) or token_ids.get(key.lower())
    if not token_id:
        raise HTTPException(status_code=404, detail=f"Token ID for outcome {key} not found")
    return str(token_id)


@router.post("/trades/limit")
async def create_limit_order(order_data: CreateLimitOrderRequest):
    """
    Create a limit order on Polymarket
    
    Args:
        order_data: market_id, side (yes/no), price, shares
    
    Returns:
        Created order details with order ID
    """
    _require_auth()
    token_id = await _resolve_token_id(order_data.market_id, order_data.side.value)
    result = await client.place_order(
        token_id=token_id,
        side="BUY",
        quantity=float(order_data.shares),
        price=float(order_data.price),
    )
    logging_service.log_event("INFO", "Created limit order", result)
    return result


@router.post("/trades/market")
async def create_market_order(order_data: CreateMarketOrderRequest):
    """
    Create a market order (immediate execution) on Polymarket
    
    Args:
        order_data: market_id, side (yes/no), shares
    
    Returns:
        Executed order details with actual price
    """
    _require_auth()
    token_id = await _resolve_token_id(order_data.market_id, order_data.side.value)
    price_payload = await client.get_price(token_id=token_id, side="BUY")
    price = _to_float(price_payload.get("price"), 0.5)
    result = await client.place_order(
        token_id=token_id,
        side="BUY",
        quantity=float(order_data.shares),
        price=price,
    )
    logging_service.log_event("INFO", "Created market order", result)
    return result


@router.get("/trades/history")
async def get_trade_history(limit: int = Query(50, ge=1, le=500)):
    """
    Get trading history
    
    Args:
        limit: Number of recent trades to return
    
    Returns:
        List of past trades with execution details
    """
    _require_auth()
    trades = await client.get_trades()
    return {"trades": trades[:limit], "limit": limit}


@router.delete("/trades/{trade_id}")
async def cancel_trade(trade_id: str):
    """
    Cancel an open trade/order
    
    Args:
        trade_id: Trade/order identifier
    
    Returns:
        Cancelled trade details
    """
    _require_auth()
    result = await client.cancel_order(trade_id)
    return result


@router.post("/trades/batch")
async def batch_orders(batch_request: dict):
    """
    Submit multiple orders in batch
    
    Args:
        batch_request: Dict with 'orders' list
    
    Returns:
        Results for all orders
    """
    _require_auth()
    orders = batch_request.get("orders", [])
    results = []
    for order in orders:
        req = CreateLimitOrderRequest(**order)
        token_id = await _resolve_token_id(req.market_id, req.side.value)
        res = await client.place_order(
            token_id=token_id,
            side="BUY",
            quantity=float(req.shares),
            price=float(req.price),
        )
        results.append(res)
    return {"count": len(results), "results": results}


@router.get("/trades/open")
async def get_open_orders():
    """
    Get all open/pending orders
    
    Returns:
        List of orders awaiting execution or settlement
    """
    _require_auth()
    orders = await client.get_open_orders()
    return {"orders": orders}


@router.post("/trades/propose")
async def propose_trade(payload: TradeProposalRequest):
    if not payload.market_id and not payload.bet_id:
        raise HTTPException(status_code=400, detail="market_id or bet_id required")
    market_id = payload.market_id or payload.bet_id
    market_data = data_toolkit.get_market_data(market_id)
    if market_data.get("status") != "success":
        raise HTTPException(status_code=404, detail=market_data.get("message", "Market not found"))

    mid_price = market_data.get("mid_price") or 0.5
    wallet_balance = payload.wallet_balance or 10000.0
    config = process_config_service.get_workforce_config()
    process_cfg = process_config_service.get_config()
    max_amount = config.trading_controls.max_amount_per_trade
    max_ai_per_trade = process_cfg.get("max_ai_weighted_per_trade", 1.0)
    allowed_value = max_amount * max_ai_per_trade
    quantity = max(1, int(min(wallet_balance, allowed_value) / mid_price))

    token_label = "yes token" if payload.outcome.value.lower() == "yes" else "no token"
    proposal = decision_service.create_proposal({
        "market_id": market_id,
        "bet_id": payload.bet_id or market_id,
        "outcome": payload.outcome.value,
        "token_label": token_label,
        "confidence": payload.confidence,
        "reasoning": payload.reasoning or "",
        "recommended_quantity": quantity,
        "recommended_price": mid_price,
        "estimated_value": quantity * mid_price,
        "status": "ready_to_execute",
    })
    logging_service.log_event("INFO", "Proposed trade", proposal)
    return proposal


@router.post("/trades/execute")
async def execute_trade(payload: TradeExecuteRequest):
    _require_auth()
    if payload.proposal_id:
        proposal = decision_service.get_proposal(payload.proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")
        market_id = proposal["market_id"]
        outcome = proposal.get("outcome", "yes")
        bet_id = proposal.get("bet_id", market_id)
        quantity = proposal["recommended_quantity"]
        price = proposal["recommended_price"]
    else:
        if not payload.market_id and not payload.bet_id:
            raise HTTPException(status_code=400, detail="market_id or bet_id required")
        if not payload.outcome or not payload.quantity:
            raise HTTPException(status_code=400, detail="outcome and quantity required")
        market_id = payload.market_id or payload.bet_id
        bet_id = payload.bet_id or market_id
        outcome = payload.outcome.value
        quantity = payload.quantity
        price = payload.price or (data_toolkit.get_market_data(market_id).get("mid_price") or 0.5)

    process_cfg = process_config_service.get_config()
    max_ai_per_trade = process_cfg.get("max_ai_weighted_per_trade", 1.0)
    max_amount = process_config_service.get_workforce_config().trading_controls.max_amount_per_trade
    trade_value = quantity * price
    if trade_value > max_amount * max_ai_per_trade:
        raise HTTPException(status_code=400, detail="Trade exceeds AI-weighted per-trade limit")

    max_ai_daily = process_cfg.get("max_ai_weighted_daily", 1.0)
    max_daily_value = process_config_service.get_workforce_config().trading_controls.max_exposure_total
    daily_cap = max_daily_value * max_ai_daily
    today = datetime.now(timezone.utc).date().isoformat()
    today_total = 0.0
    historical_trades = await client.get_trades()
    for t in historical_trades:
        try:
            ts = t.get("timestamp", "")
            if ts and ts.split("T")[0] == today:
                today_total += _trade_notional(t)
        except Exception:
            continue
    if today_total + trade_value > daily_cap:
        raise HTTPException(status_code=400, detail="Trade exceeds AI-weighted daily limit")

    token_id = await _resolve_token_id(market_id, outcome)
    order_result = await client.place_order(
        token_id=token_id,
        side="BUY",
        quantity=float(quantity),
        price=float(price),
    )
    response = {
        "success": True,
        "market_id": market_id,
        "bet_id": bet_id,
        "outcome": outcome.lower(),
        "quantity": int(quantity),
        "price": float(price),
        "order": order_result,
    }
    logging_service.log_event("INFO", "Executed trade", response)
    return response


@router.get("/trades")
async def list_trades(
    status: str | None = Query(None),
    asset: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    _require_auth()
    trades = await client.get_trades(market=asset)
    if status:
        status_lower = status.lower()
        trades = [trade for trade in trades if str(trade.get("status", "")).lower() == status_lower]
    paged = trades[:limit]
    return {"trades": paged, "total": len(trades), "limit": limit}


@router.get("/trades/{trade_id}")
async def get_trade_details(trade_id: str):
    _require_auth()
    trade = await client.get_order(trade_id)
    return trade


@router.get("/summary")
async def get_trading_summary():
    _require_auth()
    trades = await client.get_trades()
    return _summarize_trades(trades)
