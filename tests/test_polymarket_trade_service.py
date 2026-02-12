"""
Unit tests for PolymarketTradeService.

Tests cover:
- Trade execution (buy/sell)
- Trade tracking and history
- Order management
- Summary statistics
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from core.services.polymarket_trade_service import (
    PolymarketTradeService,
    TradeStatus,
    TradeType,
    TradeResult
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_toolkit():
    """Create mock trading toolkit."""
    toolkit = AsyncMock()
    toolkit.initialize = AsyncMock()
    toolkit.place_buy_order = AsyncMock(return_value={
        "success": True,
        "order_id": "order_123",
        "market_id": "market_1",
        "side": "BUY",
        "quantity": 10,
        "price": 0.75,
        "total_value": 7.5,
        "status": "pending"
    })
    toolkit.place_sell_order = AsyncMock(return_value={
        "success": True,
        "order_id": "order_124",
        "market_id": "market_1",
        "side": "SELL",
        "quantity": 10,
        "price": 0.75,
        "total_value": 7.5,
        "status": "pending"
    })
    toolkit.cancel_order = AsyncMock(return_value={
        "success": True,
        "status": "cancelled"
    })
    return toolkit


@pytest.fixture
def service(mock_toolkit):
    """Create service with mock toolkit."""
    return PolymarketTradeService(toolkit=mock_toolkit)


# ============================================================================
# TRADE RESULT TESTS
# ============================================================================

def test_trade_result_creation():
    """Test trade result object creation."""
    result = TradeResult(
        trade_id="trade_123",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.PENDING
    )
    
    assert result.trade_id == "trade_123"
    assert result.market_id == "market_1"
    assert result.asset == "BTC"
    assert result.trade_type == TradeType.BUY
    assert result.quantity == 10
    assert result.price == 0.75
    assert result.total_value == 7.5
    assert result.status == TradeStatus.PENDING


def test_trade_result_to_dict():
    """Test trade result conversion to dictionary."""
    result = TradeResult(
        trade_id="trade_123",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.FILLED,
        execution_result={"order_id": "order_123"}
    )
    
    result_dict = result.to_dict()
    
    assert result_dict["trade_id"] == "trade_123"
    assert result_dict["asset"] == "BTC"
    assert result_dict["type"] == "BUY"
    assert result_dict["quantity"] == 10
    assert result_dict["status"] == "filled"
    assert result_dict["total_value"] == 7.5


# ============================================================================
# BUY ORDER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_buy_market_success(service):
    """Test successful buy order execution."""
    result = await service.buy_market(
        market_id="market_1",
        asset="BTC",
        quantity=10,
        price=0.75
    )
    
    assert result["trade_id"] is not None
    assert result["asset"] == "BTC"
    assert result["type"] == "BUY"
    assert result["quantity"] == 10
    assert result["price"] == 0.75
    assert result["status"] == "filled"
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_buy_market_failure(service):
    """Test buy order execution failure."""
    service.toolkit.place_buy_order.return_value = {
        "success": False,
        "error": "Insufficient balance"
    }
    
    result = await service.buy_market(
        market_id="market_1",
        asset="BTC",
        quantity=100,
        price=0.75
    )
    
    assert result["status"] == "rejected"
    assert "insufficient balance" in result["error"].lower()


@pytest.mark.asyncio
async def test_buy_market_exception(service):
    """Test buy order with exception."""
    service.toolkit.place_buy_order.side_effect = Exception("API error")
    
    result = await service.buy_market(
        market_id="market_1",
        asset="BTC",
        quantity=10,
        price=0.75
    )
    
    assert result["status"] == "failed"
    assert "error" in result


# ============================================================================
# SELL ORDER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_sell_market_success(service):
    """Test successful sell order execution."""
    result = await service.sell_market(
        market_id="market_1",
        asset="ETH",
        quantity=20,
        price=0.60
    )
    
    assert result["trade_id"] is not None
    assert result["asset"] == "ETH"
    assert result["type"] == "SELL"
    assert result["quantity"] == 20
    assert result["price"] == 0.60
    assert result["status"] == "filled"


@pytest.mark.asyncio
async def test_sell_market_failure(service):
    """Test sell order execution failure."""
    service.toolkit.place_sell_order.return_value = {
        "success": False,
        "error": "Market closed"
    }
    
    result = await service.sell_market(
        market_id="market_1",
        asset="ETH",
        quantity=20,
        price=0.60
    )
    
    assert result["status"] == "rejected"
    assert "market closed" in result["error"].lower()


@pytest.mark.asyncio
async def test_sell_market_exception(service):
    """Test sell order with exception."""
    service.toolkit.place_sell_order.side_effect = Exception("Connection timeout")
    
    result = await service.sell_market(
        market_id="market_1",
        asset="ETH",
        quantity=20,
        price=0.60
    )
    
    assert result["status"] == "failed"
    assert "error" in result


# ============================================================================
# TRADE TRACKING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_trade():
    """Test retrieving a specific trade."""
    service = PolymarketTradeService()
    
    # Execute a buy order
    result = await service.buy_market(
        market_id="market_1",
        asset="BTC",
        quantity=10,
        price=0.75
    )
    
    trade_id = result["trade_id"]
    
    # Retrieve the trade
    retrieved = service.get_trade(trade_id)
    
    assert retrieved is not None
    assert retrieved["trade_id"] == trade_id
    assert retrieved["asset"] == "BTC"


@pytest.mark.asyncio
async def test_get_trade_not_found():
    """Test retrieving non-existent trade."""
    service = PolymarketTradeService()
    
    result = service.get_trade("nonexistent_id")
    
    assert result is None


@pytest.mark.asyncio
async def test_list_trades():
    """Test listing all trades."""
    service = PolymarketTradeService()
    
    # Execute multiple trades
    for i in range(3):
        await service.buy_market(
            market_id="market_1",
            asset="BTC",
            quantity=10 + i,
            price=0.75
        )
    
    trades = service.list_trades()
    
    assert len(trades) == 3
    assert all(t["type"] == "BUY" for t in trades)


@pytest.mark.asyncio
async def test_list_trades_filter_by_status():
    """Test listing trades filtered by status."""
    service = PolymarketTradeService()
    
    # Add manual trades with different statuses
    service.trade_history["trade_1"] = TradeResult(
        trade_id="trade_1",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.FILLED
    )
    service.trade_history["trade_2"] = TradeResult(
        trade_id="trade_2",
        market_id="market_1",
        asset="ETH",
        trade_type=TradeType.SELL,
        quantity=20,
        price=0.60,
        status=TradeStatus.CANCELLED
    )
    
    filled_trades = service.list_trades(status="filled")
    
    assert len(filled_trades) == 1
    assert filled_trades[0]["status"] == "filled"


@pytest.mark.asyncio
async def test_list_trades_filter_by_asset():
    """Test listing trades filtered by asset."""
    service = PolymarketTradeService()
    
    # Add manual trades with different assets
    service.trade_history["trade_1"] = TradeResult(
        trade_id="trade_1",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.FILLED
    )
    service.trade_history["trade_2"] = TradeResult(
        trade_id="trade_2",
        market_id="market_1",
        asset="ETH",
        trade_type=TradeType.BUY,
        quantity=20,
        price=0.60,
        status=TradeStatus.FILLED
    )
    
    btc_trades = service.list_trades(asset="BTC")
    
    assert len(btc_trades) == 1
    assert btc_trades[0]["asset"] == "BTC"


@pytest.mark.asyncio
async def test_get_pending_trades():
    """Test retrieving pending trades."""
    service = PolymarketTradeService()
    
    # Add pending trade
    pending_trade = TradeResult(
        trade_id="trade_1",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.PENDING
    )
    service.pending_trades["trade_1"] = pending_trade
    
    pending = service.get_pending_trades()
    
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"


# ============================================================================
# ORDER MANAGEMENT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cancel_trade_success(service):
    """Test successful trade cancellation."""
    # Add a pending trade
    pending_trade = TradeResult(
        trade_id="trade_123",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.PENDING,
        execution_result={"order_id": "order_123"}
    )
    service.trade_history["trade_123"] = pending_trade
    
    result = await service.cancel_trade("trade_123")
    
    assert result["success"] is True
    assert result["status"] == "cancelled"
    assert service.trade_history["trade_123"].status == TradeStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_trade_not_found():
    """Test cancelling non-existent trade."""
    service = PolymarketTradeService()
    
    result = await service.cancel_trade("nonexistent_id")
    
    assert result["success"] is False
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_cancel_trade_already_filled():
    """Test cancelling a filled trade."""
    service = PolymarketTradeService()
    
    # Add a filled trade
    filled_trade = TradeResult(
        trade_id="trade_123",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.FILLED
    )
    service.trade_history["trade_123"] = filled_trade
    
    result = await service.cancel_trade("trade_123")
    
    assert result["success"] is False
    assert "cannot cancel" in result["error"].lower()


# ============================================================================
# SUMMARY & STATISTICS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_summary():
    """Test trade summary generation."""
    service = PolymarketTradeService()
    
    # Add manual trades with various statuses and assets
    service.trade_history["trade_1"] = TradeResult(
        trade_id="trade_1",
        market_id="market_1",
        asset="BTC",
        trade_type=TradeType.BUY,
        quantity=10,
        price=0.75,
        status=TradeStatus.FILLED
    )
    service.trade_history["trade_2"] = TradeResult(
        trade_id="trade_2",
        market_id="market_1",
        asset="ETH",
        trade_type=TradeType.SELL,
        quantity=20,
        price=0.60,
        status=TradeStatus.FILLED
    )
    service.trade_history["trade_3"] = TradeResult(
        trade_id="trade_3",
        market_id="market_1",
        asset="SOL",
        trade_type=TradeType.BUY,
        quantity=5,
        price=0.50,
        status=TradeStatus.CANCELLED
    )
    
    summary = service.get_summary()
    
    assert summary["total_trades"] == 3
    assert summary["filled"] == 2
    assert summary["cancelled"] == 1
    assert summary["buy_trades"] == 2
    assert summary["sell_trades"] == 1
    assert summary["total_buy_value"] == 10 * 0.75 + 5 * 0.50
    assert summary["total_sell_value"] == 20 * 0.60
    assert summary["assets"]["BTC"]["count"] == 1
    assert summary["assets"]["ETH"]["count"] == 1


@pytest.mark.asyncio
async def test_get_summary_empty():
    """Test summary with no trades."""
    service = PolymarketTradeService()
    
    summary = service.get_summary()
    
    assert summary["total_trades"] == 0
    assert summary["filled"] == 0
    assert summary["buy_trades"] == 0
    assert summary["sell_trades"] == 0


# ============================================================================
# SERVICE INITIALIZATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_service_initialization():
    """Test service initializes correctly."""
    toolkit = AsyncMock()
    toolkit.initialize = AsyncMock()
    
    service = PolymarketTradeService(toolkit=toolkit)
    await service.initialize()
    
    assert service.toolkit is toolkit
    assert isinstance(service.trade_history, dict)
    assert isinstance(service.pending_trades, dict)


@pytest.mark.asyncio
async def test_full_workflow(mock_toolkit):
    """Test complete workflow: buy, sell, cancel."""
    service = PolymarketTradeService(toolkit=mock_toolkit)
    
    # Buy BTC
    buy_result = await service.buy_market(
        market_id="market_1",
        asset="BTC",
        quantity=10,
        price=0.75
    )
    buy_id = buy_result["trade_id"]
    assert buy_result["status"] == "filled"
    
    # Sell BTC
    sell_result = await service.sell_market(
        market_id="market_1",
        asset="BTC",
        quantity=5,
        price=0.80
    )
    sell_id = sell_result["trade_id"]
    assert sell_result["status"] == "filled"
    
    # Get summary
    summary = service.get_summary()
    assert summary["total_trades"] == 2
    assert summary["buy_trades"] == 1
    assert summary["sell_trades"] == 1
    
    # List trades
    trades = service.list_trades()
    assert len(trades) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
