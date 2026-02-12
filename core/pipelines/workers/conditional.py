"""Conditional callback worker primitive."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable


class ConditionalCallbackWorker:
    """Fetch items, conditionally dispatch each item to an async callback."""

    def __init__(
        self,
        fetch_items: Callable[[], Iterable[Any] | Awaitable[Iterable[Any]]],
        on_item: Callable[[Any], Awaitable[None]],
        *,
        condition: Callable[[Any], bool] | None = None,
    ) -> None:
        self.fetch_items = fetch_items
        self.on_item = on_item
        self.condition = condition or (lambda _item: True)

    async def run_once(self) -> int:
        items = self.fetch_items()
        if hasattr(items, "__await__"):
            items = await items  # type: ignore[assignment]
        processed = 0
        for item in items or []:  # type: ignore[arg-type]
            if not self.condition(item):
                continue
            await self.on_item(item)
            processed += 1
        return processed

