"""Polymarket router bindings."""

from __future__ import annotations

from collections.abc import Sequence

from api.router_registry.base import RouterBinding
from api.routers.polymarket import (
    analysis,
    auth,
    bets,
    chat,
    clob,
    config,
    decisions,
    logs,
    markets,
    monitoring,
    positions,
    results,
    rss_flux,
    settings,
    trades,
    ui as polymarket_ui,
)


def get_polymarket_router_bindings() -> Sequence[RouterBinding]:
    return (
        RouterBinding(markets.router, prefix="/api/polymarket", tags=("Polymarket Markets",)),
        RouterBinding(positions.router, prefix="/api/polymarket", tags=("Polymarket Positions",)),
        RouterBinding(trades.router, prefix="/api/polymarket", tags=("Polymarket Trades",)),
        RouterBinding(analysis.router, prefix="/api/polymarket", tags=("Polymarket Analysis",)),
        RouterBinding(decisions.router, prefix="/api/polymarket", tags=("Polymarket Decisions",)),
        RouterBinding(chat.router, prefix="/api/polymarket", tags=("Polymarket Chat",)),
        RouterBinding(config.router, prefix="/api/polymarket", tags=("Polymarket Config",)),
        RouterBinding(logs.router, prefix="/api/polymarket", tags=("Polymarket Logs",)),
        RouterBinding(settings.router, prefix="/api/polymarket", tags=("Polymarket Settings",)),
        RouterBinding(results.router, prefix="/api/polymarket", tags=("Polymarket Results",)),
        RouterBinding(monitoring.router, prefix="/api/polymarket", tags=("Polymarket Monitoring",)),
        RouterBinding(clob.router, prefix="/api/polymarket", tags=("Polymarket CLOB",)),
        RouterBinding(rss_flux.router, prefix="/api/polymarket", tags=("Polymarket Manager",)),
        RouterBinding(bets.router, prefix="/api/polymarket", tags=("Polymarket Bets",)),
        RouterBinding(auth.router, prefix="/api/polymarket", tags=("Polymarket Auth",)),
        RouterBinding(polymarket_ui.router, tags=("Polymarket UI",)),
    )
