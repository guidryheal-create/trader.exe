"""Registry for UI/API bot systems.

Centralizes discoverable bot panels so new systems (e.g. copy bot) can be
added in one place and reused by UI menu and API selectors.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotSystem:
    system_id: str
    label: str
    ui_path: str
    description: str


_SYSTEMS: tuple[BotSystem, ...] = (
    BotSystem(
        system_id="polymarket",
        label="Polymarket",
        ui_path="/ui/polymarket",
        description="Prediction market manager, analysis, and execution workflows.",
    ),
    BotSystem(
        system_id="dex",
        label="DEX",
        ui_path="/ui/dex",
        description="On-chain DEX manager with watchlist, wallet monitoring, and cycle execution.",
    ),
)


def list_bot_systems() -> list[BotSystem]:
    return list(_SYSTEMS)


def list_bot_system_ids() -> list[str]:
    return [item.system_id for item in _SYSTEMS]


def get_bot_system(system_id: str) -> BotSystem | None:
    normalized = str(system_id).strip().lower()
    for item in _SYSTEMS:
        if item.system_id == normalized:
            return item
    return None
