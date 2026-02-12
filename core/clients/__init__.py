"""
Client package for agentic system trading.

Contains all external API clients and MCP clients.
"""

from .forecasting_client import ForecastingClient, ForecastingAPIError, AssetNotEnabledError
from .santiment_client import SantimentAPIClient, SantimentAPIError
from .yahoo_finance_client import YahooFinanceMCPClient, YahooFinanceMCPError
from .youtube_transcript_client import YouTubeTranscriptMCPClient, YouTubeTranscriptMCPError
from .blockscout_client import BlockscoutMCPClient, BlockscoutMCPError
from .polymarket_client import PolymarketClient

__all__ = [
    "ForecastingClient",
    "ForecastingAPIError",
    "AssetNotEnabledError",
    "SantimentAPIClient",
    "SantimentAPIError",
    "YahooFinanceMCPClient",
    "YahooFinanceMCPError",
    "YouTubeTranscriptMCPClient",
    "YouTubeTranscriptMCPError",
    "BlockscoutMCPClient",
    "BlockscoutMCPError",
    "DEXSimulatorError",
    "PolymarketClient",
]

