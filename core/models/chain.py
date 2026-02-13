"""Typed chain/network models and default trading chain registry."""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator

ADDRESS_REGEX: Final[re.Pattern[str]] = re.compile(r"^0x[a-fA-F0-9]{40}$")


class ChainConfig(BaseModel):
    """Runtime chain configuration for Uniswap-based trading operations."""

    name: str
    chain_id: int
    universal_router: str
    pool_manager: str | None = None
    quoter: str | None = None
    permit2: str
    explorer_base_url: str | None = None
    is_testnet: bool = False

    model_config = {
        "frozen": True,
    }

    @field_validator("universal_router", "pool_manager", "quoter", "permit2")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not ADDRESS_REGEX.match(value):
            raise ValueError(f"Invalid Ethereum address: {value}")
        return value

    @field_validator("explorer_base_url")
    @classmethod
    def validate_explorer_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid explorer URL: {value}")
        return value.rstrip("/")

    def explorer_tx_url(self, tx_hash: str) -> str | None:
        if not self.explorer_base_url:
            return None
        return f"{self.explorer_base_url}/tx/{tx_hash}"

    def explorer_address_url(self, address: str) -> str | None:
        if not self.explorer_base_url:
            return None
        return f"{self.explorer_base_url}/address/{address}"


DEFAULT_PERMIT2: Final[str] = "0x000000000022D473030F116dDEE9F6B43aC78BA3"


TRADING_CHAIN_CONFIGS: dict[str, ChainConfig] = {
    "ethereum": ChainConfig(
        name="ethereum",
        chain_id=1,
        universal_router="0x66a9893cc07d91d95644aedd05d03f95e1dba8af",
        pool_manager="0x000000000004444c5dc75cB358380D2e3dE08A90",
        quoter="0x52f0e24d1c21c8a0cb1e5a5dd6198556bd9e1203",
        permit2=DEFAULT_PERMIT2,
        explorer_base_url="https://etherscan.io",
    ),
    "base": ChainConfig(
        name="base",
        chain_id=8453,
        universal_router="0x6ff5693b99212da76ad316178a184ab56d299b43",
        pool_manager="0x498581ff718922c3f8e6a244956af099b2652b2b",
        quoter="0x0d5e0f971ed27fbff6c2837bf31316121532048d",
        permit2=DEFAULT_PERMIT2,
        explorer_base_url="https://basescan.org",
    ),
    "optimism": ChainConfig(
        name="optimism",
        chain_id=10,
        universal_router="0x851116d9223fabed8e56c0e6b8ad0c31d98b3507",
        pool_manager="0x9a13f98cb987694c9f086b1f5eb990eea8264ec3",
        quoter="0x1f3131a13296fb91c90870043742c3cdbff1a8d7",
        permit2=DEFAULT_PERMIT2,
        explorer_base_url="https://optimistic.etherscan.io",
    ),
    "polygon": ChainConfig(
        name="polygon",
        chain_id=137,
        universal_router="0x1095692a6237d83c6a72f3f5efedb9a670c49223",
        pool_manager="0x67366782805870060151383f4bbff9dab53e5cd6",
        quoter="0xb3d5c3dfc3a7aebff71895a7191796bffc2c81b9",
        permit2=DEFAULT_PERMIT2,
        explorer_base_url="https://polygonscan.com",
    ),
    "arbitrum": ChainConfig(
        name="arbitrum",
        chain_id=42161,
        universal_router="0xa51afafe0263b40edaef0df8781ea9aa03e381a3",
        pool_manager="0x360e68faccca8ca495c1b759fd9eee466db9fb32",
        quoter="0x3972c00f7ed4885e145823eb7c655375d275a1c5",
        permit2=DEFAULT_PERMIT2,
        explorer_base_url="https://arbiscan.io",
    ),
}

CHAIN_KEY_BY_ID: dict[int, str] = {config.chain_id: key for key, config in TRADING_CHAIN_CONFIGS.items()}
