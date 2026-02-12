"""Universal router transaction helper."""

from __future__ import annotations

from typing import Any


class Router:
    def __init__(self, contract) -> None:
        self.contract = contract

    @property
    def address(self) -> str:
        return str(self.contract.address)

    def encode_execute(self, commands: bytes, inputs: list[bytes], deadline: int | None = None) -> str:
        args = [commands, inputs] if deadline is None else [commands, inputs, int(deadline)]
        if hasattr(self.contract, "encode_abi"):
            return self.contract.encode_abi("execute", args=args)
        return self.contract.encodeABI(fn_name="execute", args=args)

    def build_swap_tx(
        self,
        sender: str,
        calldata: str,
        nonce: int,
        gas_params: dict[str, Any],
        value: int = 0,
        chain_id: int | None = None,
    ) -> dict[str, Any]:
        tx = {
            "from": sender,
            "to": self.contract.address,
            "data": calldata,
            "value": int(value),
            "nonce": int(nonce),
            **gas_params,
        }
        if chain_id is not None:
            tx["chainId"] = int(chain_id)
        return tx
