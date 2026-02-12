"""Polymarket signal trigger settings."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.pipelines.trigger_registry import TriggerSpec, trigger_registry


class PolymarketSignalTriggerSettings(BaseModel):
    signal_threshold_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    min_signals_required: int = Field(default=2, ge=1, le=20)


SPEC = TriggerSpec(
    pipeline="polymarket",
    trigger="signal",
    description="Signal confidence trigger settings for Polymarket workforce decisions.",
    settings_model=PolymarketSignalTriggerSettings,
)


def register() -> None:
    trigger_registry.register(SPEC)


def extract(config: dict) -> dict:
    trigger_cfg = config.get("trigger_config", {})
    return PolymarketSignalTriggerSettings(
        signal_threshold_confidence=float(trigger_cfg.get("signal_threshold_confidence", 0.75)),
        min_signals_required=int(trigger_cfg.get("min_signals_required", 2)),
    ).model_dump()


def apply(config: dict, payload: dict) -> dict:
    data = PolymarketSignalTriggerSettings(**payload).model_dump()
    trigger_cfg = config.setdefault("trigger_config", {})
    trigger_cfg["signal_threshold_confidence"] = data["signal_threshold_confidence"]
    trigger_cfg["min_signals_required"] = data["min_signals_required"]
    return data
