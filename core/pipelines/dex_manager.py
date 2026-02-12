"""DEX Manager workforce pipeline.

Provides a DEX-focused orchestration layer with:
- Scheduled decision cycles (every N hours)
- Parallel watchlist trigger worker (optional)
- Position risk controls (stop-loss / take-profit auto-sell)
- Wallet analysis + optional auto-enhancement feedback loop
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from camel.tasks import Task
from camel.societies.workforce import Workforce

from core.camel_tools.auto_enhancement_toolkit import AutoEnhancementToolkit
from core.camel_tools.uviswap_toolkit import UviSwapToolkit
from core.camel_tools.wallet_analysis_toolkit import WalletAnalysisToolkit
from core.camel_tools.watchlist_toolkit import WatchlistToolkit
from core.logging import log
from core.pipelines.dex import DexTraderConfig, ExecutionTracker, ReviewMode
from core.pipelines.dex.task_flows import build_dex_pipeline_tasks
from core.pipelines.dex.trigger_flows import build_dex_trigger_flows
from core.pipelines.dex.triggers.interval import DexCycleIntervalRuntime
from core.pipelines.dex.triggers.watchlist import DexWatchlistRuntime
from core.pipelines.manager_base import TaskFlowManagerMixin


class DexManager(TaskFlowManagerMixin):
    """DEX manager orchestration with strategy cycle + watchlist parallel worker."""

    def __init__(
        self,
        workforce: Workforce,
        config: DexTraderConfig | None = None,
        uviswap_toolkit: UviSwapToolkit | None = None,
        watchlist_toolkit: WatchlistToolkit | None = None,
        wallet_toolkit: WalletAnalysisToolkit | None = None,
        enhancement_toolkit: AutoEnhancementToolkit | None = None,
        event_logger: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.workforce = workforce
        self.config = config or DexTraderConfig()

        self.uviswap_toolkit = uviswap_toolkit or UviSwapToolkit()
        self.watchlist_toolkit = watchlist_toolkit or WatchlistToolkit()
        self.wallet_toolkit = wallet_toolkit or WalletAnalysisToolkit()
        self.enhancement_toolkit = enhancement_toolkit or AutoEnhancementToolkit()
        self._event_logger = event_logger

        self._running = False
        self._cycle_task: asyncio.Task | None = None
        self._watchlist_task: asyncio.Task | None = None
        self._cycle_enabled = True
        self._watchlist_enabled = bool(self.config.watchlist_enabled)
        self._last_cycle_at: datetime | None = None
        self._wallet_review_cache: dict[str, dict[str, Any]] = {}
        self._wallet_review_cache_at: dict[str, datetime] = {}
        self._strategy_hint_cache: dict[str, Any] | None = None
        self._strategy_hint_at: datetime | None = None
        self._execution_tracker = ExecutionTracker(self._summarize_payload)
        self.pipeline = "dex"
        self.system_name = "dex_manager"
        self._init_task_flow_registry(build_dex_pipeline_tasks(self))
        self._init_trigger_flow_registry(build_dex_trigger_flows(self))
        self._watchlist_runtime = DexWatchlistRuntime(
            watchlist_toolkit=self.watchlist_toolkit,
            on_notification=lambda notification: self.run_trigger_flow(
                "watchlist_notification",
                notification=notification,
            ),
            evaluate_global_roi=self._evaluate_global_roi_trigger,
        )
        self._cycle_runtime = DexCycleIntervalRuntime(
            callback=lambda: self.run_trigger_flow(
                "cycle",
                mode=ReviewMode.LONG_STUDY,
                reason="scheduled_cycle",
            ),
            cycle_hours=int(self.config.cycle_hours),
        )

    @classmethod
    async def build(
        cls,
        workforce: Workforce | None = None,
        config: DexTraderConfig | None = None,
        event_logger: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> "DexManager":
        resolved_workforce = workforce
        if resolved_workforce is None:
            from core.camel_runtime import CamelTradingRuntime

            runtime = await CamelTradingRuntime.instance()
            resolved_workforce = await runtime.get_workforce()
        return cls(workforce=resolved_workforce, config=config, event_logger=event_logger)

    def _set_execution_state(self, execution_id: str, **updates: Any) -> None:
        self._execution_tracker.set_state(execution_id, **updates)

    def launch_execution(self, mode: ReviewMode, reason: str) -> str:
        async def _run_with_execution_id(execution_id: str) -> dict[str, Any]:
            return await self.run_trader_cycle(mode=mode, reason=reason, execution_id=execution_id)

        return self._execution_tracker.launch(mode=mode, reason=reason, run_fn=_run_with_execution_id)

    def get_execution_status(self, execution_id: str) -> dict[str, Any]:
        return self._execution_tracker.get_status(execution_id)

    def list_executions(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._execution_tracker.list(limit=limit)

    def _emit(self, level: str, message: str, context: dict[str, Any] | None = None) -> None:
        if not self._event_logger:
            return
        try:
            self._event_logger(level, message, context or {})
        except Exception:
            pass

    async def start(self, cycle_enabled: bool = True, watchlist_enabled: bool | None = None) -> None:
        if self._running:
            return
        self._cycle_enabled = bool(cycle_enabled)
        self._watchlist_enabled = (
            self.config.watchlist_enabled
            if watchlist_enabled is None
            else bool(watchlist_enabled)
        )
        if not self._cycle_enabled and not self._watchlist_enabled:
            self._running = False
            self._emit(
                "WARNING",
                "DEX manager start skipped",
                {"reason": "all_workers_disabled"},
            )
            return
        self._running = True

        if self._cycle_enabled:
            self._cycle_task = asyncio.create_task(self._cycle_loop())
        if self._watchlist_enabled:
            self._watchlist_task = asyncio.create_task(self._watchlist_loop())

        log.info(
            f"DEX manager started cycle_hours={self.config.cycle_hours} "
            f"watchlist_enabled={self._watchlist_enabled} cycle_enabled={self._cycle_enabled}"
        )
        self._emit(
            "INFO",
            "DEX manager started",
            {
                "cycle_enabled": self._cycle_enabled,
                "watchlist_enabled": self._watchlist_enabled,
                "cycle_hours": self.config.cycle_hours,
                "watchlist_scan_seconds": self.config.watchlist_scan_seconds,
            },
        )

    async def stop(self) -> None:
        self._running = False
        for task in [self._cycle_task, self._watchlist_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._cycle_task = None
        self._watchlist_task = None
        await self._execution_tracker.cancel_all()
        log.info("DEX manager stopped")
        self._emit("INFO", "DEX manager stopped", {})

    async def _cycle_loop(self) -> None:
        self._cycle_runtime.update_cycle_hours(int(self.config.cycle_hours))
        await self._cycle_runtime.run_loop(
            is_running=lambda: self._running and self._cycle_enabled,
        )

    async def _watchlist_loop(self) -> None:
        await self._watchlist_runtime.run_loop(
            is_running=lambda: self._running and self._watchlist_enabled,
            scan_seconds=int(self.config.watchlist_scan_seconds),
        )

    def _evaluate_global_roi_trigger(self) -> dict[str, Any]:
        return self.watchlist_toolkit.evaluate_global_roi_trigger(
            threshold_pct=self.config.watchlist_global_roi_trigger_pct,
            fast_threshold_pct=self.config.watchlist_global_roi_fast_trigger_pct,
            enabled=self.config.watchlist_global_roi_trigger_enabled,
        )

    @staticmethod
    def _summarize_payload(payload: dict[str, Any], max_len: int = 1500) -> str:
        text = json.dumps(payload, default=str)
        return text if len(text) <= max_len else f"{text[:max_len]}...(truncated)"

    def _build_task(
        self,
        *,
        content: str,
        task_type: str,
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
        subtasks: list[Task] | None = None,
    ) -> Task:
        kwargs: dict[str, Any] = {"content": content, "type": task_type}
        if parent is not None:
            kwargs["parent"] = parent
        if dependencies:
            kwargs["dependencies"] = dependencies
        if additional_info:
            kwargs["additional_info"] = additional_info
        if subtasks:
            kwargs["subtasks"] = subtasks

        try:
            return Task(**kwargs)
        except TypeError:
            # Compatibility with CAMEL versions that do not accept some kwargs.
            fallback_kwargs = {"content": content, "type": task_type}
            task = Task(**fallback_kwargs)
            if subtasks:
                try:
                    task.subtasks = subtasks
                except Exception:
                    pass
            return task

    def _get_recent_trade_history(self, limit: int = 20) -> list[dict[str, Any]]:
        redis_client = self.watchlist_toolkit.redis
        if not redis_client:
            return []
        try:
            raw_items = redis_client.lrange("dex:trade_history", 0, max(0, limit - 1))
            trades: list[dict[str, Any]] = []
            for raw in raw_items:
                try:
                    trades.append(json.loads(raw))
                except Exception:
                    continue
            return trades
        except Exception as exc:
            log.debug(f"Unable to load recent trade history: {exc}")
            return []

    async def run_trader_cycle(self, mode: ReviewMode, reason: str, execution_id: str | None = None) -> dict[str, Any]:
        return await self.run_trigger_flow("cycle", mode=mode, reason=reason, execution_id=execution_id)


    async def _run_token_exploration_task(
        self,
        wallet_address: str,
        mode: ReviewMode,
        reason: str,
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "mode": mode.value,
            "reason": reason,
            "token_limit": self.config.token_exploration_limit,
            "wallet_address": wallet_address,
            "markets_context_hint": "Use token exploration with liquidity/tvl/volume metrics and pool mapping.",
        }
        task = self._build_task(
            content=f"Token exploration stage: {payload}",
            task_type="token_exploration",
            parent=parent,
            dependencies=dependencies,
            additional_info=additional_info,
        )
        result = await self._execute_task(task, "token_exploration")
        return {"success": True, "result": result}

    async def _run_news_sentiment_task(
        self,
        mode: ReviewMode,
        exploration: dict[str, Any],
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = self._build_task(
            content=(
                "News and sentiment stage. Use recent token candidates from exploration, "
                "news signals, and polymarket review with price context before trend analysis.\n"
                f"mode={mode.value} exploration={exploration}"
            ),
            task_type="news_sentiment",
            parent=parent,
            dependencies=dependencies,
            additional_info=additional_info,
        )
        result = await self._execute_task(task, "news_sentiment")
        return {"success": True, "result": result}

    async def _run_trend_analysis_task(
        self,
        mode: ReviewMode,
        exploration: dict[str, Any],
        news_sentiment: dict[str, Any],
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = self._build_task(
            content=(
                "Trend analysis stage. Analyze candidate tokens with market structure, momentum, "
                "and timing.\n"
                f"mode={mode.value} exploration={exploration} news_sentiment={news_sentiment}"
            ),
            task_type="trend_analysis",
            parent=parent,
            dependencies=dependencies,
            additional_info=additional_info,
        )
        result = await self._execute_task(task, "trend_analysis")
        return {"success": True, "result": result}

    async def _run_decision_gateway_task(
        self,
        mode: ReviewMode,
        exploration: dict[str, Any],
        news_sentiment: dict[str, Any],
        trend: dict[str, Any],
        wallet_feedback: dict[str, Any],
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = self._build_task(
            content=(
                "Decision gateway stage. Fuse token exploration + news/sentiment + trend + wallet feedback. "
                "Choose execute/skip and register risk controls for selected positions.\n"
                f"mode={mode.value} exploration={exploration} news={news_sentiment} trend={trend} wallet={wallet_feedback}"
            ),
            task_type="decision_gateway",
            parent=parent,
            dependencies=dependencies,
            additional_info=additional_info,
        )
        decision_result = await self._execute_task(task, "decision_gateway")
        return {"success": True, "result": decision_result}

    async def register_position_with_risk(
        self,
        token_symbol: str,
        token_address: str,
        quantity: float,
        entry_price: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        exit_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.uviswap_toolkit.register_stop_loss_take_profit(
            token_symbol=token_symbol,
            token_address=token_address,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            exit_to_symbol="USDC",
            exit_plan=exit_plan,
        )

    async def _run_wallet_review_task(
        self,
        wallet_address: str,
        mode: ReviewMode,
        reason: str,
        use_cache: bool = True,
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cache_key = f"{wallet_address or 'all'}:{mode.value}"
        now = datetime.now(timezone.utc)
        if use_cache and cache_key in self._wallet_review_cache and cache_key in self._wallet_review_cache_at:
            ttl = max(0, int(self.config.wallet_review_cache_seconds))
            if ttl > 0 and (now - self._wallet_review_cache_at[cache_key]).total_seconds() < ttl:
                cached = dict(self._wallet_review_cache[cache_key])
                cached["cached"] = True
                return cached

        wallet_feedback = self.wallet_toolkit.get_wallet_feedback(wallet_address=wallet_address)
        global_wallet = self.wallet_toolkit.get_global_wallet_state(wallet_address=wallet_address)
        recent_trades = self._get_recent_trade_history(limit=20)
        task = self._build_task(
            content=(
                "Wallet review task. Analyze wallet exposure, open positions, and risk state.\n"
                f"mode={mode.value} reason={reason} wallet_feedback={wallet_feedback} "
                f"global_wallet={global_wallet} recent_trades={recent_trades}"
            ),
            task_type="wallet_review",
            parent=parent,
            dependencies=dependencies,
            additional_info=additional_info,
        )
        result = await self._execute_task(task, "wallet_review")
        payload = {
            "feedback": wallet_feedback,
            "global_wallet_state": global_wallet,
            "recent_trades": recent_trades,
            "task_result": result,
            "cached": False,
        }
        self._wallet_review_cache[cache_key] = payload
        self._wallet_review_cache_at[cache_key] = now
        return payload

    async def _run_position_update_task(
        self,
        wallet_address: str,
        mode: ReviewMode,
        reason: str,
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        global_wallet_state = self.wallet_toolkit.get_global_wallet_state(wallet_address=wallet_address)
        task = self._build_task(
            content=(
                "Review current positions and update watchlist/exit plans as needed based on wallet ROI and token exposure.\n"
                f"mode={mode.value} reason={reason} global_wallet_state={global_wallet_state}"
            ),
            task_type="position_update_review",
            parent=parent,
            dependencies=dependencies,
            additional_info=additional_info,
        )
        result = await self._execute_task(task, "position_update_review")
        return {"global_wallet_state": global_wallet_state, "task_result": result}

    async def _run_auto_enhancement_task(
        self,
        mode: ReviewMode,
        reason: str,
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.auto_enhancement_enabled:
            return {"success": True, "feedback": None, "disabled": True}

        feedback = self.enhancement_toolkit.generate_feedback()
        task = self._build_task(
            content=(
                "Auto enhancement task. Review trade history and wallet outcomes to improve next cycle.\n"
                f"mode={mode.value} reason={reason} feedback={feedback}"
            ),
            task_type="auto_enhancement",
            parent=parent,
            dependencies=dependencies,
            additional_info=additional_info,
        )
        result = await self._execute_task(task, "auto_enhancement")
        return {"success": True, "feedback": feedback, "task_result": result}

    async def _run_strategy_hint_task(
        self,
        mode: ReviewMode,
        reason: str,
        wallet_review: dict[str, Any],
        position_update: dict[str, Any],
        decision: dict[str, Any],
        enhancement: dict[str, Any],
        parent: Task | None = None,
        dependencies: list[Task] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        interval_hours = max(1, int(self.config.strategy_hint_interval_hours))
        if self._strategy_hint_cache and self._strategy_hint_at:
            if now - self._strategy_hint_at < timedelta(hours=interval_hours):
                cached = dict(self._strategy_hint_cache)
                cached["cached"] = True
                return cached

        recent_trades = self._get_recent_trade_history(limit=50)
        task = self._build_task(
            content=(
                "Future trade process hint task.\n"
                "Provide a concise strategy memo covering:\n"
                "1) which strategy profile should lead next cycles,\n"
                "2) which assets to prioritize/monitor,\n"
                "3) current global crypto market feeling/regime (alt season, bullish, neutral, risk-off),\n"
                "4) what was done wrong recently,\n"
                "5) concrete improvements for the next decision cycles.\n"
                f"mode={mode.value} reason={reason}\n"
                f"wallet_review={wallet_review}\n"
                f"position_update={position_update}\n"
                f"decision={decision}\n"
                f"enhancement={enhancement}\n"
                f"recent_trades={recent_trades}"
            ),
            task_type="strategy_hint",
            parent=parent,
            dependencies=dependencies,
            additional_info={
                "mode": mode.value,
                "reason": reason,
                "hint_interval_hours": interval_hours,
            },
        )
        task_result = await self._execute_task(task, "strategy_hint")
        payload = {
            "success": True,
            "cached": False,
            "generated_at": now.isoformat(),
            "task_result": task_result,
        }
        self._strategy_hint_cache = payload
        self._strategy_hint_at = now
        return payload

    async def _execute_task(self, task: Task, task_type: str) -> dict[str, Any]:
        self._emit("INFO", "DEX task started", {"task_type": task_type})
        try:
            if hasattr(self.workforce, "process_task_async"):
                result = await self.workforce.process_task_async(task)
            elif hasattr(self.workforce, "process_task"):
                result = await self.workforce.process_task(task)
            else:
                log.warning(f"Workforce missing process method for task_type={task_type}")
                self._emit("WARNING", "DEX task skipped", {"task_type": task_type, "reason": "workforce_no_method"})
                return {"status": "skipped", "reason": "workforce_no_method", "task_type": task_type}

            payload = result if isinstance(result, dict) else {"status": "completed", "result": str(result)}
            self._emit("INFO", "DEX task completed", {"task_type": task_type, "result": self._summarize_payload(payload)})
            return payload
        except Exception as exc:
            log.warning(f"Task execution failed type={task_type}: {exc}")
            self._emit("ERROR", "DEX task failed", {"task_type": task_type, "error": str(exc)})
            return {"status": "failed", "task_type": task_type, "error": str(exc)}

    def _record_trade_history(self, payload: dict[str, Any]) -> None:
        if not self.watchlist_toolkit.redis:
            return
        try:
            self.watchlist_toolkit.redis.lpush("dex:trade_history", json.dumps(payload))
            self.watchlist_toolkit.redis.ltrim("dex:trade_history", 0, 1000)
        except Exception as exc:
            log.debug(f"Failed recording dex trade history: {exc}")

    def get_status(self) -> dict[str, Any]:
        workers = [
            {
                "worker_name": "cycle_interval",
                "pipeline": "dex",
                "system_name": self.system_name,
                "enabled": bool(self._cycle_enabled),
                "running": bool(self._running and self._cycle_enabled),
                "interval_seconds": max(60, int(self.config.cycle_hours * 3600)),
            },
            {
                "worker_name": "watchlist",
                "pipeline": "dex",
                "system_name": self.system_name,
                "enabled": bool(self._watchlist_enabled),
                "running": bool(self._running and self._watchlist_enabled),
                "interval_seconds": int(self.config.watchlist_scan_seconds),
            },
        ]
        return {
            "pipeline": "dex",
            "system_name": self.system_name,
            "running": self._running,
            "cycle_enabled": self._cycle_enabled,
            "cycle_hours": self.config.cycle_hours,
            "watchlist_enabled": self._watchlist_enabled,
            "watchlist_scan_seconds": self.config.watchlist_scan_seconds,
            "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "wallet_review_cache_seconds": self.config.wallet_review_cache_seconds,
            "strategy_hint_interval_hours": self.config.strategy_hint_interval_hours,
            "last_strategy_hint_at": self._strategy_hint_at.isoformat() if self._strategy_hint_at else None,
            "auto_enhancement_enabled": self.config.auto_enhancement_enabled,
            "workers": workers,
            "task_flows": self._task_flow_hub.list_flows(flags=self._task_flow_flags),
            "trigger_flows": self.list_trigger_flows(),
            "trigger_history": self.list_trigger_history(limit=50),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
