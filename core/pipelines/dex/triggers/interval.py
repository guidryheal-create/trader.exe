"""DEX interval cycle trigger settings."""

from __future__ import annotations

from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from core.pipelines.workers import IntervalWorker
from core.pipelines.trigger_registry import TriggerSpec, trigger_registry


class DexCycleIntervalSettings(BaseModel):
    enabled: bool = False
    cycle_hours: int = Field(default=4, ge=1, le=168)
    token_exploration_limit: int = Field(default=20, ge=1, le=200)


SPEC = TriggerSpec(
    pipeline="dex",
    trigger="cycle_interval",
    description="Scheduled interval trigger for full DEX decision cycle.",
    settings_model=DexCycleIntervalSettings,
)


def register() -> None:
    trigger_registry.register(SPEC)


def extract(config: dict) -> dict:
    process = config.get("process", {})
    runtime = config.get("runtime", {})
    return DexCycleIntervalSettings(
        enabled=bool(runtime.get("cycle_enabled", False)),
        cycle_hours=int(process.get("cycle_hours", 4)),
        token_exploration_limit=int(process.get("token_exploration_limit", 20)),
    ).model_dump()


def apply(config: dict, payload: dict) -> dict:
    data = DexCycleIntervalSettings(**payload).model_dump()
    config.setdefault("process", {})["cycle_hours"] = data["cycle_hours"]
    config.setdefault("process", {})["token_exploration_limit"] = data["token_exploration_limit"]
    config.setdefault("runtime", {})["cycle_enabled"] = data["enabled"]
    return data


class DexCycleIntervalRuntime:
    """Runtime loop controller for the DEX cycle interval trigger."""

    def __init__(self, callback: Callable[[], Awaitable[None]], cycle_hours: int) -> None:
        self._worker = IntervalWorker(
            callback=callback,
            interval_seconds=max(60, int(cycle_hours * 3600)),
            name="dex_cycle",
            min_interval_seconds=60,
        )

    @property
    def interval_seconds(self) -> int:
        return int(self._worker.interval_seconds)

    def update_cycle_hours(self, cycle_hours: int) -> None:
        self._worker.interval_seconds = max(60, int(cycle_hours * 3600))

    async def run_loop(self, is_running: Callable[[], bool]) -> None:
        await self._worker.run_loop(is_running=is_running)
