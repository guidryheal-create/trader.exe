"""UviSwap client package."""

from core.clients.uviswap.client import (
    CHAIN_BY_ID,
    DEFAULT_PERMIT2,
    ETHEREUM_MAINNET,
    ROUTER_ADDRESSES,
    ChainConfig,
    UviSwapClient,
    UviSwapClientError,
    UniswapV4Client,
)
from core.clients.uviswap.swap import SwapPlan, SwapRequest
from core.clients.uviswap.models import (
    MarketContextModel,
    PoolModel,
    PoolSelectionModel,
    PoolTokenModel,
    PolywhalerAssetModel,
)

__all__ = [
    "CHAIN_BY_ID",
    "DEFAULT_PERMIT2",
    "ETHEREUM_MAINNET",
    "ROUTER_ADDRESSES",
    "ChainConfig",
    "SwapPlan",
    "SwapRequest",
    "PoolTokenModel",
    "PoolModel",
    "PoolSelectionModel",
    "PolywhalerAssetModel",
    "MarketContextModel",
    "UviSwapClient",
    "UviSwapClientError",
    "UniswapV4Client",
]
