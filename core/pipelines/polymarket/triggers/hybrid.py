"""Polymarket hybrid trigger settings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.pipelines.trigger_registry import TriggerSpec, trigger_registry


class PolymarketHybridTriggerSettings(BaseModel):
    hybrid_mode: Literal["OR", "AND"] = "OR"


SPEC = TriggerSpec(
    pipeline="polymarket",
    trigger="hybrid",
    description="Hybrid trigger composition settings (AND/OR conditions).",
    settings_model=PolymarketHybridTriggerSettings,
)


def register() -> None:
    trigger_registry.register(SPEC)


def extract(config: dict) -> dict:
    trigger_cfg = config.get("trigger_config", {})
    return PolymarketHybridTriggerSettings(
        hybrid_mode=str(trigger_cfg.get("hybrid_mode", "OR")),
    ).model_dump()


def apply(config: dict, payload: dict) -> dict:
    data = PolymarketHybridTriggerSettings(**payload).model_dump()
    trigger_cfg = config.setdefault("trigger_config", {})
    trigger_cfg["hybrid_mode"] = data["hybrid_mode"]
    return data
