"""Quote helpers for Uniswap quoter contracts."""

from __future__ import annotations

from web3 import Web3


class QuoteError(Exception):
    """Raised when quote retrieval fails."""


class Quoter:
    def __init__(self, w3: Web3, quoter_contract) -> None:
        self.w3 = w3
        self.contract = quoter_contract

    def quote_exact_in(self, token_in: str, token_out: str, amount_in: int, fee: int = 3_000) -> int:
        try:
            amount_out = self.contract.functions.quoteExactInputSingle(
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out),
                int(amount_in),
                int(fee),
            ).call()
            return int(amount_out)
        except Exception as exc:
            raise QuoteError(f"quote_exact_in failed: {exc}") from exc
