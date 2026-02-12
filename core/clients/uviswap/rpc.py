"""RPC helpers for UviSwap/Uniswap operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web3 import Web3


class RPCError(Exception):
    """Raised when RPC interactions fail."""


@dataclass(frozen=True)
class RPCNetworkInfo:
    chain_id: int
    block_number: int


class RPC:
    """Thin wrapper around web3 provider with normalized error handling."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.w3 = Web3(Web3.HTTPProvider(url))
        if not self.w3.is_connected():
            raise RPCError(f"RPC connection failed for url={url}")

    @property
    def chain_id(self) -> int:
        return int(self.w3.eth.chain_id)

    def network_info(self) -> RPCNetworkInfo:
        return RPCNetworkInfo(
            chain_id=int(self.w3.eth.chain_id),
            block_number=int(self.w3.eth.block_number),
        )

    def nonce(self, address: str) -> int:
        try:
            return int(self.w3.eth.get_transaction_count(address, "pending"))
        except Exception as exc:
            raise RPCError(f"Failed to fetch nonce for {address}: {exc}") from exc

    def simulate(self, tx: dict[str, Any]) -> bytes:
        try:
            return self.w3.eth.call(tx)
        except Exception as exc:
            raise RPCError(f"Simulation failed: {exc}") from exc

    def send_raw(self, raw_tx: bytes):
        try:
            return self.w3.eth.send_raw_transaction(raw_tx)
        except Exception as exc:
            raise RPCError(f"Failed to send raw transaction: {exc}") from exc
