"""DEX task-flow registration using class-based pipeline tasks."""

from __future__ import annotations

from typing import Any

from core.pipelines.dex.pipeline_tasks import DexCyclePipelineTask, DexWatchlistReviewPipelineTask
from core.pipelines.tasks import BasePipelineTask, TaskFlowSpec


def build_dex_pipeline_tasks(runtime: Any) -> list[BasePipelineTask]:
    return [
        DexCyclePipelineTask(runtime),
        DexWatchlistReviewPipelineTask(runtime),
    ]


def build_dex_task_flows(runtime: Any) -> list[TaskFlowSpec]:
    return [task.to_spec() for task in build_dex_pipeline_tasks(runtime)]
