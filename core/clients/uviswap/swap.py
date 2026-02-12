"""Swap planning structures and helper functions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.clients.uviswap.slippage import calculate_min_out


@dataclass(frozen=True)
class SwapRequest:
    token_in: str
    token_out: str
    amount_in: int
    slippage_bps: int = 25
    fee: int = 3_000
    estimated_gas_limit: int = 300_000
    value: int = 0


@dataclass
class SwapPlan:
    request: SwapRequest
    expected_out: int
    min_out: int
    nonce: int
    calldata: str
    tx: dict[str, Any]
    simulation_ok: bool
    simulation_result: Any


def compute_min_out(expected_out: int, slippage_bps: int) -> int:
    return calculate_min_out(expected_out=expected_out, slippage_bps=slippage_bps)
