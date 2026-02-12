"""
Unit tests for PolymarketTradingToolkit.

Tests cover:
- Market discovery (crypto & stock)
- Price data retrieval
- Trade execution (buy/sell orders)
- Position monitoring
- Result tracking

2 unit tests per core function (success + error paths).
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from core.camel_tools.polymarket_trading_mcp import (
    PolymarketTradingToolkit,
    PolymarketTradingResult
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_polymarket_client():
    """Create mock Polymarket client."""
    client = AsyncMock()
    client.is_authenticated = True
    client.search_markets = AsyncMock(return_value=[
        {"id": "market_1", "title": "BTC Price", "liquidity": 100000, "volume_24h": 50000, "mid_price": 0.75},
        {"id": "market_2", "title": "ETH Price", "liquidity": 80000, "volume_24h": 40000, "mid_price": 0.65}
    ])
    client.get_market_details = AsyncMock(return_value={
        "id": "market_1",
        "title": "BTC Price",
        "liquidity": 100000,
        "volume_24h": 50000,
        "mid_price": 0.75
    })
    client.get_orderbook = AsyncMock(return_value={
        "bids": [{"price": 0.74}],
        "asks": [{"price": 0.76}]
    })
    client.place_order = AsyncMock(return_value={
        "order_id": "order_123",
        "status": "pending"
    })
    client.get_orders = AsyncMock(return_value=[
        {"order_id": "order_123", "market_id": "market_1", "side": "BUY", "quantity": 10, "price": 0.75, "status": "pending", "created_at": "2024-01-01T00:00:00"}
    ])
    client.cancel_order = AsyncMock(return_value={"status": "cancelled"})
    return client


@pytest.fixture
def toolkit(mock_polymarket_client):
    """Create toolkit with mock client."""
    return PolymarketTradingToolkit(polymarket_client=mock_polymarket_client)


# ============================================================================
# RESULT TRACKER TESTS
# ============================================================================

def test_result_tracker_add_result():
    """Test result tracker adds results correctly."""
    tracker = PolymarketTradingResult()
    
    tracker.add_result("search_crypto", True, {"found": 5})
    
    assert len(tracker.results) == 1
    result = tracker.results[0]
    assert result["operation"] == "search_crypto"
    assert result["success"] is True
    assert result["data"] == {"found": 5}
    assert "timestamp" in result


def test_result_tracker_get_latest():
    """Test result tracker retrieves latest results."""
    tracker = PolymarketTradingResult()
    
    tracker.add_result("search_crypto", True, {"found": 5})
    tracker.add_result("get_price", True, {"price": 0.75})
    tracker.add_result("trade", True, {"order_id": "123"})
    
    latest = tracker.get_latest(count=2)
    assert len(latest) == 2
    assert latest[-1]["operation"] == "trade"


def test_result_tracker_get_trades():
    """Test result tracker gets only trades."""
    tracker = PolymarketTradingResult()
    
    tracker.add_result("search_crypto", True, {"found": 5})
    tracker.add_result("trade", True, {"order_id": "123"})
    tracker.add_result("get_price", True, {"price": 0.75})
    tracker.add_result("trade", True, {"order_id": "124"})
    
    trades = tracker.get_trades()
    assert len(trades) == 2
    assert all(t["operation"] == "trade" for t in trades)


def test_result_tracker_summary():
    """Test result tracker generates summary."""
    tracker = PolymarketTradingResult()
    
    tracker.add_result("search_crypto", True, {"found": 5})
    tracker.add_result("search_crypto", False, {"error": "timeout"})
    tracker.add_result("trade", True, {"order_id": "123"})
    
    summary = tracker.get_summary()
    assert summary["total_operations"] == 3
    assert summary["successful"] == 2
    assert summary["failed"] == 1
    assert summary["success_rate"] == pytest.approx(2/3)
    assert summary["total_trades"] == 1


# ============================================================================
# MARKET DISCOVERY TESTS (CRYPTO)
# ============================================================================

@pytest.mark.asyncio
async def test_search_crypto_markets_success(toolkit):
    """Test successful crypto market search."""
    result = await toolkit.search_crypto_markets("bitcoin", limit=5)
    
    assert result["success"] is True
    assert result["query"] == "bitcoin"
    assert result["found"] == 2
    assert len(result["markets"]) == 2
    assert result["markets"][0]["title"] == "BTC Price"


@pytest.mark.asyncio
async def test_search_crypto_markets_invalid_query(toolkit):
    """Test crypto market search with invalid query."""
    result = await toolkit.search_crypto_markets("", limit=5)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_search_crypto_markets_invalid_limit(toolkit):
    """Test crypto market search with invalid limit."""
    result = await toolkit.search_crypto_markets("bitcoin", limit=100)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_search_crypto_markets_error_handling(toolkit):
    """Test crypto market search handles client errors."""
    toolkit.client.search_markets.side_effect = Exception("API error")
    
    result = await toolkit.search_crypto_markets("bitcoin", limit=5)
    
    assert result["success"] is False
    assert "error" in result


# ============================================================================
# MARKET DISCOVERY TESTS (STOCK)
# ============================================================================

@pytest.mark.asyncio
async def test_search_stock_markets_success(toolkit):
    """Test successful stock market search."""
    result = await toolkit.search_stock_markets("S&P 500", limit=5)
    
    assert result["success"] is True
    assert result["query"] == "S&P 500"
    assert result["found"] == 2
    assert len(result["markets"]) == 2


@pytest.mark.asyncio
async def test_search_stock_markets_invalid_query(toolkit):
    """Test stock market search with invalid query."""
    result = await toolkit.search_stock_markets("", limit=5)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_search_stock_markets_error_handling(toolkit):
    """Test stock market search handles client errors."""
    toolkit.client.search_markets.side_effect = Exception("API error")
    
    result = await toolkit.search_stock_markets("S&P 500", limit=5)
    
    assert result["success"] is False
    assert "error" in result


# ============================================================================
# PRICE DATA TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_market_price_success(toolkit):
    """Test successful market price retrieval."""
    result = await toolkit.get_market_price("market_1")
    
    assert result["success"] is True
    assert result["market_id"] == "market_1"
    assert result["mid_price"] == 0.75
    assert result["bid"] == 0.74
    assert result["ask"] == 0.76
    assert result["spread"] == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_get_market_price_invalid_market_id(toolkit):
    """Test market price with invalid market ID."""
    result = await toolkit.get_market_price("")
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_get_market_price_error_handling(toolkit):
    """Test market price handles client errors."""
    toolkit.client.get_market_details.side_effect = Exception("API error")
    
    result = await toolkit.get_market_price("market_1")
    
    assert result["success"] is False
    assert "error" in result


# ============================================================================
# TRADE EXECUTION TESTS (BUY ORDERS)
# ============================================================================

@pytest.mark.asyncio
async def test_place_buy_order_success(toolkit):
    """Test successful buy order placement."""
    result = await toolkit.place_buy_order("market_1", quantity=10, price=0.75)
    
    assert result["success"] is True
    assert result["order_id"] == "order_123"
    assert result["market_id"] == "market_1"
    assert result["side"] == "BUY"
    assert result["quantity"] == 10
    assert result["price"] == 0.75
    assert result["total_value"] == 7.5
    assert result["status"] == "pending"
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_place_buy_order_invalid_market_id(toolkit):
    """Test buy order with invalid market ID."""
    result = await toolkit.place_buy_order("", quantity=10, price=0.75)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_place_buy_order_invalid_quantity(toolkit):
    """Test buy order with invalid quantity."""
    result = await toolkit.place_buy_order("market_1", quantity=-5, price=0.75)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_place_buy_order_invalid_price_low(toolkit):
    """Test buy order with price zero."""
    result = await toolkit.place_buy_order("market_1", quantity=10, price=0.0)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_place_buy_order_invalid_price_high(toolkit):
    """Test buy order with price too high."""
    result = await toolkit.place_buy_order("market_1", quantity=10, price=1.5)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_place_buy_order_not_authenticated(toolkit):
    """Test buy order when not authenticated."""
    toolkit.client.is_authenticated = False
    
    result = await toolkit.place_buy_order("market_1", quantity=10, price=0.75)
    
    assert result["success"] is False
    assert "authenticated" in result["error"].lower()


@pytest.mark.asyncio
async def test_place_buy_order_client_error(toolkit):
    """Test buy order handles client errors."""
    toolkit.client.place_order.side_effect = Exception("Order rejected")
    
    result = await toolkit.place_buy_order("market_1", quantity=10, price=0.75)
    
    assert result["success"] is False
    assert "error" in result


# ============================================================================
# TRADE EXECUTION TESTS (SELL ORDERS)
# ============================================================================

@pytest.mark.asyncio
async def test_place_sell_order_success(toolkit):
    """Test successful sell order placement."""
    result = await toolkit.place_sell_order("market_1", quantity=10, price=0.75)
    
    assert result["success"] is True
    assert result["order_id"] == "order_123"
    assert result["market_id"] == "market_1"
    assert result["side"] == "SELL"
    assert result["quantity"] == 10
    assert result["price"] == 0.75
    assert result["total_value"] == 7.5
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_place_sell_order_invalid_quantity(toolkit):
    """Test sell order with invalid quantity."""
    result = await toolkit.place_sell_order("market_1", quantity=0, price=0.75)
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_place_sell_order_not_authenticated(toolkit):
    """Test sell order when not authenticated."""
    toolkit.client.is_authenticated = False
    
    result = await toolkit.place_sell_order("market_1", quantity=10, price=0.75)
    
    assert result["success"] is False
    assert "authenticated" in result["error"].lower()


@pytest.mark.asyncio
async def test_place_sell_order_client_error(toolkit):
    """Test sell order handles client errors."""
    toolkit.client.place_order.side_effect = Exception("Market closed")
    
    result = await toolkit.place_sell_order("market_1", quantity=10, price=0.75)
    
    assert result["success"] is False
    assert "error" in result


# ============================================================================
# ORDER MONITORING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_open_orders_success(toolkit):
    """Test successful retrieval of open orders."""
    result = await toolkit.get_open_orders()
    
    assert result["success"] is True
    assert result["order_count"] == 1
    assert len(result["orders"]) == 1
    assert result["orders"][0]["order_id"] == "order_123"


@pytest.mark.asyncio
async def test_get_open_orders_not_authenticated(toolkit):
    """Test get open orders when not authenticated."""
    toolkit.client.is_authenticated = False
    
    result = await toolkit.get_open_orders()
    
    assert result["success"] is False
    assert "authenticated" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_open_orders_client_error(toolkit):
    """Test get open orders handles client errors."""
    toolkit.client.get_orders.side_effect = Exception("Connection error")
    
    result = await toolkit.get_open_orders()
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_cancel_order_success(toolkit):
    """Test successful order cancellation."""
    result = await toolkit.cancel_order("order_123")
    
    assert result["success"] is True
    assert result["order_id"] == "order_123"
    assert result["status"] == "cancelled"
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_cancel_order_invalid_order_id(toolkit):
    """Test cancel order with invalid order ID."""
    result = await toolkit.cancel_order("")
    
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_cancel_order_not_authenticated(toolkit):
    """Test cancel order when not authenticated."""
    toolkit.client.is_authenticated = False
    
    result = await toolkit.cancel_order("order_123")
    
    assert result["success"] is False
    assert "authenticated" in result["error"].lower()


@pytest.mark.asyncio
async def test_cancel_order_client_error(toolkit):
    """Test cancel order handles client errors."""
    toolkit.client.cancel_order.side_effect = Exception("Order not found")
    
    result = await toolkit.cancel_order("order_123")
    
    assert result["success"] is False
    assert "error" in result


# ============================================================================
# RESULT TRACKING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_trade_results(toolkit):
    """Test retrieving trade results from tracker."""
    # Execute some operations to populate results
    await toolkit.search_crypto_markets("bitcoin")
    await toolkit.place_buy_order("market_1", 10, 0.75)
    await toolkit.get_market_price("market_1")
    
    results = toolkit.get_trade_results(limit=5)
    
    assert results["count"] >= 1
    trades = results["trades"]
    if trades:
        assert all(t["operation"] == "trade" for t in trades)


@pytest.mark.asyncio
async def test_get_operation_results(toolkit):
    """Test retrieving all operation results."""
    await toolkit.search_crypto_markets("bitcoin")
    await toolkit.place_buy_order("market_1", 10, 0.75)
    await toolkit.get_market_price("market_1")
    
    results = toolkit.get_operation_results(limit=10)
    
    assert results["count"] >= 3


@pytest.mark.asyncio
async def test_get_summary(toolkit):
    """Test toolkit summary generation."""
    await toolkit.search_crypto_markets("bitcoin")
    await toolkit.place_buy_order("market_1", 10, 0.75)
    await toolkit.search_stock_markets("S&P")
    
    summary = toolkit.get_summary()
    
    assert "total_operations" in summary
    assert "successful" in summary
    assert "failed" in summary
    assert "success_rate" in summary
    assert "total_trades" in summary


# ============================================================================
# TOOLKIT INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_toolkit_initialization():
    """Test toolkit initializes without errors."""
    with patch("core.camel_tools.polymarket_trading_mcp.PolymarketClient"):
        toolkit = PolymarketTradingToolkit()
        await toolkit.initialize()
        
        assert toolkit._initialized is True


def test_toolkit_get_tools(toolkit):
    """Test toolkit generates CAMEL tools if available."""
    # Just verify the method exists and doesn't crash
    # Tools may be empty if CAMEL not available
    try:
        tools = toolkit.get_tools()
        assert isinstance(tools, list)
    except TypeError:
        # FunctionTool might not be available, that's ok
        pass


@pytest.mark.asyncio
async def test_full_trade_workflow(toolkit):
    """Test complete workflow: search -> get price -> place order."""
    # Search for crypto market
    search_result = await toolkit.search_crypto_markets("bitcoin", limit=5)
    assert search_result["success"] is True
    market_id = search_result["markets"][0]["id"]
    
    # Get market price
    price_result = await toolkit.get_market_price(market_id)
    assert price_result["success"] is True
    
    # Place buy order
    order_result = await toolkit.place_buy_order(market_id, quantity=5, price=price_result["mid_price"])
    assert order_result["success"] is True
    
    # Get open orders
    orders_result = await toolkit.get_open_orders()
    assert orders_result["success"] is True
    assert orders_result["order_count"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
