"""Gas parameter estimation for EIP-1559 chains."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GasQuote:
    gas: int
    max_priority_fee_per_gas: int
    max_fee_per_gas: int
    tx_type: int = 2

    def to_tx_params(self) -> dict[str, int]:
        return {
            "gas": self.gas,
            "maxPriorityFeePerGas": self.max_priority_fee_per_gas,
            "maxFeePerGas": self.max_fee_per_gas,
            "type": self.tx_type,
        }


class GasManager:
    def __init__(self, w3) -> None:
        self.w3 = w3

    def aggressive_fast(self, gas_limit: int, multiplier: float = 1.15) -> GasQuote:
        block = self.w3.eth.get_block("latest")
        base_fee = int(block.get("baseFeePerGas", 0) or 0)

        try:
            priority = int(self.w3.eth.max_priority_fee)
        except Exception:
            priority = 1_500_000_000

        boosted_priority = max(int(priority * multiplier), 1)
        max_fee = max(int(base_fee * multiplier + boosted_priority), boosted_priority)

        return GasQuote(
            gas=int(gas_limit),
            max_priority_fee_per_gas=boosted_priority,
            max_fee_per_gas=max_fee,
        )

    def has_balance_for_gas(self, sender: str, gas_quote: GasQuote) -> bool:
        balance = int(self.w3.eth.get_balance(sender))
        estimated = int(gas_quote.gas) * int(gas_quote.max_fee_per_gas)
        return balance >= estimated
