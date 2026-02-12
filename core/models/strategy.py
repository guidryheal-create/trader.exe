"""
Strategy mode definitions matching the frontend StrategyMode enum.
Defines trading strategies and their CAMEL worker configurations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class StrategyMode(str, Enum):
    """Trading strategy modes matching frontend enum."""

    WALLET_BALANCING = "wallet_balancing"
    TRADING = "trading"
    MOMENTUM_SNIPER = "momentum_sniper"
    MEAN_REVERSION = "mean_reversion"
    TREND_FOLLOWER = "trend_follower"
    ARBITRAGE_HUNTER = "arbitrage_hunter"
    NEWS_CATALYST = "news_catalyst"
    RISK_ADJUSTED_PORTFOLIO = "risk_adjusted_portfolio"

class ChainConfig:
    name: str
    chain_id: int
    universal_router: str
    pool_manager: str
    quoter: str
    permit2: str


@dataclass
class StrategyConfig:
    """Configuration for a trading strategy."""

    mode: StrategyMode
    interval: str  # "minutes" | "hours" | "days"
    focus: str  # "minimize_loss" | "maximize_gain"
    description: str
    display_name: str
    # Strategy-specific parameters
    max_allocation: float = 0.25  # Maximum position size per asset
    min_action_threshold: float = 0.15  # Minimum confidence to take action
    trend_weight: float = 0.4  # Weight for trend signals
    fact_weight: float = 0.35  # Weight for fact/sentiment signals
    risk_weight: float = 0.1  # Weight for risk adjustment


# ✅ OPTIMIZED: Only keep essential strategies (3-5 total)
# Enabled strategies: WALLET_BALANCING, TRADING, TREND_FOLLOWER, RISK_ADJUSTED_PORTFOLIO
# Disabled: MOMENTUM_SNIPER, MEAN_REVERSION, ARBITRAGE_HUNTER, NEWS_CATALYST

# Strategy configurations matching frontend STRATEGY_CONFIGS
STRATEGY_CONFIGS: dict[StrategyMode, StrategyConfig] = {
    StrategyMode.WALLET_BALANCING: StrategyConfig(
        mode=StrategyMode.WALLET_BALANCING,
        interval="days",
        focus="minimize_loss",
        description="Optimize wallet allocation to minimize long-term loss. Focuses on portfolio stability and risk management.",
        display_name="Wallet Balancing",
        max_allocation=0.20,  # Lower max allocation for stability
        min_action_threshold=0.20,  # Higher threshold for conservative decisions
        trend_weight=0.3,
        fact_weight=0.3,
        risk_weight=0.2,  # Higher risk weight
    ),
    StrategyMode.TRADING: StrategyConfig(
        mode=StrategyMode.TRADING,
        interval="minutes",
        focus="maximize_gain",
        description="Snipe crypto opportunities for maximum gain. Focuses on strong opportunities.",
        display_name="Trading",
        max_allocation=0.35,  # Higher max allocation for aggressive trading
        min_action_threshold=0.10,  # Lower threshold for quick decisions
        trend_weight=0.5,  # Higher trend weight
        fact_weight=0.25,
        risk_weight=0.05,  # Lower risk weight
    ),
    StrategyMode.TREND_FOLLOWER: StrategyConfig(
        mode=StrategyMode.TREND_FOLLOWER,
        interval="hours",
        focus="maximize_gain",
        description="Follow sustained trends using signal analysis and sentiment data. Optimized for longer-term directional moves.",
        display_name="Trend Follower",
        max_allocation=0.30,
        min_action_threshold=0.15,
        trend_weight=0.55,  # Very high trend weight
        fact_weight=0.20,
        risk_weight=0.10,
    ),
    StrategyMode.RISK_ADJUSTED_PORTFOLIO: StrategyConfig(
        mode=StrategyMode.RISK_ADJUSTED_PORTFOLIO,
        interval="days",
        focus="minimize_loss",
        description="Balanced portfolio allocation using comprehensive risk assessment across all workers. Maximizes risk-adjusted returns.",
        display_name="Risk-Adjusted Portfolio",
        max_allocation=0.20,
        min_action_threshold=0.18,
        trend_weight=0.25,
        fact_weight=0.25,
        risk_weight=0.25,  # Very high risk weight
    ),
    # ✅ DISABLED STRATEGIES (commented out for optimization)
    # StrategyMode.MOMENTUM_SNIPER: StrategyConfig(...),
    # StrategyMode.MEAN_REVERSION: StrategyConfig(...),
    # StrategyMode.ARBITRAGE_HUNTER: StrategyConfig(...),
    # StrategyMode.NEWS_CATALYST: StrategyConfig(...),
}

# ✅ Enabled strategies list for filtering
ENABLED_STRATEGIES = [
    StrategyMode.WALLET_BALANCING,
    StrategyMode.TRADING,
    StrategyMode.TREND_FOLLOWER,
    StrategyMode.RISK_ADJUSTED_PORTFOLIO,
]


def get_strategy_config(mode: StrategyMode | str) -> StrategyConfig:
    """Get strategy configuration by mode."""
    if isinstance(mode, str):
        try:
            mode = StrategyMode(mode)
        except ValueError:
            # Default to wallet balancing if invalid
            mode = StrategyMode.WALLET_BALANCING
    
    # ✅ Check if strategy is enabled
    if mode not in ENABLED_STRATEGIES:
        # Fallback to wallet balancing if strategy is disabled
        mode = StrategyMode.WALLET_BALANCING
    
    return STRATEGY_CONFIGS.get(mode, STRATEGY_CONFIGS[StrategyMode.WALLET_BALANCING])


def is_strategy_enabled(mode: StrategyMode | str) -> bool:
    """Check if a strategy is enabled."""
    if isinstance(mode, str):
        try:
            mode = StrategyMode(mode)
        except ValueError:
            return False
    return mode in ENABLED_STRATEGIES

