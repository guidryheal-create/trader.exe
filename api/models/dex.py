"""Pydantic models for DEX trading API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DexProcessConfig(BaseModel):
    active_bot: Literal["polymarket", "dex"] = "dex"
    cycle_hours: int = Field(default=4, ge=1, le=168)
    watchlist_scan_seconds: int = Field(default=60, ge=5, le=3600)
    watchlist_trigger_pct: float = Field(default=0.05, ge=0.0, le=1.0)
    watchlist_fast_trigger_pct: float = Field(default=0.10, ge=0.0, le=1.0)
    watchlist_global_roi_trigger_enabled: bool = True
    watchlist_global_roi_trigger_pct: float = Field(default=0.04, ge=0.0, le=1.0)
    watchlist_global_roi_fast_trigger_pct: float = Field(default=0.08, ge=0.0, le=1.0)
    token_exploration_limit: int = Field(default=20, ge=1, le=200)
    wallet_review_cache_seconds: int = Field(default=3600, ge=0, le=86400)
    strategy_hint_interval_hours: int = Field(default=6, ge=1, le=168)
    auto_enhancement_enabled: bool = True


class DexRuntimeConfig(BaseModel):
    cycle_enabled: bool = False
    watchlist_enabled: bool = False
    auto_start_on_boot: bool = True


class DexProcessConfigUpdate(BaseModel):
    active_bot: Literal["polymarket", "dex"] | None = None
    cycle_hours: int | None = Field(default=None, ge=1, le=168)
    watchlist_scan_seconds: int | None = Field(default=None, ge=5, le=3600)
    watchlist_trigger_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    watchlist_fast_trigger_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    watchlist_global_roi_trigger_enabled: bool | None = None
    watchlist_global_roi_trigger_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    watchlist_global_roi_fast_trigger_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    token_exploration_limit: int | None = Field(default=None, ge=1, le=200)
    wallet_review_cache_seconds: int | None = Field(default=None, ge=0, le=86400)
    strategy_hint_interval_hours: int | None = Field(default=None, ge=1, le=168)
    auto_enhancement_enabled: bool | None = None


class DexRuntimeConfigUpdate(BaseModel):
    cycle_enabled: bool | None = None
    watchlist_enabled: bool | None = None
    auto_start_on_boot: bool | None = None


class DexConfigResponse(BaseModel):
    status: str = "ok"
    process: DexProcessConfig
    runtime: DexRuntimeConfig
    last_updated: str


class DexConfigUpdateRequest(BaseModel):
    process: DexProcessConfigUpdate | None = None
    runtime: DexRuntimeConfigUpdate | None = None


class DexControlRequest(BaseModel):
    cycle_enabled: bool = True
    watchlist_enabled: bool = True


class DexTriggerRequest(BaseModel):
    mode: Literal["long_study", "fast_decision"] = "long_study"
    reason: str = "manual_trigger"


class DexStatusResponse(BaseModel):
    status: str
    pipeline: str | None = None
    system_name: str | None = None
    running: bool
    cycle_enabled: bool
    watchlist_enabled: bool
    active_bot: str
    workforce: dict[str, Any]
    wallet_state: dict[str, Any]
    metrics: dict[str, Any]
    workers: list[dict[str, Any]] = Field(default_factory=list)
    task_flows: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: str
