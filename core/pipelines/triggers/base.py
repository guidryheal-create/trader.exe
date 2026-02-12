"""Class-based trigger-flow interface for pipeline managers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTriggerFlow(ABC):
    """Uniform trigger flow contract consumed by manager registries."""

    trigger_id: str = ""
    pipeline: str = ""
    system_name: str = ""
    scheduler_type: str = "event"
    description: str = ""
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    @abstractmethod
    async def resolve(self, **kwargs: Any) -> dict[str, Any]:
        """Resolve trigger flow with a normalized kwargs interface."""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "pipeline": self.pipeline,
            "system_name": self.system_name,
            "scheduler_type": self.scheduler_type,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "handler_name": self.__class__.__name__,
        }
