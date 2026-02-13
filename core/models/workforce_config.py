"""
Workforce Configuration Service for Polymarket Trading.

Manages:
- Trading limits (max trades/day, amount per trade, exposure)
- Market filters (asset whitelist, liquidity minimum, etc.)
- Workforce triggers (interval-based, signal-based, market-based)
- Agent weights in decision making
- Trade validation and enforcement

Used by PolymarketWorkforceManager to enforce policies.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from core.logging import log

logger = logging.getLogger(__name__)


@dataclass
class TradingControls:
    """Trading limits and constraints."""
    
    # Trade Limits
    max_trades_per_day: int = 10
    max_amount_per_trade: float = 500.0  # USD
    max_exposure_total: float = 5000.0   # USD total open
    max_spread_tolerance: float = 0.05   # 5% max spread
    
    # Market Filters
    min_liquidity: float = 10000.0        # USD
    min_volume_24h: float = 5000.0        # USD
    min_market_age_hours: int = 24        # Don't trade brand new markets
    
    # Probability Filters
    min_probability: float = 0.55
    max_probability: float = 0.95
    
    # Asset & Category Filters
    asset_whitelist: List[str] = field(default_factory=lambda: [
        "BTC", "ETH", "SOL", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"
    ])
    asset_blacklist: List[str] = field(default_factory=list)
    
    category_whitelist: List[str] = field(default_factory=lambda: [
        "crypto", "stock"
    ])
    category_blacklist: List[str] = field(default_factory=lambda: [
        "politics"
    ])
    
    # Execution Mode
    real_mode: bool = False  # False = DEMO_MODE mock trading
    
    @classmethod
    def from_env(cls) -> "TradingControls":
        """Load from environment variables."""
        import os
        
        return cls(
            max_trades_per_day=int(os.getenv("TRADING_MAX_TRADES_PER_DAY", "10")),
            max_amount_per_trade=float(os.getenv("TRADING_MAX_AMOUNT_PER_TRADE", "500")),
            max_exposure_total=float(os.getenv("TRADING_MAX_EXPOSURE_TOTAL", "5000")),
            min_probability=float(os.getenv("TRADING_MIN_PROBABILITY", "0.55")),
            real_mode=os.getenv("EXECUTION_MODE", "mock").lower() == "real"
        )
    
    def validate(self) -> Tuple[bool, str]:
        """Validate configuration consistency."""
        if self.max_amount_per_trade > self.max_exposure_total:
            return False, "max_amount_per_trade cannot exceed max_exposure_total"
        
        if self.min_probability >= self.max_probability:
            return False, "min_probability must be < max_probability"
        
        if self.max_spread_tolerance < 0 or self.max_spread_tolerance > 1:
            return False, "max_spread_tolerance must be between 0 and 1"
        
        return True, "Configuration valid"


@dataclass
class WorkforceTriggerConfig:
    """Configure workflow trigger conditions."""
    
    # Trigger Type: "interval", "signal", "market", "hybrid"
    trigger_type: str = "hybrid"
    
    # Interval-based (run every N hours)
    interval_hours: int = 4
    
    # Signal-based (trigger on high-confidence signals)
    signal_threshold_confidence: float = 0.75
    min_signals_required: int = 2
    
    # Market-based (trigger if N new markets appear)
    new_markets_threshold: int = 5
    
    # Hybrid mode: "OR" = any condition, "AND" = all conditions
    hybrid_mode: str = "OR"
    
    @classmethod
    def from_env(cls) -> "WorkforceTriggerConfig":
        """Load from environment variables."""
        import os
        
        return cls(
            trigger_type=os.getenv("WORKFORCE_TRIGGER_TYPE", "hybrid"),
            interval_hours=int(os.getenv("WORKFORCE_TRIGGER_INTERVAL_HOURS", "4")),
            signal_threshold_confidence=float(os.getenv("WORKFORCE_SIGNAL_THRESHOLD", "0.75")),
            min_signals_required=int(os.getenv("WORKFORCE_MIN_SIGNALS", "2")),
            new_markets_threshold=int(os.getenv("WORKFORCE_NEW_MARKETS_THRESHOLD", "5")),
            hybrid_mode=os.getenv("WORKFORCE_HYBRID_MODE", "OR")
        )
    
    def validate(self) -> Tuple[bool, str]:
        """Validate configuration."""
        valid_types = ["interval", "signal", "market", "hybrid"]
        if self.trigger_type not in valid_types:
            return False, f"trigger_type must be one of {valid_types}"
        
        if self.interval_hours < 1:
            return False, "interval_hours must be >= 1"
        
        if not (0 <= self.signal_threshold_confidence <= 1):
            return False, "signal_threshold_confidence must be 0-1"
        
        return True, "Configuration valid"


@dataclass
class AgentWeightConfig:
    """Configure agent influence on decisions."""
    
    # Decision weights (should sum to 1.0)
    agent_weight: float = 0.60             # Agent reasoning
    signal_weight: float = 0.30            # RSS signals
    market_data_weight: float = 0.10       # Raw market data
    
    # Per-agent risk limits
    per_agent_max_exposure: float = 2000.0  # Each agent max $2k
    per_agent_max_trades: int = 5           # Each agent max 5 trades
    
    # Strategy per agent
    agent_strategies: Dict[str, str] = field(default_factory=lambda: {
        "market_scanner": "aggressive",
        "risk_manager": "conservative",
        "trend_follower": "momentum"
    })
    
    @classmethod
    def from_env(cls) -> "AgentWeightConfig":
        """Load from environment variables."""
        import os
        
        agent_weight = float(os.getenv("AGENT_WEIGHT", "0.60"))
        signal_weight = float(os.getenv("SIGNAL_WEIGHT", "0.30"))
        market_data_weight = float(os.getenv("MARKET_DATA_WEIGHT", "0.10"))
        
        return cls(
            agent_weight=agent_weight,
            signal_weight=signal_weight,
            market_data_weight=market_data_weight,
            per_agent_max_exposure=float(os.getenv("PER_AGENT_MAX_EXPOSURE", "2000")),
            per_agent_max_trades=int(os.getenv("PER_AGENT_MAX_TRADES", "5"))
        )
    
    def validate(self) -> Tuple[bool, str]:
        """Validate weight configuration."""
        # Check for negative weights
        if any(w < 0 for w in [self.agent_weight, self.signal_weight, self.market_data_weight]):
            return False, "All weights must be >= 0"
        
        total_weight = self.agent_weight + self.signal_weight + self.market_data_weight
        
        # Allow small floating point error
        if abs(total_weight - 1.0) > 0.01:
            return False, f"Weights must sum to 1.0, got {total_weight}"
        
        return True, "Configuration valid"


class WorkforceConfigService:
    """Service for managing workforce configuration and validation."""
    
    def __init__(self):
        """Initialize configuration service."""
        self.trading_controls = TradingControls.from_env()
        self.trigger_config = WorkforceTriggerConfig.from_env()
        self.agent_weights = AgentWeightConfig.from_env()
        
        # Trade tracking
        self.trades_today: List[Dict[str, Any]] = []
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        
        # Validation
        self._validate_all()
    
    def _validate_all(self) -> None:
        """Validate all configurations on initialization."""
        configs = [
            ("Trading Controls", self.trading_controls),
            ("Trigger Config", self.trigger_config),
            ("Agent Weights", self.agent_weights)
        ]
        
        for name, config in configs:
            valid, message = config.validate()
            if not valid:
                raise ValueError(f"{name} validation failed: {message}")
            log.info(f"✓ {name} validated: {message}")
    
    # =========================================================================
    # TRADE VALIDATION & LIMITS
    # =========================================================================
    def should_allow_trade(
        self,
        market_data: Dict[str, Any],
        quantity: int,
        price: float
    ) -> Tuple[bool, str]:
        """Check if trade passes all validation filters.
        
        Returns:
            (allowed: bool, reason: str)
        """
        
        # 1. Check execution mode
        if self.trading_controls.real_mode:
            log.warning("Real trading mode enabled - proceed with caution")
        
        # 2. Check trade count limit
        trades_today = self._get_trades_today()
        if len(trades_today) >= self.trading_controls.max_trades_per_day:
            return False, f"Max trades per day ({self.trading_controls.max_trades_per_day}) reached"
        
        # 3. Check amount limit
        trade_value = quantity * price
        if trade_value > self.trading_controls.max_amount_per_trade:
            return False, f"Trade value ${trade_value:.2f} exceeds max ${self.trading_controls.max_amount_per_trade:.2f}"
        
        # 4. Check total exposure limit
        current_exposure = self._get_current_exposure()
        if current_exposure + trade_value > self.trading_controls.max_exposure_total:
            return False, f"Exposure ${current_exposure + trade_value:.2f} would exceed max ${self.trading_controls.max_exposure_total:.2f}"
        
        # 5. Check market liquidity
        market_liquidity = market_data.get("liquidity", 0)
        if market_liquidity < self.trading_controls.min_liquidity:
            return False, f"Market liquidity ${market_liquidity:.2f} below minimum ${self.trading_controls.min_liquidity:.2f}"
        
        # 6. Check market volume
        market_volume = market_data.get("volume_24h", 0)
        if market_volume < self.trading_controls.min_volume_24h:
            return False, f"Market volume ${market_volume:.2f} below minimum ${self.trading_controls.min_volume_24h:.2f}"
        
        # 7. Check market age
        if "created_at" in market_data:
            created_at_raw = market_data.get("created_at")
            created_at = None
            if isinstance(created_at_raw, str):
                try:
                    # Handle Zulu timestamps like "2024-01-03T10:00:00Z"
                    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                except ValueError:
                    created_at = None
            if created_at:
                market_age_hours = (datetime.utcnow().replace(tzinfo=created_at.tzinfo) - created_at).total_seconds() / 3600
                if market_age_hours < self.trading_controls.min_market_age_hours:
                    return False, f"Market age {market_age_hours:.1f}h below minimum {self.trading_controls.min_market_age_hours}h"
        
        # 8. Check bid-ask spread
        bid = market_data.get("bid", 0)
        ask = market_data.get("ask", 1)
        spread = ask - bid
        if spread > self.trading_controls.max_spread_tolerance:
            return False, f"Spread {spread:.4f} ({spread*100:.2f}%) exceeds tolerance {self.trading_controls.max_spread_tolerance*100:.2f}%"
        
        # 9. Check asset whitelist
        asset = market_data.get("asset", "UNKNOWN")
        if self.trading_controls.asset_whitelist:
            if asset not in self.trading_controls.asset_whitelist:
                return False, f"Asset {asset} not in whitelist {self.trading_controls.asset_whitelist}"
        
        # 10. Check asset blacklist
        if asset in self.trading_controls.asset_blacklist:
            return False, f"Asset {asset} is blacklisted"
        
        # 11. Check category whitelist
        category = market_data.get("category", "unknown")
        if self.trading_controls.category_whitelist:
            if category not in self.trading_controls.category_whitelist:
                return False, f"Category {category} not in whitelist {self.trading_controls.category_whitelist}"
        
        # 12. Check category blacklist
        if category in self.trading_controls.category_blacklist:
            return False, f"Category {category} is blacklisted"
        
        # 13. Check probability
        probability = market_data.get("probability", 0.5)
        if probability < self.trading_controls.min_probability:
            return False, f"Probability {probability:.2%} below minimum {self.trading_controls.min_probability:.2%}"
        
        if probability > self.trading_controls.max_probability:
            return False, f"Probability {probability:.2%} above maximum {self.trading_controls.max_probability:.2%}"
        
        # All checks passed
        return True, "All validation checks passed"
    
    # =========================================================================
    # EXPOSURE & TRACKING
    # =========================================================================
    
    def record_trade(self, trade_record: Dict[str, Any]) -> None:
        """Record trade execution."""
        self.trades_today.append({
            **trade_record,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Track open position
        market_id = trade_record.get("market_id")
        if market_id:
            self.open_positions[market_id] = {
                "market_id": market_id,
                "entry_price": trade_record.get("execution_price", 0),
                "quantity": trade_record.get("quantity", 0),
                "side": trade_record.get("side", "BUY"),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _get_trades_today(self) -> List[Dict[str, Any]]:
        """Get trades executed today."""
        today = datetime.utcnow().date().isoformat()
        return [
            t for t in self.trades_today
            if t.get("timestamp", "").startswith(today)
        ]
    
    def _get_current_exposure(self) -> float:
        """Get total current exposure in USD."""
        return sum(
            pos.get("quantity", 0) * pos.get("entry_price", 0)
            for pos in self.open_positions.values()
        )
    
    def get_limits_status(self) -> Dict[str, Any]:
        """Get current status vs. limits."""
        trades_today = self._get_trades_today()
        current_exposure = self._get_current_exposure()
        open_positions_count = len(self.open_positions)
        
        return {
            "trades": {
                "today": len(trades_today),
                "limit": self.trading_controls.max_trades_per_day,
                "remaining": self.trading_controls.max_trades_per_day - len(trades_today),
                "pct_used": len(trades_today) / self.trading_controls.max_trades_per_day * 100
            },
            "exposure": {
                "current": current_exposure,
                "limit": self.trading_controls.max_exposure_total,
                "remaining": self.trading_controls.max_exposure_total - current_exposure,
                "pct_used": current_exposure / self.trading_controls.max_exposure_total * 100
            },
            "open_positions": open_positions_count,
            "max_positions": None,
        }
    
    # =========================================================================
    # TRIGGER CONFIGURATION
    # =========================================================================
    
    def should_trigger_workflow(
        self,
        last_run_time: Optional[datetime] = None,
        active_signals_count: int = 0,
        new_markets_count: int = 0
    ) -> Tuple[bool, List[str]]:
        """Check if workflow should trigger.
        
        Returns:
            (should_trigger: bool, reasons: List[str])
        """
        triggered_by = []
        
        # Interval-based trigger
        if last_run_time is None or \
           (datetime.utcnow() - last_run_time) > timedelta(hours=self.trigger_config.interval_hours):
            triggered_by.append("interval")
        
        # Signal-based trigger
        if active_signals_count >= self.trigger_config.min_signals_required:
            triggered_by.append("signals")
        
        # Market-based trigger
        if new_markets_count >= self.trigger_config.new_markets_threshold:
            triggered_by.append("new_markets")
        
        # Decide based on hybrid mode
        if self.trigger_config.trigger_type == "interval":
            should_trigger = "interval" in triggered_by
        elif self.trigger_config.trigger_type == "signal":
            should_trigger = "signals" in triggered_by
        elif self.trigger_config.trigger_type == "market":
            should_trigger = "new_markets" in triggered_by
        else:  # hybrid
            if self.trigger_config.hybrid_mode == "OR":
                should_trigger = len(triggered_by) > 0
            else:  # AND
                should_trigger = len(triggered_by) >= 2
        
        return should_trigger, triggered_by
    
    # =========================================================================
    # AGENT WEIGHT CALCULATIONS
    # =========================================================================
    
    def calculate_trade_score(
        self,
        agent_score: float,
        signal_score: float,
        market_data_score: float
    ) -> float:
        """Calculate weighted trade score.
        
        Args:
            agent_score: Agent recommendation (0-1)
            signal_score: RSS signal confidence (0-1)
            market_data_score: Market quality score (0-1)
        
        Returns:
            Weighted score (0-1)
        """
        weighted = (
            agent_score * self.agent_weights.agent_weight +
            signal_score * self.agent_weights.signal_weight +
            market_data_score * self.agent_weights.market_data_weight
        )
        
        # Clamp to 0-1
        return max(0, min(1, weighted))
    
    def get_agent_limits(self, agent_name: str) -> Dict[str, Any]:
        """Get per-agent limits."""
        agent_trades = [t for t in self.trades_today if t.get("agent_name") == agent_name]
        agent_exposure = sum(
            t.get("quantity", 0) * t.get("execution_price", 0)
            for t in agent_trades
        )
        
        return {
            "agent_name": agent_name,
            "max_trades": self.agent_weights.per_agent_max_trades,
            "trades_used": len(agent_trades),
            "trades_remaining": self.agent_weights.per_agent_max_trades - len(agent_trades),
            "max_exposure": self.agent_weights.per_agent_max_exposure,
            "exposure_used": agent_exposure,
            "exposure_remaining": self.agent_weights.per_agent_max_exposure - agent_exposure
        }
    
    def get_agent_strategy(self, agent_name: str) -> str:
        """Get trading strategy for agent."""
        return self.agent_weights.agent_strategies.get(
            agent_name,
            "balanced"
        )
    
    # =========================================================================
    # CONFIGURATION EXPORT
    # =========================================================================
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get complete configuration summary."""
        return {
            "trading_controls": {
                "max_trades_per_day": self.trading_controls.max_trades_per_day,
                "max_amount_per_trade": self.trading_controls.max_amount_per_trade,
                "max_exposure_total": self.trading_controls.max_exposure_total,
                "min_probability": self.trading_controls.min_probability,
                "max_probability": self.trading_controls.max_probability,
                "asset_whitelist": self.trading_controls.asset_whitelist,
                "category_whitelist": self.trading_controls.category_whitelist,
                "execution_mode": "real" if self.trading_controls.real_mode else "mock"
            },
            "trigger_config": {
                "trigger_type": self.trigger_config.trigger_type,
                "interval_hours": self.trigger_config.interval_hours,
                "min_signals_required": self.trigger_config.min_signals_required,
                "new_markets_threshold": self.trigger_config.new_markets_threshold,
                "hybrid_mode": self.trigger_config.hybrid_mode
            },
            "agent_weights": {
                "agent_weight": self.agent_weights.agent_weight,
                "signal_weight": self.agent_weights.signal_weight,
                "market_data_weight": self.agent_weights.market_data_weight,
                "per_agent_max_exposure": self.agent_weights.per_agent_max_exposure,
                "per_agent_max_trades": self.agent_weights.per_agent_max_trades
            },
            "limits_status": self.get_limits_status()
        }
