"""Class-based pipeline task interface for task-flow registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .base import TaskFlowSpec


class BasePipelineTask(ABC):
    """Unified interface for a task-flow pipeline unit."""

    task_id: str = ""
    pipeline: str = ""
    system_name: str = ""
    trigger_types: set[str] = set()
    scheduler_type: str = "manual"
    dependencies: list[str] = []
    description: str = ""
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute pipeline unit with runtime context."""

    def to_spec(self) -> TaskFlowSpec:
        return TaskFlowSpec(
            task_id=self.task_id,
            pipeline=self.pipeline,
            system_name=self.system_name,
            trigger_types=set(self.trigger_types),
            scheduler_type=self.scheduler_type,
            dependencies=list(self.dependencies),
            description=self.description,
            input_schema=dict(self.input_schema),
            output_schema=dict(self.output_schema),
            handler_name=self.__class__.__name__,
            executor=self.execute,
        )
