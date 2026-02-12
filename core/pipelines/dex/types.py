"""Types/config used by DEX pipeline runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.config import settings


class ReviewMode(str, Enum):
    LONG_STUDY = "long_study"
    FAST_DECISION = "fast_decision"


@dataclass
class DexTraderConfig:
    cycle_hours: int = settings.dex_trader_cycle_hours
    watchlist_enabled: bool = settings.watchlist_enabled
    watchlist_scan_seconds: int = settings.watchlist_scan_seconds
    watchlist_trigger_pct: float = settings.watchlist_trigger_pct
    watchlist_fast_trigger_pct: float = settings.watchlist_fast_trigger_pct
    watchlist_global_roi_trigger_enabled: bool = settings.watchlist_global_roi_trigger_enabled
    watchlist_global_roi_trigger_pct: float = settings.watchlist_global_roi_trigger_pct
    watchlist_global_roi_fast_trigger_pct: float = settings.watchlist_global_roi_fast_trigger_pct
    token_exploration_limit: int = settings.dex_trader_token_exploration_limit
    wallet_review_cache_seconds: int = settings.dex_wallet_review_cache_seconds
    strategy_hint_interval_hours: int = settings.dex_strategy_hint_interval_hours
    auto_enhancement_enabled: bool = settings.auto_enhancement_enabled

