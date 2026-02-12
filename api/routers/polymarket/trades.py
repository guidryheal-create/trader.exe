"""Polymarket router package - Trade execution"""
from typing import Any, Dict, List

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
from core.services.polymarket_trade_service import PolymarketTradeService
from core.camel_tools.polymarket_data_toolkit import PolymarketDataToolkit

router = APIRouter()
trade_service = PolymarketTradeService()
data_toolkit = PolymarketDataToolkit()
data_toolkit.initialize()


@router.post("/trades/limit")
async def create_limit_order(order_data: CreateLimitOrderRequest):
    """
    Create a limit order on Polymarket
    
    Args:
        order_data: market_id, side (yes/no), price, shares
    
    Returns:
        Created order details with order ID
    """
    await trade_service.initialize()
    if order_data.side.value.lower() == "yes":
        result = await trade_service.buy_market(
            market_id=order_data.market_id,
            asset="UNKNOWN",
            quantity=int(order_data.shares),
            price=order_data.price,
            outcome="YES",
            bet_id=order_data.market_id,
        )
    else:
        result = await trade_service.sell_market(
            market_id=order_data.market_id,
            asset="UNKNOWN",
            quantity=int(order_data.shares),
            price=order_data.price,
            bet_id=order_data.market_id,
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
    await trade_service.initialize()
    market_data = data_toolkit.get_market_data(order_data.market_id)
    price = market_data.get("mid_price") or 0.5
    if order_data.side.value.lower() == "yes":
        result = await trade_service.buy_market(
            market_id=order_data.market_id,
            asset="UNKNOWN",
            quantity=int(order_data.shares),
            price=price,
            outcome="YES",
            bet_id=order_data.market_id,
        )
    else:
        result = await trade_service.sell_market(
            market_id=order_data.market_id,
            asset="UNKNOWN",
            quantity=int(order_data.shares),
            price=price,
            bet_id=order_data.market_id,
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
    return {"trades": trade_service.list_trades(limit=limit), "limit": limit}


@router.delete("/trades/{trade_id}")
async def cancel_trade(trade_id: str):
    """
    Cancel an open trade/order
    
    Args:
        trade_id: Trade/order identifier
    
    Returns:
        Cancelled trade details
    """
    result = await trade_service.cancel_trade(trade_id)
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
    orders = batch_request.get("orders", [])
    results = []
    for order in orders:
        req = CreateLimitOrderRequest(**order)
        if req.side.value.lower() == "yes":
            res = await trade_service.buy_market(req.market_id, "UNKNOWN", int(req.shares), req.price)
        else:
            res = await trade_service.sell_market(req.market_id, "UNKNOWN", int(req.shares), req.price)
        results.append(res)
    return {"count": len(results), "results": results}


@router.get("/trades/open")
async def get_open_orders():
    """
    Get all open/pending orders
    
    Returns:
        List of orders awaiting execution or settlement
    """
    return {"orders": trade_service.get_pending_trades()}


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
    await trade_service.initialize()
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
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    today_total = 0.0
    for t in trade_service.list_trades(limit=500):
        try:
            ts = t.get("timestamp", "")
            if ts and ts.split("T")[0] == today:
                today_total += t.get("total_value", 0.0)
        except Exception:
            continue
    if today_total + trade_value > daily_cap:
        raise HTTPException(status_code=400, detail="Trade exceeds AI-weighted daily limit")

    if outcome.lower() == "yes":
        result = await trade_service.buy_market(
            market_id, "UNKNOWN", quantity, price, outcome="YES", bet_id=bet_id
        )
    else:
        result = await trade_service.sell_market(
            market_id, "UNKNOWN", quantity, price, bet_id=bet_id
        )
    logging_service.log_event("INFO", "Executed trade", result)
    return result


@router.get("/trades")
async def list_trades(
    status: str | None = Query(None),
    asset: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    return {
        "trades": trade_service.list_trades(limit=limit, status=status, asset=asset),
        "total": len(trade_service.list_trades(limit=limit, status=status, asset=asset)),
        "limit": limit,
    }


@router.get("/trades/{trade_id}")
async def get_trade_details(trade_id: str):
    trade = trade_service.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.get("/summary")
async def get_trading_summary():
    return trade_service.get_summary()
