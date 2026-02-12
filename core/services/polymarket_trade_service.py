"""
Polymarket Trade Execution Service.

Provides:
- Trade execution with proper validation
- Result tracking and persistence
- Order management
- Position monitoring

Used by FastAPI endpoints for REST API.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import uuid4
import logging
import inspect
from enum import Enum

from core.camel_tools.polymarket_trading_mcp import PolymarketTradingToolkit
from core.services.polymarket_token_registry import TokenRegistry
from core.logging import log

logger = logging.getLogger(__name__)


class TradeStatus(str, Enum):
    """Trade execution status."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class TradeType(str, Enum):
    """Trade type."""
    BUY = "BUY"
    SELL = "SELL"


class TradeResult:
    """Result of a single trade execution."""
    
    def __init__(
        self,
        trade_id: str,
        market_id: str,
        asset: str,
        trade_type: TradeType,
        quantity: int,
        price: float,
        status: TradeStatus,
        timestamp: Optional[datetime] = None,
        execution_result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        self.trade_id = trade_id
        self.market_id = market_id
        self.asset = asset
        self.trade_type = trade_type
        self.quantity = quantity
        self.price = price
        self.total_value = quantity * price
        self.status = status
        self.timestamp = timestamp or datetime.utcnow()
        self.execution_result = execution_result or {}
        self.error = error
        self.outcome: Optional[str] = None
        self.token_label: Optional[str] = None
        self.bet_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trade_id": self.trade_id,
            "market_id": self.market_id,
            "bet_id": self.bet_id,
            "asset": self.asset,
            "type": self.trade_type.value,
            "outcome": self.outcome,
            "token_label": self.token_label,
            "quantity": self.quantity,
            "price": self.price,
            "total_value": self.total_value,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "execution_result": self.execution_result
        }


class PolymarketTradeService:
    """Service for executing Polymarket trades with result tracking."""
    
    def __init__(self, toolkit: Optional[PolymarketTradingToolkit] = None):
        """Initialize trade service."""
        self.toolkit = toolkit or PolymarketTradingToolkit()
        self.trade_history: Dict[str, TradeResult] = {}
        self.pending_trades: Dict[str, TradeResult] = {}
        self.token_registry = TokenRegistry()
    
    async def initialize(self) -> None:
        """Initialize the service."""
        await self.toolkit.initialize()
        log.info("PolymarketTradeService initialized")
    
    async def buy_market(
        self,
        market_id: str,
        asset: str,
        quantity: int,
        price: float,
        outcome: str = "YES",
        bet_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a buy order for a Polymarket outcome token (YES/NO).
        
        Args:
            market_id: Polymarket market ID
            asset: Asset name (BTC, ETH, SOL, AAPL, etc.)
            quantity: Number of shares to buy
            price: Limit price
            
        Returns:
            Trade result with trade ID and status
        """
        trade_id = str(uuid4())
        outcome_value = outcome.upper()
        bet_id_value = bet_id or market_id
        trade_result = TradeResult(
            trade_id=trade_id,
            market_id=market_id,
            asset=asset,
            trade_type=TradeType.BUY,
            quantity=quantity,
            price=price,
            status=TradeStatus.PENDING
        )
        trade_result.outcome = outcome_value
        trade_result.token_label = "yes token" if outcome_value == "YES" else "no token"
        trade_result.bet_id = bet_id_value
        self.token_registry.register_trade(trade_id, bet_id_value, outcome_value)
        
        try:
            # Add to pending trades
            self.pending_trades[trade_id] = trade_result

            # Resolve and register token IDs for bet_id mapping
            try:
                token_ids = await self.toolkit.client.get_outcome_token_ids(market_id)
                maybe_register = self.token_registry.register_market(
                    market_id=market_id,
                    bet_id=bet_id_value,
                    yes_token_id=token_ids.get("YES"),
                    no_token_id=token_ids.get("NO"),
                )
                if inspect.isawaitable(maybe_register):
                    await maybe_register
            except Exception:
                pass
            
            # Execute trade via toolkit (BUY YES/NO)
            if outcome_value == "YES":
                execution_result = await self.toolkit.place_buy_order(
                    market_id=market_id,
                    quantity=quantity,
                    price=price
                )
            else:
                execution_result = await self.toolkit.place_sell_order(
                    market_id=market_id,
                    quantity=quantity,
                    price=price
                )
            
            if execution_result.get("success"):
                trade_result.status = TradeStatus.FILLED
                trade_result.execution_result = execution_result
                log.info(f"Trade filled: {trade_id}")
            else:
                trade_result.status = TradeStatus.REJECTED
                trade_result.error = execution_result.get("error", "Unknown error")
                log.warning(f"Trade rejected: {trade_id} - {trade_result.error}")
            
        except Exception as e:
            trade_result.status = TradeStatus.FAILED
            trade_result.error = str(e)
            log.error(f"Trade error: {trade_id} - {e}")
        
        finally:
            # Only move to history once resolved. Keep pending trades pending.
            if trade_result.status == TradeStatus.PENDING:
                self.pending_trades[trade_id] = trade_result
            else:
                if trade_id in self.pending_trades:
                    del self.pending_trades[trade_id]
                self.trade_history[trade_id] = trade_result
        
        return trade_result.to_dict()
    
    async def sell_market(
        self,
        market_id: str,
        asset: str,
        quantity: int,
        price: float,
        bet_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a NO outcome buy (backward-compatible for NO-side requests).
        
        Args:
            market_id: Polymarket market ID
            asset: Asset name (BTC, ETH, SOL, AAPL, etc.)
            quantity: Number of shares to sell
            price: Limit price
            
        Returns:
            Trade result with trade ID and status
        """
        trade_id = str(uuid4())
        bet_id_value = bet_id or market_id
        trade_result = TradeResult(
            trade_id=trade_id,
            market_id=market_id,
            asset=asset,
            trade_type=TradeType.SELL,
            quantity=quantity,
            price=price,
            status=TradeStatus.PENDING
        )
        trade_result.outcome = "NO"
        trade_result.token_label = "no token"
        trade_result.bet_id = bet_id_value
        self.token_registry.register_trade(trade_id, bet_id_value, "NO")
        
        try:
            # Add to pending trades
            self.pending_trades[trade_id] = trade_result

            # Resolve and register token IDs for bet_id mapping
            try:
                token_ids = await self.toolkit.client.get_outcome_token_ids(market_id)
                maybe_register = self.token_registry.register_market(
                    market_id=market_id,
                    bet_id=bet_id_value,
                    yes_token_id=token_ids.get("YES"),
                    no_token_id=token_ids.get("NO"),
                )
                if inspect.isawaitable(maybe_register):
                    await maybe_register
            except Exception:
                pass
            
            # Execute trade via toolkit (BUY NO)
            execution_result = await self.toolkit.place_sell_order(
                market_id=market_id,
                quantity=quantity,
                price=price
            )
            
            if execution_result.get("success"):
                trade_result.status = TradeStatus.FILLED
                trade_result.execution_result = execution_result
                log.info(f"Trade filled: {trade_id}")
            else:
                trade_result.status = TradeStatus.REJECTED
                trade_result.error = execution_result.get("error", "Unknown error")
                log.warning(f"Trade rejected: {trade_id} - {trade_result.error}")
            
        except Exception as e:
            trade_result.status = TradeStatus.FAILED
            trade_result.error = str(e)
            log.error(f"Trade error: {trade_id} - {e}")
        
        finally:
            # Only move to history once resolved. Keep pending trades pending.
            if trade_result.status == TradeStatus.PENDING:
                self.pending_trades[trade_id] = trade_result
            else:
                if trade_id in self.pending_trades:
                    del self.pending_trades[trade_id]
                self.trade_history[trade_id] = trade_result
        
        return trade_result.to_dict()
    
    def get_trade(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get trade result by ID."""
        trade = self.trade_history.get(trade_id)
        if trade:
            return trade.to_dict()
        return None

    def resolve_token_for_trade(self, trade_id: str) -> Optional[str]:
        """Resolve token ID for a trade_id (internal use only)."""
        entry = self.token_registry.resolve_trade(trade_id)
        if not entry:
            return None
        return self.token_registry.resolve_token_id(entry["bet_id"], entry["outcome"])

    def resolve_token_for_bet(self, bet_id: str, outcome: str) -> Optional[str]:
        """Resolve token ID for a bet_id/outcome (internal use only)."""
        return self.token_registry.resolve_token_id(bet_id, outcome)
    
    def list_trades(
        self,
        limit: int = 50,
        status: Optional[str] = None,
        asset: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List trades with optional filtering.
        
        Args:
            limit: Max trades to return
            status: Filter by status (pending, filled, cancelled, etc.)
            asset: Filter by asset (BTC, ETH, AAPL, etc.)
            
        Returns:
            List of trade results
        """
        trades = list(self.trade_history.values())
        
        # Filter by status
        if status:
            trades = [t for t in trades if t.status.value == status]
        
        # Filter by asset
        if asset:
            trades = [t for t in trades if t.asset == asset]
        
        # Sort by timestamp descending (newest first)
        trades.sort(key=lambda t: t.timestamp, reverse=True)
        
        # Apply limit
        trades = trades[:limit]
        
        return [t.to_dict() for t in trades]
    
    def get_pending_trades(self) -> List[Dict[str, Any]]:
        """Get all pending trades."""
        return [t.to_dict() for t in self.pending_trades.values()]
    
    async def cancel_trade(self, trade_id: str) -> Dict[str, Any]:
        """Cancel a pending trade.
        
        Args:
            trade_id: Trade ID to cancel
            
        Returns:
            Cancellation result
        """
        trade = self.pending_trades.get(trade_id) or self.trade_history.get(trade_id)
        if not trade:
            return {"error": f"Trade not found: {trade_id}", "success": False}

        if trade.status != TradeStatus.PENDING:
            return {
                "error": f"Cannot cancel trade in {trade.status.value} status",
                "success": False
            }
        
        try:
            # Try to cancel via toolkit (if we have order ID)
            order_id = trade.execution_result.get("order_id")
            if order_id:
                cancel_result = await self.toolkit.cancel_order(order_id)
                if cancel_result.get("success"):
                    trade.status = TradeStatus.CANCELLED
                    return {"success": True, "trade_id": trade_id, "status": "cancelled"}
            
            # Otherwise just mark as cancelled
            trade.status = TradeStatus.CANCELLED
            if trade_id in self.pending_trades:
                del self.pending_trades[trade_id]
            self.trade_history[trade_id] = trade
            return {"success": True, "trade_id": trade_id, "status": "cancelled"}
            
        except Exception as e:
            log.error(f"Cancel trade error: {e}")
            return {"error": str(e), "success": False}
    
    def get_summary(self) -> Dict[str, Any]:
        """Get trade summary statistics."""
        trades = list(self.trade_history.values())
        
        total_trades = len(trades)
        filled_trades = sum(1 for t in trades if t.status == TradeStatus.FILLED)
        rejected_trades = sum(1 for t in trades if t.status == TradeStatus.REJECTED)
        cancelled_trades = sum(1 for t in trades if t.status == TradeStatus.CANCELLED)
        failed_trades = sum(1 for t in trades if t.status == TradeStatus.FAILED)
        
        buy_trades = sum(1 for t in trades if t.trade_type == TradeType.BUY)
        sell_trades = sum(1 for t in trades if t.trade_type == TradeType.SELL)
        
        total_buy_value = sum(t.total_value for t in trades if t.trade_type == TradeType.BUY)
        total_sell_value = sum(t.total_value for t in trades if t.trade_type == TradeType.SELL)
        
        # Asset distribution
        asset_trades = {}
        for trade in trades:
            asset = trade.asset
            if asset not in asset_trades:
                asset_trades[asset] = {"count": 0, "value": 0}
            asset_trades[asset]["count"] += 1
            asset_trades[asset]["value"] += trade.total_value
        
        return {
            "total_trades": total_trades,
            "filled": filled_trades,
            "rejected": rejected_trades,
            "cancelled": cancelled_trades,
            "failed": failed_trades,
            "pending": len(self.pending_trades),
            "buy_trades": buy_trades,
            "sell_trades": sell_trades,
            "total_buy_value": total_buy_value,
            "total_sell_value": total_sell_value,
            "net_value": total_buy_value - total_sell_value,
            "assets": asset_trades,
            "latest_trades": [t.to_dict() for t in trades[-5:]]
        }
