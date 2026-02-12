"""DEX strategy feedback trigger settings."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.pipelines.trigger_registry import TriggerSpec, trigger_registry


class DexStrategyFeedbackSettings(BaseModel):
    wallet_review_cache_seconds: int = Field(default=3600, ge=0, le=86400)
    strategy_hint_interval_hours: int = Field(default=6, ge=1, le=168)
    auto_enhancement_enabled: bool = True


SPEC = TriggerSpec(
    pipeline="dex",
    trigger="strategy_feedback",
    description="Periodic wallet review and strategy feedback settings.",
    settings_model=DexStrategyFeedbackSettings,
)


def register() -> None:
    trigger_registry.register(SPEC)


def extract(config: dict) -> dict:
    process = config.get("process", {})
    return DexStrategyFeedbackSettings(
        wallet_review_cache_seconds=int(process.get("wallet_review_cache_seconds", 3600)),
        strategy_hint_interval_hours=int(process.get("strategy_hint_interval_hours", 6)),
        auto_enhancement_enabled=bool(process.get("auto_enhancement_enabled", True)),
    ).model_dump()


def apply(config: dict, payload: dict) -> dict:
    data = DexStrategyFeedbackSettings(**payload).model_dump()
    process = config.setdefault("process", {})
    process["wallet_review_cache_seconds"] = data["wallet_review_cache_seconds"]
    process["strategy_hint_interval_hours"] = data["strategy_hint_interval_hours"]
    process["auto_enhancement_enabled"] = data["auto_enhancement_enabled"]
    return data
