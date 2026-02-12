"""UI/global router bindings."""

from __future__ import annotations

from collections.abc import Sequence

from api.router_registry.base import RouterBinding
from api.routers import ui_menu
from api.routers import system_settings as system_settings_router


def get_ui_router_bindings() -> Sequence[RouterBinding]:
    return (
        RouterBinding(system_settings_router.router, tags=("System Settings",)),
        RouterBinding(ui_menu.router, tags=("UI Menu",)),
    )
