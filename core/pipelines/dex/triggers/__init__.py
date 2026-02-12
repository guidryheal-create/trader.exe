"""DEX trigger specifications and config adapters."""

from __future__ import annotations

from typing import Callable

from . import interval, strategy, watchlist

Extractor = Callable[[dict], dict]
Applier = Callable[[dict, dict], dict]

_TRIGGER_EXTRACTORS: dict[str, Extractor] = {
    "cycle_interval": interval.extract,
    "watchlist": watchlist.extract,
    "strategy_feedback": strategy.extract,
}

_TRIGGER_APPLIERS: dict[str, Applier] = {
    "cycle_interval": interval.apply,
    "watchlist": watchlist.apply,
    "strategy_feedback": strategy.apply,
}

_registered = False


def ensure_registered() -> None:
    global _registered
    if _registered:
        return
    interval.register()
    watchlist.register()
    strategy.register()
    _registered = True


def list_triggers() -> list[str]:
    ensure_registered()
    return sorted(_TRIGGER_EXTRACTORS.keys())


def extract_trigger_settings(trigger: str, config: dict) -> dict:
    ensure_registered()
    extractor = _TRIGGER_EXTRACTORS.get(trigger)
    if not extractor:
        raise KeyError(trigger)
    return extractor(config)


def apply_trigger_settings(trigger: str, config: dict, payload: dict) -> dict:
    ensure_registered()
    applier = _TRIGGER_APPLIERS.get(trigger)
    if not applier:
        raise KeyError(trigger)
    return applier(config, payload)
