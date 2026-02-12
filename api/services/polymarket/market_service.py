"""Polymarket trading service for API.

Handles all Polymarket trading operations with proper logging and state management.
"""

from __future__ import annotations

from typing import Any, Dict
from datetime import datetime, timezone

from core.logging import log
from core.camel_tools.polymarket_toolkit import EnhancedPolymarketToolkit


class PolymarketService:
    """Service for Polymarket trading operations."""

    def __init__(self):
        """Initialize Polymarket service."""
        self.toolkit = EnhancedPolymarketToolkit()
        self.toolkit.initialize()
        log.info("[POLYMARKET SERVICE] Initialized")

    # ========================================================================
    # MARKET DISCOVERY & ANALYSIS
    # ========================================================================

    def search_markets(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        active_only: bool = True,
        category: str | None = None,
    ) -> Dict[str, Any]:
        """Search for markets."""
        log.info(f"[POLYMARKET SERVICE] Searching markets: query={query}, limit={limit}")
        result = self.toolkit.search_markets(query=query, limit=limit, offset=offset)
        
        if result.get("success"):
            markets = result.get("markets", [])
            if category and isinstance(markets, list):
                needle = category.strip().lower()
                def _matches_category(m: Dict[str, Any]) -> bool:
                    cat = str(m.get("category", "")).lower()
                    if needle and needle in cat:
                        return True
                    tags = m.get("tags") or []
                    if isinstance(tags, str):
                        tags = [tags]
                    for t in tags:
                        if needle in str(t).lower():
                            return True
                    return False
                markets = [m for m in markets if _matches_category(m)]
                result["markets"] = markets
                result["count"] = len(markets)
            if active_only and isinstance(markets, list):
                def _is_active(m: Dict[str, Any]) -> bool:
                    if m.get("active") is False or m.get("closed") is True:
                        return False
                    close_time = m.get("close_time") or m.get("end_time")
                    if isinstance(close_time, str):
                        try:
                            close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                            if close_dt <= datetime.now(close_dt.tzinfo):
                                return False
                        except Exception:
                            pass
                    return True
                active_markets = [m for m in markets if _is_active(m)]
                if active_markets:
                    markets = active_markets
                    result["markets"] = markets
                    result["count"] = len(markets)
            log.debug(f"[POLYMARKET SERVICE] Found {result.get('count', 0)} markets")
        else:
            log.warning(f"[POLYMARKET SERVICE] Search failed: {result.get('error')}")
        
        return result

    def get_trending_markets(
        self,
        timeframe: str = "24h",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get trending markets by volume."""
        log.info(f"[POLYMARKET SERVICE] Fetching trending ({timeframe}): limit={limit}")
        result = self.toolkit.get_trending_markets(timeframe=timeframe, limit=limit)
        
        if result.get("success"):
            log.debug(f"[POLYMARKET SERVICE] Retrieved {result.get('count', 0)} trending markets")
        else:
            log.warning(f"[POLYMARKET SERVICE] Trending fetch failed: {result.get('error')}")
        
        return result

    def get_market_details(self, market_id: str) -> Dict[str, Any]:
        """Get detailed market information."""
        log.debug(f"[POLYMARKET SERVICE] Fetching details: market={market_id[:8]}...")
        result = self.toolkit.get_market_details(market_id=market_id)
        
        if result.get("success"):
            market = result.get("market", {})
            log.debug(f"[POLYMARKET SERVICE] Market: {market.get('title', 'unknown')}")
        else:
            log.warning(f"[POLYMARKET SERVICE] Details fetch failed: {result.get('error')}")
        
        return result

    def get_orderbook(self, market_id: str, depth: int = 10) -> Dict[str, Any]:
        """Get orderbook for market."""
        log.debug(f"[POLYMARKET SERVICE] Fetching orderbook: market={market_id[:8]}..., depth={depth}")
        result = self.toolkit.get_orderbook(market_id=market_id, depth=depth)
        
        if result.get("success"):
            log.debug(f"[POLYMARKET SERVICE] Orderbook retrieved")
        else:
            log.warning(f"[POLYMARKET SERVICE] Orderbook fetch failed: {result.get('error')}")
        
        return result

    def calculate_opportunity(
        self,
        market_id: str,
        confidence_threshold: float = 0.55
    ) -> Dict[str, Any]:
        """Calculate market opportunity score."""
        log.debug(f"[POLYMARKET SERVICE] Calculating opportunity: market={market_id[:8]}...")
        result = self.toolkit.calculate_market_opportunity(
            market_id=market_id,
            confidence_threshold=confidence_threshold
        )
        
        if result.get("success"):
            log.debug(
                f"[POLYMARKET SERVICE] Opportunity score: {result.get('opportunity_score', 0):.2f}, "
                f"signal: {result.get('signal')}, confidence: {result.get('confidence', 0):.2f}"
            )
        else:
            log.warning(f"[POLYMARKET SERVICE] Opportunity calc failed: {result.get('error')}")
        
        return result

    # ========================================================================
    # POSITION SIZING
    # ========================================================================

    def calculate_position_size(
        self,
        market_id: str,
        portfolio_value: float,
        confidence: float,
        max_exposure_pct: float = 5.0
    ) -> Dict[str, Any]:
        """Calculate optimal position size."""
        log.debug(
            f"[POLYMARKET SERVICE] Sizing position: market={market_id[:8]}..., "
            f"portfolio=${portfolio_value:.2f}, confidence={confidence:.2f}"
        )
        
        result = self.toolkit.suggest_trade_size(
            market_id=market_id,
            portfolio_value=portfolio_value,
            confidence=confidence,
            max_exposure_pct=max_exposure_pct
        )
        
        if result.get("success"):
            log.debug(f"[POLYMARKET SERVICE] Position size: ${result.get('suggested_size', 0):.2f}")
        else:
            log.warning(f"[POLYMARKET SERVICE] Position sizing failed: {result.get('error')}")
        
        return result

    def get_service_status(self) -> Dict[str, Any]:
        """Get service status."""
        status = {
            "service": "PolymarketService",
            "status": "running",
            "toolkit_initialized": self.toolkit._initialized,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        log.debug(f"[POLYMARKET SERVICE] Status: {status}")
        return status
