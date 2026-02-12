"""Polymarket market/feed threshold trigger settings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.pipelines.workers import FeedCacheThresholdWorker
from core.pipelines.trigger_registry import TriggerSpec, trigger_registry


class PolymarketMarketTriggerSettings(BaseModel):
    new_markets_threshold: int = Field(default=5, ge=1, le=1000)
    review_threshold: int = Field(default=25, ge=1, le=1000)
    batch_size: int = Field(default=50, ge=1, le=500)
    max_cache: int = Field(default=500, ge=10, le=10000)


SPEC = TriggerSpec(
    pipeline="polymarket",
    trigger="market",
    description="Market/feed threshold trigger and cache settings.",
    settings_model=PolymarketMarketTriggerSettings,
)


def register() -> None:
    trigger_registry.register(SPEC)


def extract(config: dict) -> dict:
    trigger_cfg = config.get("trigger_config", {})
    rss_cfg = config.get("rss_flux", {})
    return PolymarketMarketTriggerSettings(
        new_markets_threshold=int(trigger_cfg.get("new_markets_threshold", 5)),
        review_threshold=int(rss_cfg.get("review_threshold", 25)),
        batch_size=int(rss_cfg.get("batch_size", 50)),
        max_cache=int(rss_cfg.get("max_cache", 500)),
    ).model_dump()


def apply(config: dict, payload: dict) -> dict:
    data = PolymarketMarketTriggerSettings(**payload).model_dump()
    trigger_cfg = config.setdefault("trigger_config", {})
    rss_cfg = config.setdefault("rss_flux", {})
    trigger_cfg["new_markets_threshold"] = data["new_markets_threshold"]
    rss_cfg["review_threshold"] = data["review_threshold"]
    rss_cfg["batch_size"] = data["batch_size"]
    rss_cfg["max_cache"] = data["max_cache"]
    return data


class PolymarketFeedRuntime:
    """Feed cache + threshold runtime controller for market trigger."""

    def __init__(self, max_cache: int, threshold: int) -> None:
        self._worker = FeedCacheThresholdWorker(
            key_fn=lambda market: str(market.get("id") or ""),
            entry_builder=self._build_feed_entry,
            is_entry_active=lambda entry: not bool(entry.get("exhausted")),
            max_cache=max_cache,
            threshold=threshold,
        )

    @staticmethod
    def _build_feed_entry(
        market: dict[str, Any],
        existing: dict[str, Any] | None,
        now_iso: str,
    ) -> dict[str, Any]:
        return {
            "id": market.get("id"),
            "title": market.get("title"),
            "first_seen": (existing or {}).get("first_seen", now_iso),
            "last_seen": now_iso,
            "exhausted": bool(market.get("exhausted", False)),
            "data": market.get("data", market),
        }

    @property
    def cache(self) -> dict[str, dict[str, Any]]:
        return self._worker.cache

    def load(self, cache: dict[str, dict[str, Any]]) -> None:
        self._worker.load(cache)

    def update_limits(self, max_cache: int, threshold: int) -> None:
        self._worker.max_cache = int(max_cache)
        self._worker.threshold = int(threshold)

    def update(self, markets: list[dict[str, Any]], is_exhausted: Any) -> dict[str, dict[str, Any]]:
        enriched = []
        for market in markets:
            copied = dict(market)
            copied["exhausted"] = bool(is_exhausted(market))
            enriched.append(copied)
        return self._worker.update(enriched)

    def pending_items(self) -> list[dict[str, Any]]:
        return self._worker.pending_items()

    def ready(self) -> bool:
        return self._worker.ready()

    def mark_processed(self, processed_items: list[dict[str, Any]]) -> None:
        self._worker.mark_processed(processed_items)
