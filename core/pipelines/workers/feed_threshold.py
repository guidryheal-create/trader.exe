"""Feed cache + threshold worker primitive (RSS-like)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


class FeedCacheThresholdWorker:
    """Maintain a bounded cache of feed items and apply threshold gating."""

    def __init__(
        self,
        *,
        key_fn: Callable[[dict[str, Any]], str | None],
        entry_builder: Callable[[dict[str, Any], dict[str, Any] | None, str], dict[str, Any]],
        is_entry_active: Callable[[dict[str, Any]], bool],
        max_cache: int = 500,
        threshold: int = 25,
    ) -> None:
        self.key_fn = key_fn
        self.entry_builder = entry_builder
        self.is_entry_active = is_entry_active
        self.max_cache = int(max_cache)
        self.threshold = int(threshold)
        self.cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def load(self, cache: dict[str, dict[str, Any]]) -> None:
        self.cache = dict(cache or {})

    def update(self, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        now = self._now_iso()
        for item in items:
            key = self.key_fn(item)
            if not key:
                continue
            existing = self.cache.get(key)
            self.cache[key] = self.entry_builder(item, existing, now)

        self.cache = {k: v for k, v in self.cache.items() if self.is_entry_active(v)}
        if len(self.cache) > self.max_cache:
            ordered = sorted(self.cache.values(), key=lambda item: str(item.get("last_seen", "")))
            keep = ordered[-self.max_cache :]
            self.cache = {str(item.get("id")): item for item in keep if item.get("id")}
        return self.cache

    def pending_items(self) -> list[dict[str, Any]]:
        return list(self.cache.values())

    def ready(self) -> bool:
        return len(self.cache) >= self.threshold

    def mark_processed(self, items: list[dict[str, Any]], *, exhausted_field: str = "exhausted") -> None:
        for item in items:
            key = item.get("id")
            if not key:
                continue
            if key in self.cache:
                self.cache[key][exhausted_field] = True
        self.update([])

