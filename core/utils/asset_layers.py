"""
Asset layer definitions for L1 and L2 universes.

These helpers provide small, curated subsets of the full asset universe
so that agentic workflows can reason about:
- Layer 1 majors (BTC, ETH, SOL, etc.)
- Layer 2 tokens grouped by main network (e.g. ETH L2s)

They deliberately return base tickers (e.g. \"BTC\") while using
`core.models.asset_registry.get_assets()` to intersect with what the
forecasting API currently exposes/enables.
"""

from __future__ import annotations

from typing import Dict, List

from core.models.asset_registry import get_assets

# Conservative L1 universe: only majors that we expect to have
# good liquidity and forecasting coverage.
LAYER1_ASSETS: List[str] = [
    "BTC",
    "ETH",
    "SOL",
    "SUI",
    "ADA",
    "XRP",
    "AAVE",
]

# Layer 2 / ecosystem mappings by main network (base ticker form).
# These lists are intentionally small to avoid overflow; they can
# be extended as the forecasting backend adds coverage.
LAYER2_BY_NETWORK: Dict[str, List[str]] = {
    # Ethereum L2 / ecosystem tokens
    "ETH": [
        "OP",   # Optimism
        "ARB",  # Arbitrum
        "IMX",  # Immutable
        "MATIC",
    ],
    # Solana ecosystem
    "SOL": [
        "SAND",
        "GALA",
        "AXS",
        "MANA",
    ],
}


def _filter_enabled(bases: List[str]) -> List[str]:
    """Intersect a candidate base ticker list with currently enabled assets."""
    enabled = {asset.upper() for asset in get_assets()}
    return [b for b in bases if b.upper() in enabled]


def get_layer1_assets(enabled_only: bool = True) -> List[str]:
    """
    Return L1 base tickers.

    Args:
        enabled_only: If True, intersect with asset_registry.get_assets().
    """
    bases = list(LAYER1_ASSETS)
    return _filter_enabled(bases) if enabled_only else bases


def get_layer2_assets(network: str, enabled_only: bool = True) -> List[str]:
    """
    Return L2 base tickers for a given main network (e.g. \"ETH\", \"SOL\").

    Args:
        network: Main network base ticker (case-insensitive).
        enabled_only: If True, intersect with asset_registry.get_assets().
    """
    network_key = network.upper()
    bases = LAYER2_BY_NETWORK.get(network_key, [])
    return _filter_enabled(bases) if enabled_only else bases


