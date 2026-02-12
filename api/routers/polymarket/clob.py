"""Polymarket CLOB router - native client endpoints."""
from fastapi import APIRouter, Query, HTTPException

from core.clients.polymarket_client import PolymarketClient
from api.services.polymarket.logging_service import logging_service

router = APIRouter()
client = PolymarketClient()


def _require_auth():
    client.refresh_from_env()
    if not client.is_authenticated:
        diag = client.auth_diagnostics()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Polymarket client not authenticated. Set POLYGON_PRIVATE_KEY/PK and CLOB creds.",
                "diagnostics": diag,
            },
        )


@router.get("/clob/readonly-keys")
async def get_readonly_api_keys():
    """List readonly API keys."""
    _require_auth()
    result = await client.get_readonly_api_keys()
    logging_service.log_event("INFO", "Fetched readonly API keys", {})
    return result


@router.get("/clob/orders/open")
async def get_open_orders(
    market: str | None = Query(None),
    maker_address: str | None = Query(None),
):
    """Get open orders with optional filtering."""
    _require_auth()
    orders = await client.get_open_orders(market=market, maker_address=maker_address)
    logging_service.log_event("INFO", "Fetched open orders", {"market": market})
    return {"orders": orders, "count": len(orders)}


@router.get("/clob/orders")
async def get_orders(order_id: str | None = Query(None)):
    """Get all orders or a single order by ID."""
    _require_auth()
    if order_id:
        order = await client.get_order(order_id)
        logging_service.log_event("INFO", "Fetched order", {"order_id": order_id})
        return {"order": order}
    orders = await client.get_orders()
    logging_service.log_event("INFO", "Fetched orders", {"count": len(orders)})
    return {"orders": orders, "count": len(orders)}


@router.get("/clob/trades")
async def get_trades(
    market: str | None = Query(None),
    maker_address: str | None = Query(None),
    taker_address: str | None = Query(None),
):
    """Get trades with optional filtering."""
    _require_auth()
    trades = await client.get_trades(
        market=market,
        maker_address=maker_address,
        taker_address=taker_address,
    )
    logging_service.log_event("INFO", "Fetched trades", {"market": market})
    return {"trades": trades, "count": len(trades)}


@router.get("/clob/price")
async def get_price(
    token_id: str = Query(..., min_length=1),
    side: str = Query("BUY"),
):
    """Get best price for a token and side."""
    _require_auth()
    result = await client.get_price(token_id=token_id, side=side)
    logging_service.log_event("INFO", "Fetched price", {"token_id": token_id, "side": side})
    return result


@router.get("/clob/order-scoring")
async def is_order_scoring(order_id: str = Query(..., min_length=1)):
    """Check if an order is scoring."""
    _require_auth()
    result = await client.is_order_scoring(order_id=order_id)
    logging_service.log_event("INFO", "Checked order scoring", {"order_id": order_id})
    return result
