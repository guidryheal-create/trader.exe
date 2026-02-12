"""Polymarket Manager Pipeline - Event-driven market scanning & trading.

This pipeline only processes the Polymarket market feed (no external RSS sources).
Because Polymarket does not expose a direct RSS endpoint, we maintain a cached JSON
state of market updates and review batches once a threshold is reached.

Architecture:
- MarketScanner: Polls Polymarket for new/updated markets (RSS-like)
- MarketAnalyzer: Deep analysis per market (orderbook, liquidity, activity)
- TradeDecisionMaker: Determines if position is worthwhile
- TradeExecutor: Executes position or records skip decision
- ResultTracker: Monitors outcomes and ROI

Pure CAMEL Workforce + Task decomposition with Polymarket MCP tools.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum

from camel.tasks import Task
from camel.societies.workforce import Workforce

from core.clients.polymarket_client import PolymarketClient
from core.logging import log
from core.pipelines.manager_base import TaskFlowManagerMixin
from core.pipelines.polymarket.task_flows import build_polymarket_pipeline_tasks
from core.pipelines.polymarket.trigger_flows import build_polymarket_trigger_flows
from core.pipelines.polymarket.triggers.interval import PolymarketIntervalRuntime
from core.pipelines.polymarket.triggers.market import PolymarketFeedRuntime


class MarketFilterCriteria(Enum):
    """Filtering criteria for market selection."""
    HIGH_VOLUME = "high_volume"  # Recent activity
    LIQUID = "liquid"  # Deep orderbook
    CLOSE_ODDS = "close_odds"  # Tight bid-ask
    TRENDING = "trending"  # Rising volume/interest
    NEW_MARKET = "new_market"  # Recently created


class RSSFluxConfig:
    """Configuration for Polymarket manager trigger intervals."""

    def __init__(
        self,
        scan_interval: int = 300,  # 5 minutes default
        batch_size: int = 50,
        review_threshold: int = 25,
        max_cache: int = 500,
        max_trades_per_day: int = 10,
        min_confidence: float = 0.65,
        trigger_type: str = "interval",
        interval_hours: int = 4,
        cache_path: Optional[str] = None,
    ):
        self.scan_interval = scan_interval
        self.batch_size = batch_size
        self.review_threshold = review_threshold
        self.max_cache = max_cache
        self.max_trades_per_day = max_trades_per_day
        self.min_confidence = min_confidence
        self.trigger_type = trigger_type
        self.interval_hours = interval_hours
        self.cache_path = cache_path or "logs/polymarket_feed_cache.json"
        log.info(
            "[RSS FLUX CONFIG] Initialized: scan_interval=%ds, batch_size=%d, "
            "min_confidence=%.2f, max_trades_per_day=%d",
            scan_interval,
            batch_size,
            min_confidence,
            max_trades_per_day,
        )


class PolymarketManager(TaskFlowManagerMixin):
    """Event-driven Polymarket trading orchestrator using CAMEL Workforce.

    Continuously scans Polymarket markets, applies filters, performs analysis,
    and executes trades based on opportunity scoring.

    Public API:
    - `start()` : Begin continuous market scanning
    - `process_market_batch()` : Scan and filter markets
    - `stop()` : Graceful shutdown
    """

    def __init__(
        self,
        workforce: Workforce,
        api_client: Any = None,
        config: Optional[RSSFluxConfig] = None,
        event_logger: Any | None = None,
    ) -> None:
        """Initialize Polymarket Manager pipeline.

        Args:
            workforce: CAMEL Workforce instance with shared memory
            api_client: PolymarketClient for market data access
            config: RSSFluxConfig with trigger intervals and trading limits
        """
        self.config = config or RSSFluxConfig()
        self.workforce = workforce
        self.api_client = api_client or PolymarketClient()
        self.polymarket_client = self.api_client
        self.scan_interval = self.config.scan_interval
        self.batch_size = self.config.batch_size
        self.trigger_type = self.config.trigger_type
        self.interval_hours = self.config.interval_hours
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self._last_scan_cursor = None
        self._active_positions: Dict[str, Dict[str, Any]] = {}
        self.review_threshold = self.config.review_threshold
        self.max_cache = self.config.max_cache
        self.cache_path = Path(self.config.cache_path)
        self._feed_cache: Dict[str, Dict[str, Any]] = {}
        self._trades_today = 0
        self._trade_day = datetime.now(timezone.utc).date()
        self._scan_lock = asyncio.Lock()
        self._last_trigger_at: Optional[datetime] = None
        self._last_trigger_type: Optional[str] = None
        self._last_interval_trigger_at: Optional[datetime] = None
        self._event_logger = event_logger
        self.pipeline = "polymarket"
        self.system_name = "polymarket_manager"
        self._init_task_flow_registry(build_polymarket_pipeline_tasks(self))
        self._init_trigger_flow_registry(build_polymarket_trigger_flows(self))
        self._interval_runtime = PolymarketIntervalRuntime(
            callback=self._interval_scan_tick,
            scan_interval=self.scan_interval,
        )
        self._feed_runtime = PolymarketFeedRuntime(
            max_cache=self.max_cache,
            threshold=self.review_threshold,
        )
        self._load_cache()

    @classmethod
    async def build(
        cls,
        workforce: Workforce | None = None,
        api_client: Any = None,
        config: Optional[RSSFluxConfig] = None,
        event_logger: Any | None = None,
    ) -> "PolymarketManager":
        resolved_workforce = workforce
        if resolved_workforce is None:
            from core.camel_runtime import CamelTradingRuntime

            runtime = await CamelTradingRuntime.instance()
            resolved_workforce = await runtime.get_workforce()
        return cls(
            workforce=resolved_workforce,
            api_client=api_client,
            config=config,
            event_logger=event_logger,
        )

    def _load_cache(self) -> None:
        """Load cached Polymarket feed state from disk."""
        try:
            if self.cache_path.exists():
                data = json.loads(self.cache_path.read_text())
                self._feed_cache = data.get("markets", {}) if isinstance(data, dict) else {}
            else:
                self._feed_cache = {}
            self._feed_runtime.load(self._feed_cache)
        except Exception as exc:
            log.warning(f"[POLYMARKET RSS FLUX] Failed to load cache: {exc}")
            self._feed_cache = {}
            self._feed_runtime.load({})

    def _save_cache(self) -> None:
        """Persist cached Polymarket feed state to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(self._feed_cache),
                "markets": self._feed_cache,
            }
            self.cache_path.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            log.warning(f"[POLYMARKET RSS FLUX] Failed to save cache: {exc}")

    def _is_exhausted(self, market: Dict[str, Any]) -> bool:
        """Check if a market is exhausted (closed/expired or already active)."""
        market_id = market.get("id")
        if not market_id:
            return True
        if market_id in self._active_positions:
            return True
        if market.get("closed") is True or market.get("active") is False:
            return True
        close_time = market.get("close_time")
        if isinstance(close_time, str):
            try:
                close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                if close_dt <= datetime.now(timezone.utc):
                    return True
            except Exception:
                pass
        return False

    def _update_feed_cache(self, markets: List[Dict[str, Any]]) -> None:
        """Update cached feed with latest markets and prune exhausted."""
        self._feed_runtime.update_limits(max_cache=self.max_cache, threshold=self.review_threshold)
        self._feed_cache = self._feed_runtime.update(markets, is_exhausted=self._is_exhausted)

    async def start(self) -> None:
        """Begin continuous market scanning loop."""
        if self._running:
            log.warning("[POLYMARKET RSS FLUX] Already running, ignoring start request")
            return

        self._running = True
        log.info(
            f"[POLYMARKET RSS FLUX] Starting market scanning (interval={self.scan_interval}s, batch={self.batch_size})"
        )

        # Launch background scanning task
        self._interval_runtime.update_scan_interval(self.scan_interval)
        self._scan_task = asyncio.create_task(self._interval_runtime.run_loop(is_running=lambda: self._running))

    async def stop(self) -> None:
        """Graceful shutdown of market scanning."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        log.info("[POLYMARKET RSS FLUX] Market scanning stopped")

    async def _interval_scan_tick(self) -> None:
        if self.trigger_type != "interval":
            return
        await self.process_market_batch(trigger_type="interval", verify_positions=True, enforce_limits=True)

    async def _refresh_active_positions(self) -> None:
        """Refresh active positions from the Polymarket client when available."""
        if not hasattr(self.polymarket_client, "get_open_positions"):
            return
        try:
            positions = self.polymarket_client.get_open_positions()
            if asyncio.iscoroutine(positions):
                positions = await positions
            positions = positions or {}
            if isinstance(positions, dict):
                for market_id, orders in positions.items():
                    existing = self._active_positions.get(market_id, {})
                    if not isinstance(existing, dict):
                        existing = {}
                    self._active_positions[market_id] = {
                        **existing,
                        "market_id": market_id,
                        "orders": orders,
                    }
                address = (
                    getattr(self.polymarket_client, "polygon_address", None)
                    or getattr(self.polymarket_client, "address", None)
                    or "unknown"
                )
                short_addr = f"{str(address)[:6]}...{str(address)[-4:]}" if address else "unknown"
                log.info(
                    "[POLYMARKET RSS FLUX] Open positions refreshed for wallet %s: %d",
                    short_addr,
                    len(self._active_positions),
                )
        except Exception as exc:
            log.warning(f"[POLYMARKET RSS FLUX] Failed to refresh open positions: {exc}")

    async def process_market_batch(
        self,
        trigger_type: str = "interval",
        verify_positions: bool = True,
        enforce_limits: bool = True,
    ) -> Dict[str, Any]:
        return await self.run_trigger_flow(
            "market_batch",
            trigger_type=trigger_type,
            verify_positions=verify_positions,
            enforce_limits=enforce_limits,
        )

    async def _fetch_latest_markets(self) -> List[Dict[str, Any]]:
        """Fetch the latest markets directly from Polymarket API."""
        if not self.polymarket_client:
            return []
        try:
            markets = await self.polymarket_client.search_markets(
                query="",
                limit=self.batch_size,
            )
            return markets or []
        except Exception as exc:
            log.warning("[POLYMARKET RSS FLUX] Latest market fetch failed: %s", exc)
            return []

    def _filter_markets(self, markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter markets by opportunity criteria.

        Filters for:
        - High recent volume
        - Good liquidity (deep orderbook)
        - Tight odds (bid-ask spread)
        - Trending (increasing activity)
        - Sufficient time to expiration

        Returns:
            Filtered list of promising markets
        """
        filtered = []
        now = datetime.now(timezone.utc)

        for market in markets:
            try:
                # Extract market metrics
                volume_24h = market.get("volume_24h", 0)
                liquidity = market.get("liquidity_score", 0)  # 0-100
                bid_ask_spread = market.get("bid_ask_spread", 1.0)  # percentage
                close_time = market.get("close_time")

                # Parse close_time if string
                if isinstance(close_time, str):
                    close_time = datetime.fromisoformat(close_time.replace("Z", "+00:00"))

                # Calculate time to close
                time_to_close = (close_time - now).total_seconds() / 3600 if close_time else 0

                # Apply filters
                if volume_24h < 100:  # Minimum volume threshold
                    continue
                if liquidity < 40:  # Minimum liquidity (orderbook depth)
                    continue
                if bid_ask_spread > 5:  # Too wide spread
                    continue
                if time_to_close < 1 or time_to_close > 240:  # Between 1 hour and 10 days
                    continue

                # Market passed filters
                filtered.append({
                    **market,
                    "filter_score": (volume_24h / 1000) + (liquidity / 10) - (bid_ask_spread / 2),
                })

            except Exception as exc:
                log.debug(f"[POLYMARKET RSS FLUX] Filter error for market: {exc}")
                continue

        # Sort by opportunity score (highest first)
        filtered.sort(key=lambda m: m.get("filter_score", 0), reverse=True)

        return filtered[:20]  # Limit to top 20 opportunities per scan

    async def _run_batch_task(
        self,
        markets: List[Dict[str, Any]],
        trigger_type: str,
        enforce_limits: bool,
    ) -> Dict[str, Any]:
        """Backward-compatible entrypoint; delegates to registered batch pipeline task."""
        flow_results = await self._task_flow_hub.run(
            trigger_type=trigger_type,
            context={
                "markets": markets,
                "trigger_type": trigger_type,
                "enforce_limits": enforce_limits,
            },
            flags=self._task_flow_flags,
            selected_task_ids=["batch_orchestration"],
        )
        result = flow_results.get("batch_orchestration", {})
        return result if isinstance(result, dict) else {"status": "failed", "error": "batch_orchestration_failed"}

    async def _execute_task(
        self, task: Task, task_type: str
    ) -> Dict[str, Any]:
        """Execute a task through the Workforce.

        Args:
            task: CAMEL Task to execute
            task_type: Task type descriptor for logging

        Returns:
            Task execution result
        """
        try:
            log.debug(
                f"[POLYMARKET RSS FLUX] Executing task ({task_type}) "
                f"via workforce: {self.workforce.__class__.__name__}"
            )

            # Try multiple execution methods in fallback order
            if hasattr(self.workforce, "process_task_async"):
                log.debug("[POLYMARKET RSS FLUX] Using process_task_async")
                result = await self.workforce.process_task_async(task)
            elif hasattr(self.workforce, "process_task"):
                log.debug("[POLYMARKET RSS FLUX] Using process_task")
                result = await self.workforce.process_task(task)
            else:
                log.warning("[POLYMARKET RSS FLUX] Workforce has no task execution method")
                result = {"status": "placeholder"}

            return result if isinstance(result, dict) else {}
        except Exception as exc:
            log.warning(f"[POLYMARKET RSS FLUX] Task execution failed ({task_type}): {exc}")
            return {"status": "failed", "error": str(exc)}

    def get_active_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get currently active trading positions."""
        return self._active_positions.copy()

    def get_status(self) -> Dict[str, Any]:
        """Get current Polymarket Manager status including trading limits."""
        workers = [
            {
                "worker_name": "interval",
                "pipeline": "polymarket",
                "system_name": self.system_name,
                "enabled": self.trigger_type == "interval",
                "running": bool(self._running and self.trigger_type == "interval"),
                "interval_seconds": int(self.scan_interval),
            },
            {
                "worker_name": "market",
                "pipeline": "polymarket",
                "system_name": self.system_name,
                "enabled": True,
                "running": bool(self._running),
                "threshold": int(self.review_threshold),
                "cache_size": len(self._feed_cache),
            },
        ]
        return {
            "pipeline": "polymarket",
            "system_name": self.system_name,
            "running": self._running,
            "scan_interval": self.scan_interval,
            "batch_size": self.batch_size,
            "review_threshold": self.review_threshold,
            "active_positions": len(self._active_positions),
            "trades_today": self._trades_today,
            "trades_max_per_day": self.config.max_trades_per_day,
            "min_confidence": self.config.min_confidence,
            "cached_markets": len(self._feed_cache),
            "last_trigger_at": self._last_trigger_at.isoformat() if self._last_trigger_at else None,
            "last_trigger_type": self._last_trigger_type,
            "scan_in_progress": self._scan_lock.locked(),
            "trigger_type": self.trigger_type,
            "interval_hours": self.interval_hours,
            "workers": workers,
            "task_flows": self._task_flow_hub.list_flows(flags=self._task_flow_flags),
            "trigger_flows": self.list_trigger_flows(),
            "trigger_history": self.list_trigger_history(limit=50),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
