"""Polymarket interval trigger settings."""

from __future__ import annotations

from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from core.pipelines.workers import IntervalWorker
from core.pipelines.trigger_registry import TriggerSpec, trigger_registry


class PolymarketIntervalTriggerSettings(BaseModel):
    trigger_type: Literal["interval", "manual", "hybrid", "signal", "market"] = "hybrid"
    interval_hours: int = Field(default=4, ge=1, le=168)


SPEC = TriggerSpec(
    pipeline="polymarket",
    trigger="interval",
    description="Interval-based trigger policy for Polymarket flux scans.",
    settings_model=PolymarketIntervalTriggerSettings,
)


def register() -> None:
    trigger_registry.register(SPEC)


def extract(config: dict) -> dict:
    trigger_cfg = config.get("trigger_config", {})
    return PolymarketIntervalTriggerSettings(
        trigger_type=str(trigger_cfg.get("trigger_type", "hybrid")),
        interval_hours=int(trigger_cfg.get("interval_hours", 4)),
    ).model_dump()


def apply(config: dict, payload: dict) -> dict:
    data = PolymarketIntervalTriggerSettings(**payload).model_dump()
    trigger_cfg = config.setdefault("trigger_config", {})
    trigger_cfg["trigger_type"] = data["trigger_type"]
    trigger_cfg["interval_hours"] = data["interval_hours"]
    return data


class PolymarketIntervalRuntime:
    """Runtime loop controller for Polymarket interval scans."""

    def __init__(self, callback: Callable[[], Awaitable[None]], scan_interval: int) -> None:
        self._worker = IntervalWorker(
            callback=callback,
            interval_seconds=max(5, int(scan_interval)),
            name="polymarket_interval_scan",
            min_interval_seconds=5,
        )

    def update_scan_interval(self, scan_interval: int) -> None:
        self._worker.interval_seconds = max(5, int(scan_interval))

    async def run_loop(self, is_running: Callable[[], bool]) -> None:
        await self._worker.run_loop(is_running=is_running)
