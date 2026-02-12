"""Permit2 and ERC20 approval helpers."""

from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3


PERMIT2_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [
            {"internalType": "uint160", "name": "amount", "type": "uint160"},
            {"internalType": "uint48", "name": "expiration", "type": "uint48"},
            {"internalType": "uint48", "name": "nonce", "type": "uint48"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]

ERC20_APPROVE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class Permit2Error(Exception):
    """Raised on Permit2 operations failures."""


@dataclass(frozen=True)
class Permit2Allowance:
    amount: int
    expiration: int
    nonce: int


class Permit2Client:
    """Helper for ERC20 approvals through Permit2."""

    def __init__(self, w3: Web3, permit2_address: str) -> None:
        self.w3 = w3
        self.address = Web3.to_checksum_address(permit2_address)
        self.contract = self.w3.eth.contract(address=self.address, abi=PERMIT2_ABI)

    def get_allowance(self, owner: str, token: str, spender: str) -> Permit2Allowance:
        try:
            amount, expiration, nonce = self.contract.functions.allowance(
                Web3.to_checksum_address(owner),
                Web3.to_checksum_address(token),
                Web3.to_checksum_address(spender),
            ).call()
            return Permit2Allowance(amount=int(amount), expiration=int(expiration), nonce=int(nonce))
        except Exception as exc:
            raise Permit2Error(f"Failed to read Permit2 allowance: {exc}") from exc

    def needs_erc20_approval(self, owner: str, token: str, min_allowance: int | None = None) -> bool:
        token_contract = self.w3.eth.contract(address=Web3.to_checksum_address(token), abi=ERC20_APPROVE_ABI)
        current_allowance = int(token_contract.functions.allowance(
            Web3.to_checksum_address(owner),
            self.address,
        ).call())

        threshold = int(min_allowance) if min_allowance is not None else (2**200)
        return current_allowance < threshold

    def build_erc20_approve_tx(
        self,
        token: str,
        owner: str,
        nonce: int,
        gas_params: dict[str, int],
        amount: int | None = None,
        chain_id: int | None = None,
    ) -> dict[str, int | str]:
        token_contract = self.w3.eth.contract(address=Web3.to_checksum_address(token), abi=ERC20_APPROVE_ABI)
        max_amount = int(amount) if amount is not None else (2**256 - 1)
        tx = token_contract.functions.approve(self.address, max_amount).build_transaction(
            {
                "from": Web3.to_checksum_address(owner),
                "nonce": int(nonce),
                "value": 0,
                **gas_params,
            }
        )
        if chain_id is not None:
            tx["chainId"] = int(chain_id)
        return tx
