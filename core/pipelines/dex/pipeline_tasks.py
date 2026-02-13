"""Class-based DEX pipeline tasks for TaskFlowHub."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.settings.config import settings
from core.pipelines.dex.types import ReviewMode
from core.pipelines.tasks import BasePipelineTask

CYCLE_TRIGGERS = {
    "scheduled_cycle",
    "manual_trigger",
    "watchlist_global_roi_trigger",
    "watchlist_fast_trigger",
}


class DexCyclePipelineTask(BasePipelineTask):
    task_id = "cycle_pipeline"
    pipeline = "dex"
    system_name = "dex_manager"
    trigger_types = set(CYCLE_TRIGGERS)
    scheduler_type = "interval"
    description = (
        "Single DEX cycle pipeline block handled by one root CAMEL task with subtasks "
        "(wallet -> exploration -> sentiment -> trend -> decision -> position update -> enhancement -> strategy hint)."
    )
    input_schema = {
        "type": "object",
        "required": ["mode", "reason"],
        "properties": {
            "mode": {"type": "string"},
            "reason": {"type": "string"},
            "execution_id": {"type": "string"},
        },
    }

    async def execute(self, context: dict[str, object]) -> dict[str, object]:
        runtime = self.runtime
        mode = context["mode"]
        reason = str(context["reason"])
        execution_id = context.get("execution_id")

        started_at = datetime.now(timezone.utc)
        if execution_id:
            runtime._set_execution_state(str(execution_id), status="running", stage="wallet_review")
        runtime._emit("INFO", "DEX cycle started", {"mode": mode.value, "reason": reason, "started_at": started_at.isoformat()})

        wallet_address = settings.wallet_address or ""
        root_task = runtime._build_task(
            content=(
                "End-to-end DEX analysis and trade decision cycle.\n\n"
                f"Trigger: {reason}\n"
                f"Mode: {mode.value}\n"
                f"Wallet: {wallet_address or 'not_configured'}\n\n"
                "Use dependency-aware task resolution. Respect subtask dependencies and hierarchy. "
                "Keep execution decisions grounded in pool metrics, sentiment/news, trend, and wallet state."
            ),
            task_type="dex_orchestration",
            additional_info={
                "trigger_type": reason,
                "mode": mode.value,
                "wallet_address": wallet_address,
                "token_exploration_limit": runtime.config.token_exploration_limit,
            },
        )

        wallet_stage = runtime._build_task(
            content="Wallet review context: evaluate global wallet state and recent trades.",
            task_type="wallet_review",
            parent=root_task,
            additional_info={"mode": mode.value, "reason": reason, "wallet_address": wallet_address},
        )
        exploration_stage = runtime._build_task(
            content="Token exploration stage.",
            task_type="token_exploration",
            parent=root_task,
            dependencies=[wallet_stage],
        )
        news_stage = runtime._build_task(
            content="News + sentiment stage.",
            task_type="news_sentiment",
            parent=root_task,
            dependencies=[exploration_stage],
        )
        trend_stage = runtime._build_task(
            content="Trend analysis stage.",
            task_type="trend_analysis",
            parent=root_task,
            dependencies=[exploration_stage, news_stage],
        )
        decision_stage = runtime._build_task(
            content="Decision gateway stage.",
            task_type="decision_gateway",
            parent=root_task,
            dependencies=[wallet_stage, exploration_stage, news_stage, trend_stage],
        )
        position_update_stage = runtime._build_task(
            content="Position update review stage (must run after decision).",
            task_type="position_update_review",
            parent=root_task,
            dependencies=[wallet_stage, decision_stage],
        )
        enhancement_stage = runtime._build_task(
            content="Auto enhancement stage.",
            task_type="auto_enhancement",
            parent=root_task,
            dependencies=[decision_stage, position_update_stage],
        )
        strategy_hint_stage = runtime._build_task(
            content="Strategy hint stage.",
            task_type="strategy_hint",
            parent=root_task,
            dependencies=[wallet_stage, decision_stage, position_update_stage, enhancement_stage],
        )

        try:
            root_task.subtasks = [
                wallet_stage,
                exploration_stage,
                news_stage,
                trend_stage,
                decision_stage,
                position_update_stage,
                enhancement_stage,
                strategy_hint_stage,
            ]
        except Exception:
            pass

        orchestration = await runtime._execute_task(root_task, "dex_orchestration")

        if execution_id:
            runtime._set_execution_state(str(execution_id), stage="token_exploration")
        wallet_feedback = await runtime._run_wallet_review_task(
            wallet_address=wallet_address,
            mode=mode,
            reason=reason,
            use_cache=True,
            parent=root_task,
            dependencies=None,
            additional_info={"wallet_stage": True},
        )
        exploration = await runtime._run_token_exploration_task(
            wallet_address=wallet_address,
            mode=mode,
            reason=reason,
            parent=root_task,
            dependencies=[wallet_stage],
            additional_info={"token_limit": runtime.config.token_exploration_limit},
        )
        news_sentiment = await runtime._run_news_sentiment_task(
            mode=mode,
            exploration=exploration,
            parent=root_task,
            dependencies=[exploration_stage],
            additional_info={"reason": reason},
        )
        if execution_id:
            runtime._set_execution_state(str(execution_id), stage="trend_analysis")
        trend = await runtime._run_trend_analysis_task(
            mode=mode,
            exploration=exploration,
            news_sentiment=news_sentiment,
            parent=root_task,
            dependencies=[exploration_stage, news_stage],
            additional_info={"reason": reason},
        )
        decision = await runtime._run_decision_gateway_task(
            mode=mode,
            exploration=exploration,
            news_sentiment=news_sentiment,
            trend=trend,
            wallet_feedback=wallet_feedback,
            parent=root_task,
            dependencies=[wallet_stage, exploration_stage, news_stage, trend_stage],
            additional_info={"reason": reason},
        )
        if execution_id:
            runtime._set_execution_state(str(execution_id), stage="position_update")
        position_update = await runtime._run_position_update_task(
            wallet_address=wallet_address,
            mode=mode,
            reason=reason,
            parent=root_task,
            dependencies=[wallet_stage, decision_stage],
            additional_info={"decision": runtime._summarize_payload(decision)},
        )
        enhancement = await runtime._run_auto_enhancement_task(
            mode=mode,
            reason=reason,
            parent=root_task,
            dependencies=[decision_stage, position_update_stage],
            additional_info={"decision": runtime._summarize_payload(decision)},
        )
        if execution_id:
            runtime._set_execution_state(str(execution_id), stage="strategy_hint")
        strategy_hint = await runtime._run_strategy_hint_task(
            mode=mode,
            reason=reason,
            wallet_review=wallet_feedback,
            position_update=position_update,
            decision=decision,
            enhancement=enhancement,
            parent=root_task,
            dependencies=[wallet_stage, decision_stage, position_update_stage, enhancement_stage],
        )

        runtime._last_cycle_at = started_at
        payload = {
            "success": True,
            "mode": mode.value,
            "reason": reason,
            "started_at": started_at.isoformat(),
            "orchestration": orchestration,
            "token_exploration": exploration,
            "news_sentiment": news_sentiment,
            "trend": trend,
            "decision": decision,
            "wallet_feedback": wallet_feedback,
            "position_update": position_update,
            "enhancement": enhancement,
            "strategy_hint": strategy_hint,
        }
        runtime._emit("INFO", "DEX cycle completed", {"mode": mode.value, "reason": reason, "started_at": started_at.isoformat()})
        if execution_id:
            runtime._set_execution_state(str(execution_id), stage="completed")
        return payload


class DexWatchlistReviewPipelineTask(BasePipelineTask):
    task_id = "watchlist_review_pipeline"
    pipeline = "dex"
    system_name = "dex_manager"
    trigger_types = {"watchlist_review_only"}
    scheduler_type = "event"
    description = "Single watchlist review pipeline block for triggered position update review."
    input_schema = {
        "type": "object",
        "required": ["notification"],
        "properties": {"notification": {"type": "object"}},
    }

    async def execute(self, context: dict[str, object]) -> dict[str, object]:
        runtime = self.runtime
        notification: dict[str, Any] = context["notification"]  # type: ignore[assignment]

        wallet_feedback = await runtime._run_wallet_review_task(
            wallet_address=notification.get("wallet_address", ""),
            mode=ReviewMode.LONG_STUDY,
            reason="watchlist_review_only",
        )
        position_update = await runtime._run_position_update_task(
            wallet_address=notification.get("wallet_address", ""),
            mode=ReviewMode.LONG_STUDY,
            reason="watchlist_review_only",
        )
        task = runtime._build_task(
            content=(
                "Review the triggered position and update watchlist state without full trade pipeline.\n"
                f"Notification: {notification}\n"
                f"Wallet feedback: {wallet_feedback}\n"
                f"Position update: {position_update}"
            ),
            task_type="watchlist_review",
            additional_info={
                "trigger_type": notification.get("trigger_type"),
                "position_id": notification.get("position_id"),
            },
        )
        result = await runtime._execute_task(task, "watchlist_review")
        return {"success": True, "result": result}
