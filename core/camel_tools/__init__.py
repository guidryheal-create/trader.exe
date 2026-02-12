"""
CAMEL-compatible tools for trading system operations.
"""
from core.camel_tools.api_forecasting_toolkit import APIForecastingToolkit
from core.camel_tools.polymarket_toolkit import EnhancedPolymarketToolkit, PolymarketToolkit
from core.camel_tools.blockscout_toolkit import BlockscoutMCPToolkit, get_blockscout_toolkit
from core.camel_tools.market_data_toolkit import MarketDataToolkit
from core.camel_tools.crypto_tools import CryptoTools
from core.camel_tools.guidry_stats_toolkit import GuidryStatsToolkit
from core.camel_tools.review_pipeline_toolkit import ReviewPipelineToolkit
from core.camel_tools.uviswap_toolkit import UviSwapToolkit
from core.camel_tools.watchlist_toolkit import WatchlistToolkit
from core.camel_tools.wallet_analysis_toolkit import WalletAnalysisToolkit
from core.camel_tools.auto_enhancement_toolkit import AutoEnhancementToolkit

try:
    from core.camel_tools.asknews_toolkit import AskNewsToolkit
except ImportError:  # pragma: no cover
    AskNewsToolkit = None  # type: ignore

try:
    from core.camel_tools.google_research_toolkit import GoogleResearchToolkit
except ImportError:  # pragma: no cover
    GoogleResearchToolkit = None  # type: ignore

__all__ = [
    "APIForecastingToolkit",
        "EnhancedPolymarketToolkit",
        "PolymarketToolkit",
    "BlockscoutMCPToolkit",
    "get_blockscout_toolkit",
    "MarketDataToolkit",
    "CryptoTools",
    "GuidryStatsToolkit",
    "ReviewPipelineToolkit",
    "UviSwapToolkit",
    "WatchlistToolkit",
    "WalletAnalysisToolkit",
    "AutoEnhancementToolkit",
]
