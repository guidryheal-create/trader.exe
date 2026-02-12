"""Slippage utilities."""

from __future__ import annotations


class SlippageError(ValueError):
    """Raised when invalid slippage values are supplied."""


def calculate_min_out(expected_out: int, slippage_bps: int) -> int:
    """Return minimum acceptable output amount using basis-points slippage."""
    if expected_out < 0:
        raise SlippageError("expected_out must be non-negative")
    if slippage_bps < 0 or slippage_bps > 10_000:
        raise SlippageError("slippage_bps must be in [0, 10000]")

    return int(expected_out * (10_000 - slippage_bps) / 10_000)


def adaptive_slippage(pair_type: str) -> int:
    pair = (pair_type or "").strip().lower()
    if pair == "stable":
        return 15
    if pair == "volatile":
        return 35
    return 25
