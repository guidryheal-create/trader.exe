"""DEX router bindings."""

from __future__ import annotations

from collections.abc import Sequence

from api.router_registry.base import RouterBinding
from api.routers.dex import (
    config as dex_config,
    history as dex_history,
    logs as dex_logs,
    monitoring as dex_monitoring,
    settings as dex_settings,
    ui as dex_ui,
)


def get_dex_router_bindings() -> Sequence[RouterBinding]:
    return (
        RouterBinding(dex_config.router, prefix="/api/dex", tags=("DEX Config",)),
        RouterBinding(dex_logs.router, prefix="/api/dex", tags=("DEX Logs",)),
        RouterBinding(dex_monitoring.router, prefix="/api/dex", tags=("DEX Monitoring",)),
        RouterBinding(dex_settings.router, prefix="/api/dex", tags=("DEX Settings",)),
        RouterBinding(dex_history.router, prefix="/api/dex", tags=("DEX History",)),
        RouterBinding(dex_ui.router, tags=("DEX UI",)),
    )
