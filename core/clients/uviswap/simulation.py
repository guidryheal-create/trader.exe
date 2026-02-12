"""Transaction simulation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SimulationResult:
    ok: bool
    result: Any


def simulate_transaction(rpc, tx: dict[str, Any]) -> SimulationResult:
    try:
        result = rpc.simulate(tx)
        return SimulationResult(ok=True, result=result)
    except Exception as exc:
        return SimulationResult(ok=False, result=str(exc))
