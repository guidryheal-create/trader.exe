"""DEX watchlist trigger settings."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from core.pipelines.dex.watchlist_worker import WatchlistWorker
from core.pipelines.trigger_registry import TriggerSpec, trigger_registry


class DexWatchlistTriggerSettings(BaseModel):
    enabled: bool = False
    scan_seconds: int = Field(default=60, ge=5, le=3600)
    trigger_pct: float = Field(default=0.05, ge=0.0, le=1.0)
    fast_trigger_pct: float = Field(default=0.10, ge=0.0, le=1.0)
    global_roi_trigger_enabled: bool = True
    global_roi_trigger_pct: float = Field(default=0.04, ge=0.0, le=1.0)
    global_roi_fast_trigger_pct: float = Field(default=0.08, ge=0.0, le=1.0)


SPEC = TriggerSpec(
    pipeline="dex",
    trigger="watchlist",
    description="Watchlist trigger for position-level and global ROI threshold events.",
    settings_model=DexWatchlistTriggerSettings,
)


def register() -> None:
    trigger_registry.register(SPEC)


def extract(config: dict) -> dict:
    process = config.get("process", {})
    runtime = config.get("runtime", {})
    return DexWatchlistTriggerSettings(
        enabled=bool(runtime.get("watchlist_enabled", False)),
        scan_seconds=int(process.get("watchlist_scan_seconds", 60)),
        trigger_pct=float(process.get("watchlist_trigger_pct", 0.05)),
        fast_trigger_pct=float(process.get("watchlist_fast_trigger_pct", 0.10)),
        global_roi_trigger_enabled=bool(process.get("watchlist_global_roi_trigger_enabled", True)),
        global_roi_trigger_pct=float(process.get("watchlist_global_roi_trigger_pct", 0.04)),
        global_roi_fast_trigger_pct=float(process.get("watchlist_global_roi_fast_trigger_pct", 0.08)),
    ).model_dump()


def apply(config: dict, payload: dict) -> dict:
    data = DexWatchlistTriggerSettings(**payload).model_dump()
    process = config.setdefault("process", {})
    runtime = config.setdefault("runtime", {})
    process["watchlist_scan_seconds"] = data["scan_seconds"]
    process["watchlist_trigger_pct"] = data["trigger_pct"]
    process["watchlist_fast_trigger_pct"] = data["fast_trigger_pct"]
    process["watchlist_global_roi_trigger_enabled"] = data["global_roi_trigger_enabled"]
    process["watchlist_global_roi_trigger_pct"] = data["global_roi_trigger_pct"]
    process["watchlist_global_roi_fast_trigger_pct"] = data["global_roi_fast_trigger_pct"]
    runtime["watchlist_enabled"] = data["enabled"]
    return data


class DexWatchlistRuntime:
    """Runtime loop controller for DEX watchlist trigger processing."""

    def __init__(
        self,
        watchlist_toolkit: Any,
        on_notification: Callable[[dict[str, Any]], Awaitable[None]],
        evaluate_global_roi: Callable[[], dict[str, Any]],
    ) -> None:
        self._worker = WatchlistWorker(
            watchlist_toolkit=watchlist_toolkit,
            on_notification=on_notification,
            evaluate_global_roi=evaluate_global_roi,
        )

    async def run_loop(self, is_running: Callable[[], bool], scan_seconds: int) -> None:
        await self._worker.run_loop(is_running=is_running, scan_seconds=scan_seconds)
