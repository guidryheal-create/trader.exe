"""Polymarket task-flow registration using class-based pipeline tasks."""

from __future__ import annotations

from typing import Any

from core.pipelines.polymarket.pipeline_tasks import PolymarketBatchOrchestrationTask
from core.pipelines.tasks import BasePipelineTask, TaskFlowSpec


def build_polymarket_pipeline_tasks(runtime: Any) -> list[BasePipelineTask]:
    return [PolymarketBatchOrchestrationTask(runtime)]


def build_polymarket_task_flows(runtime: Any) -> list[TaskFlowSpec]:
    return [task.to_spec() for task in build_polymarket_pipeline_tasks(runtime)]
