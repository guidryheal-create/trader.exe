"""Pydantic models for UviSwap client data structures."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PoolTokenModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    symbol: str


class PoolModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    token0: PoolTokenModel
    token1: PoolTokenModel
    createdAtTimestamp: int
    createdAtBlockNumber: int | str
    txCount: int | str
    volumeUSD: float
    totalValueLockedUSD: float

    @property
    def pair_symbol(self) -> str:
        return f"{self.token0.symbol.upper()}/{self.token1.symbol.upper()}"

    @property
    def created_at_iso(self) -> str:
        return datetime.fromtimestamp(int(self.createdAtTimestamp)).strftime("%Y-%m-%d %H:%M:%S")


class PoolSelectionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pair: str
    pool_address: str
    token0_symbol: str
    token0_address: str
    token1_symbol: str
    token1_address: str
    tvl_usd: float
    volume_usd: float
    tx_count: int
    created_at: str


class PolywhalerAssetModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price: float
    change24h: float
    trend: str


class MarketContextModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    polywhaler: dict[str, Any] = Field(default_factory=dict)
    last_polymarket_bet: dict[str, Any] | None = None
