"""Pydantic models for Polymarket trading system"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# Enums
class SideEnum(str, Enum):
    """Trading side"""
    yes = "yes"
    no = "no"


class OrderStatusEnum(str, Enum):
    """Order status"""
    pending = "pending"
    open = "open"
    filled = "filled"
    partially_filled = "partially_filled"
    cancelled = "cancelled"
    failed = "failed"


class DecisionActionEnum(str, Enum):
    """Trading decision action"""
    buy = "buy"
    sell = "sell"
    hold = "hold"
    close = "close"


class StrategyEnum(str, Enum):
    """Allocation strategies"""
    trend_follower = "trend_follower"
    risk_adjusted = "risk_adjusted"
    sentiment = "sentiment"
    wallet_balancing = "wallet_balancing"
    trading = "trading"
    agentic = "agentic"


# Market Models
class MarketPrice(BaseModel):
    """Market price data"""
    yes: float = Field(..., ge=0, le=1)
    no: float = Field(..., ge=0, le=1)
    timestamp: datetime


class Market(BaseModel):
    """Polymarket market"""
    market_id: str
    question: str
    category: str
    volume_24h: float
    liquidity: float
    prices: MarketPrice
    closing_time: Optional[datetime] = None
    created_at: datetime


class MarketSearchResponse(BaseModel):
    """Search results"""
    markets: List[Market]
    total: int
    limit: int


# Position Models
class Position(BaseModel):
    """Trading position"""
    position_id: str
    market_id: str
    side: SideEnum
    shares: float
    entry_price: float
    current_price: float
    entry_time: datetime
    unrealized_pnl: float
    roi_percent: float
    status: str


class PositionList(BaseModel):
    """List of positions"""
    positions: List[Position]
    total_value: float
    total_pnl: float


class PositionCreateRequest(BaseModel):
    """Create a position (paper trading or live)."""
    market_id: str
    side: SideEnum
    size: float = Field(..., gt=0)
    user_address: str


class PositionUpdateRequest(BaseModel):
    """Update position parameters (placeholder)."""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


# Trade Models
class TradeOrder(BaseModel):
    """Trade order"""
    order_id: str
    market_id: str
    side: SideEnum
    price: Optional[float] = None
    shares: float
    order_type: str  # "limit" or "market"
    status: OrderStatusEnum
    created_at: datetime
    executed_at: Optional[datetime] = None
    execution_price: Optional[float] = None


class CreateLimitOrderRequest(BaseModel):
    """Request to create limit order"""
    market_id: str
    side: SideEnum
    price: float = Field(..., gt=0, le=1)
    shares: float = Field(..., gt=0)


class CreateMarketOrderRequest(BaseModel):
    """Request to create market order"""
    market_id: str
    side: SideEnum
    shares: float = Field(..., gt=0)


class TradeHistory(BaseModel):
    """Trade history entry"""
    trades: List[TradeOrder]
    total: int


# Analysis Models
class SignalScore(BaseModel):
    """Signal and confidence score"""
    action: DecisionActionEnum
    confidence: float = Field(..., ge=0, le=1)
    reason: str


class TrendAnalysis(BaseModel):
    """Trend analysis results"""
    ticker: str
    trend: str  # "bullish", "bearish", "neutral"
    strength: float = Field(..., ge=0, le=1)
    signal: SignalScore
    timeframe: str


class SentimentAnalysis(BaseModel):
    """Sentiment analysis results"""
    ticker: str
    sentiment: float = Field(..., ge=-1, le=1)  # -1 to 1 scale
    source: str
    confidence: float = Field(..., ge=0, le=1)
    latest_news: Optional[List[str]] = None


class OpportunityScore(BaseModel):
    """Market opportunity"""
    market_id: str
    question: str
    score: float = Field(..., ge=0, le=1)
    signal: DecisionActionEnum
    confidence: float = Field(..., ge=0, le=1)
    reasoning: str


# Decision Models
class AIDecision(BaseModel):
    """Agentic decision"""
    decision_id: str
    timestamp: datetime
    ticker: Optional[str] = None
    market_id: Optional[str] = None
    action: DecisionActionEnum
    confidence: float = Field(..., ge=0, le=1)
    reasoning: str
    signals_used: List[str]
    recommended_position_size: Optional[float] = None
    execution_id: Optional[str] = None
    execution_status: str = "pending"


class DecisionHistory(BaseModel):
    """Decision history"""
    decisions: List[AIDecision]
    total: int


# Wallet Models
class WalletAllocation(BaseModel):
    """Wallet allocation"""
    asset: str
    percentage: float = Field(..., ge=0, le=100)


class WalletDistribution(BaseModel):
    """Complete wallet distribution"""
    strategy: StrategyEnum
    interval: str  # "daily", "hourly"
    allocations: List[WalletAllocation]
    reserve_pct: float = Field(..., ge=0, le=100)
    total_allocated: float = Field(..., ge=0, le=100)
    timestamp: datetime
    explanation: Optional[str] = None


class RebalanceRecommendation(BaseModel):
    """Rebalancing recommendation"""
    from_allocation: WalletDistribution
    to_allocation: WalletDistribution
    trades_needed: List[Dict[str, Any]]
    estimated_slippage: float


# Chat Models
class ChatMessage(BaseModel):
    """Chat message"""
    role: str  # "user" or "agent"
    content: str
    timestamp: datetime


class ChatRequest(BaseModel):
    """Chat request"""
    message: str
    context: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response"""
    response: str
    analysis: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[str]] = None
    confidence: Optional[float] = None


# Health Models
class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str


# Process Config & Logging Models
class ProcessConfig(BaseModel):
    """Runtime process configuration."""
    active_flux: str = Field(..., description="polymarket_manager (legacy aliases supported)")
    trade_frequency_hours: int = Field(..., ge=1)
    max_ai_weighted_daily: float = Field(..., ge=0)
    max_ai_weighted_per_trade: float = Field(..., ge=0)


class ProcessConfigUpdate(BaseModel):
    """Partial process configuration update."""
    active_flux: Optional[str] = None
    trade_frequency_hours: Optional[int] = Field(None, ge=1)
    max_ai_weighted_daily: Optional[float] = Field(None, ge=0)
    max_ai_weighted_per_trade: Optional[float] = Field(None, ge=0)


class ConfigUpdateRequest(BaseModel):
    """Update runtime process + trading configuration."""
    process: Optional[ProcessConfigUpdate] = None
    trading_controls: Optional[Dict[str, Any]] = None
    trigger_config: Optional[Dict[str, Any]] = None
    agent_weights: Optional[Dict[str, Any]] = None


class ConfigResponse(BaseModel):
    """Full configuration response."""
    active_flux: str
    trade_frequency_hours: int
    max_ai_weighted_daily: float
    max_ai_weighted_per_trade: float
    trading_controls: Dict[str, Any]
    trigger_config: Dict[str, Any]
    agent_weights: Dict[str, Any]
    limits_status: Dict[str, Any]
    last_updated: str


class SettingsUpdateRequest(BaseModel):
    """Update settings for UI/workflow."""
    process: Optional[ProcessConfigUpdate] = None
    trading_controls: Optional[Dict[str, Any]] = None
    trigger_config: Optional[Dict[str, Any]] = None
    agent_weights: Optional[Dict[str, Any]] = None


class SettingsResponse(BaseModel):
    """UI-friendly settings response."""
    status: str
    config: Dict[str, Any]
    ui: Dict[str, Any]
    timestamp: str


class LogEvent(BaseModel):
    """Log event structure."""
    timestamp: str
    level: str
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)


class LogListResponse(BaseModel):
    """List of log events."""
    events: List[LogEvent]
    count: int


class TradeProposalRequest(BaseModel):
    """Proposal request for a trade."""
    market_id: Optional[str] = None
    bet_id: Optional[str] = None
    outcome: SideEnum
    confidence: float = Field(..., ge=0, le=1)
    reasoning: Optional[str] = None
    wallet_balance: Optional[float] = None


class TradeProposalResponse(BaseModel):
    """Trade proposal response."""
    proposal_id: str
    market_id: Optional[str] = None
    bet_id: Optional[str] = None
    outcome: SideEnum
    token_label: Optional[str] = None
    recommended_quantity: int
    recommended_price: float
    estimated_value: float
    confidence: float
    expected_roi: Optional[float] = None
    reasoning: Optional[str] = None
    status: str


class TradeExecuteRequest(BaseModel):
    """Execute a trade or proposal."""
    trade_id: Optional[str] = None
    proposal_id: Optional[str] = None
    market_id: Optional[str] = None
    bet_id: Optional[str] = None
    outcome: Optional[SideEnum] = None
    quantity: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, gt=0, le=1)


class TradeExecuteResponse(BaseModel):
    """Execution result."""
    success: bool
    trade_id: Optional[str] = None
    market_id: Optional[str] = None
    bet_id: Optional[str] = None
    outcome: Optional[SideEnum] = None
    token_label: Optional[str] = None
    quantity: Optional[int] = None
    target_price: Optional[float] = None
    execution_price: Optional[float] = None
    slippage: Optional[float] = None
    status: Optional[str] = None
    execution_mode: Optional[str] = None


class TradeSummaryResponse(BaseModel):
    """Summary of trades."""
    total_trades: int
    filled: int
    rejected: int
    cancelled: int
    failed: int
    pending: int
    buy_trades: int
    sell_trades: int
    total_buy_value: float
    total_sell_value: float
    net_value: float
    assets: Dict[str, Any]


class ResultsSummaryResponse(BaseModel):
    """Results summary for UI."""
    status: str
    summary: Dict[str, Any]


class ResultsRecentTradesResponse(BaseModel):
    """Recent trades response for UI."""
    status: str
    count: int
    trades: List[Dict[str, Any]]
    limit: int


class WorkforceStatusResponse(BaseModel):
    """Workforce status for UI."""
    status: str
    pipeline: Optional[str] = None
    system_name: Optional[str] = None
    active_flux: Optional[str] = None
    trade_frequency_hours: Optional[int] = None
    limits_status: Dict[str, Any]
    trigger_config: Dict[str, Any]
    agent_weights: Dict[str, Any]
    workers: List[Dict[str, Any]] = Field(default_factory=list)
    task_flows: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: Optional[str] = None


class RssCacheResponse(BaseModel):
    """Cached Polymarket feed state for UI."""
    status: str
    updated_at: Optional[str] = None
    count: int
    markets: Dict[str, Any]


class APIStatus(BaseModel):
    """API status"""
    status: str
    endpoint: str
    timestamp: datetime
    implementation_phase: str
