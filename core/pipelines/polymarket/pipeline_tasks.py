"""Class-based Polymarket pipeline tasks for TaskFlowHub."""

from __future__ import annotations

from typing import Any

from camel.tasks import Task

from core.pipelines.tasks import BasePipelineTask


class PolymarketBatchOrchestrationTask(BasePipelineTask):
    task_id = "batch_orchestration"
    pipeline = "polymarket"
    system_name = "polymarket_manager"
    trigger_types = {"interval", "manual", "signal", "market", "hybrid"}
    scheduler_type = "event"
    description = "Run polymarket batch task tree (fetch -> analysis -> decision)."
    input_schema = {
        "type": "object",
        "required": ["markets", "trigger_type", "enforce_limits"],
        "properties": {
            "markets": {"type": "array"},
            "trigger_type": {"type": "string"},
            "enforce_limits": {"type": "boolean"},
        },
    }

    async def execute(self, context: dict[str, object]) -> dict[str, object]:
        runtime = self.runtime
        markets = context.get("markets", [])
        trigger_type = str(context.get("trigger_type", "interval"))
        enforce_limits = bool(context.get("enforce_limits", True))

        if not markets:
            return {"status": "skipped", "reason": "no_markets"}

        market_titles = [m.get("title", "Unknown Market") for m in markets]
        market_ids = [m.get("id") for m in markets if m.get("id")]

        allow_execution = True
        if enforce_limits and runtime._trades_today >= runtime.config.max_trades_per_day:
            allow_execution = False

        limit_note = "Manual override: bypass limits and confidence thresholds."
        if enforce_limits:
            limit_note = (
                f"Respect limits (max_trades_per_day={runtime.config.max_trades_per_day}, "
                f"min_confidence={runtime.config.min_confidence:.2f})."
            )
        if not allow_execution:
            limit_note += " Trading execution is disabled for this batch (daily limit reached)."

        root_task = Task(
            content=(
                "End-to-end analysis and trade decision for Polymarket batch.\n\n"
                f"Trigger: {trigger_type}\n"
                f"Batch size: {len(markets)}\n"
                f"Markets: {market_titles}\n\n"
                "Use the Polymarket toolkit to fetch data and execute trades. "
                "Do not return structured JSON as source of truth. "
                f"{limit_note}"
            ),
            type="orchestration",
            additional_info={
                "trigger_type": trigger_type,
                "market_ids": market_ids,
            },
        )

        fetch_task = Task(
            content=(
                "Fetch full market details and orderbooks for each market in the batch.\n"
                "Use: get_market_details(), get_orderbook()."
            ),
            type="market_fetch",
            parent=root_task,
        )

        analysis_task = Task(
            content=(
                "Analyze each market and estimate confidence (0.0–1.0). "
                "Evaluate liquidity, spread, odds, and crowd consensus risk."
            ),
            type="analysis",
            parent=root_task,
            dependencies=[fetch_task],
        )

        if allow_execution:
            decision_task = Task(
                content=(
                    "For each market, decide BUY / HOLD / SKIP. "
                    "Execute trades only for BUY using the Polymarket toolkit."
                ),
                type="decision",
                parent=root_task,
                dependencies=[analysis_task],
            )
            root_task.subtasks = [fetch_task, analysis_task, decision_task]
        else:
            decision_task = Task(
                content=(
                    "For each market, decide BUY / HOLD / SKIP. "
                    "Execution is disabled for this batch."
                ),
                type="decision",
                parent=root_task,
                dependencies=[analysis_task],
            )
            root_task.subtasks = [fetch_task, analysis_task, decision_task]

        result = await runtime._execute_task(root_task, "batch_orchestration")

        workforce_snapshot = {}
        if hasattr(runtime.workforce, "get_workforce_log_tree"):
            workforce_snapshot["task_tree"] = runtime.workforce.get_workforce_log_tree()
        if hasattr(runtime.workforce, "get_completed_tasks"):
            workforce_snapshot["completed_tasks"] = runtime.workforce.get_completed_tasks()
        if hasattr(runtime.workforce, "get_workforce_kpis"):
            workforce_snapshot["kpis"] = runtime.workforce.get_workforce_kpis()

        return {
            "status": "completed",
            "result": result,
            "workforce_observability": workforce_snapshot,
            "execution_enabled": allow_execution,
        }
