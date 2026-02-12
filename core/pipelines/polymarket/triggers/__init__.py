"""Polymarket trigger specifications and config adapters."""

from __future__ import annotations

from typing import Callable

from . import hybrid, interval, market, signal

Extractor = Callable[[dict], dict]
Applier = Callable[[dict, dict], dict]

_TRIGGER_EXTRACTORS: dict[str, Extractor] = {
    "interval": interval.extract,
    "signal": signal.extract,
    "market": market.extract,
    "hybrid": hybrid.extract,
}

_TRIGGER_APPLIERS: dict[str, Applier] = {
    "interval": interval.apply,
    "signal": signal.apply,
    "market": market.apply,
    "hybrid": hybrid.apply,
}

_registered = False


def ensure_registered() -> None:
    global _registered
    if _registered:
        return
    interval.register()
    signal.register()
    market.register()
    hybrid.register()
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
