"""Global registry for pipeline trigger classes and settings schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class TriggerSpec:
    pipeline: str
    trigger: str
    description: str
    settings_model: type[BaseModel]

    @property
    def key(self) -> str:
        return f"{self.pipeline}.{self.trigger}"


class TriggerRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, TriggerSpec] = {}

    def register(self, spec: TriggerSpec) -> None:
        self._specs[spec.key] = spec

    def list(self) -> list[TriggerSpec]:
        return sorted(self._specs.values(), key=lambda s: s.key)

    def get(self, pipeline: str, trigger: str) -> TriggerSpec | None:
        return self._specs.get(f"{pipeline}.{trigger}")

    def describe(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for spec in self.list():
            rows.append(
                {
                    "key": spec.key,
                    "pipeline": spec.pipeline,
                    "trigger": spec.trigger,
                    "description": spec.description,
                    "settings_schema": spec.settings_model.model_json_schema(),
                }
            )
        return rows


trigger_registry = TriggerRegistry()

