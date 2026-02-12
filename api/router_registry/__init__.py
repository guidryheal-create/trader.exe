"""Composable router registry."""

from __future__ import annotations

from collections.abc import Sequence

from api.router_registry.base import RouterBinding
from api.router_registry.dex_registry import get_dex_router_bindings
from api.router_registry.polymarket_registry import get_polymarket_router_bindings
from api.router_registry.ui_registry import get_ui_router_bindings


def get_router_bindings() -> Sequence[RouterBinding]:
    return (
        *get_polymarket_router_bindings(),
        *get_dex_router_bindings(),
        *get_ui_router_bindings(),
    )


__all__ = ["RouterBinding", "get_router_bindings"]
