"""
Market Data Toolkit for CAMEL

Provides CAMEL-compatible tools for retrieving market data and performing analysis.
"""
from typing import Dict, Any, List, Optional, Annotated
from pydantic import Field
from core.settings.config import settings
from core.logging import log
from core.clients.forecasting_client import ForecastingClient

try:
    from camel.toolkits import FunctionTool  # type: ignore
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False
    log.warning("CAMEL function tools not available. Install with: pip install 'camel-ai[tools]'")


class MarketDataToolkit:
    """Toolkit for market data retrieval and analysis."""
    
    def __init__(self, forecasting_client: Optional[ForecastingClient] = None):
        """
        Initialize the toolkit.
        
        Args:
            forecasting_client: Optional ForecastingClient instance
        """
        self.forecasting_client = forecasting_client or ForecastingClient({
            "base_url": settings.mcp_api_url,
            "api_key": settings.mcp_api_key,
            "mock_mode": settings.use_mock_services,
        })
    
    async def initialize(self):
        """Initialize the forecasting client."""
        await self.forecasting_client.connect()
    
    def get_ticker_info_tool(self):
        """Get tool for retrieving ticker information."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_ticker_info(
            ticker: Annotated[str, Field(description="Stock ticker symbol (e.g., BTC-USD or BTC). DO NOT use 'PORTFOLIO' or 'portfolio' as a ticker - query individual tickers only.")]
        ) -> Dict[str, Any]:
            """
            Get detailed information about a specific ticker.
            
            **CRITICAL**: This tool only works with individual ticker symbols (BTC, ETH, SOL, etc.).
            DO NOT query 'PORTFOLIO' or 'portfolio' as a ticker - it will fail.
            For portfolio-level analysis, aggregate data from individual tickers.
            
            Args:
                ticker: Stock ticker symbol (e.g., BTC, ETH, BTC-USD, ETH-USD)
                
            Returns:
                Ticker information including available intervals and metadata
            """
            try:
                # ✅ CRITICAL: Reject invalid tickers like "PORTFOLIO" early
                normalized = ticker.upper().replace("-USD", "").strip()
                if not normalized or normalized in ["PORTFOLIO", "PORT", "ALL", "TOTAL"]:
                    return {
                        "success": False,
                        "error": f"Invalid ticker symbol: '{ticker}'. This tool only works with individual ticker symbols (BTC, ETH, SOL, etc.). DO NOT query 'PORTFOLIO' as a ticker. For portfolio analysis, query individual tickers and aggregate the results.",
                        "ticker": ticker,
                        "info": {}
                    }
                
                api_ticker = f"{normalized}-USD"
                # ✅ CRITICAL: Handle event loop closure errors gracefully
                try:
                    result = await toolkit_instance.forecasting_client.get_ticker_info(api_ticker)
                except RuntimeError as loop_error:
                    if "Event loop is closed" in str(loop_error):
                        log.error(f"[MarketDataToolkit] Event loop closed during get_ticker_info for {ticker}")
                        return {
                            "success": False,
                            "error": "Event loop closed during request. This may happen during concurrent operations. Please retry.",
                            "ticker": ticker,
                            "info": {}
                        }
                    raise
                
                return {
                    "success": True,
                    "ticker": ticker,
                    "info": result
                }
            except Exception as e:
                error_msg = str(e)
                # Provide helpful error message for common mistakes
                if "PORTFOLIO" in error_msg.upper() or "not found" in error_msg.lower():
                    return {
                        "success": False,
                        "error": f"Ticker '{ticker}' not found. This tool only works with individual ticker symbols (BTC, ETH, SOL, etc.). DO NOT query 'PORTFOLIO' as a ticker. For portfolio analysis, query individual tickers (BTC, ETH, etc.) and aggregate the results.",
                        "ticker": ticker,
                        "info": {}
                    }
                log.error(f"Error getting ticker info: {e}")
                return {
                    "success": False,
                    "error": f"Failed to get ticker info: {e}",
                    "ticker": ticker,
                    "info": {}
                }
        
        get_ticker_info.__name__ = "get_ticker_info"
        get_ticker_info.__doc__ = "Get detailed information about a ticker including available intervals"
        return get_ticker_info
    
    def get_all_tools(self) -> List:
        """Get all tools in this toolkit."""
        # No tools are exposed at the moment since the lightweight interval tool was removed.
        return []

    @staticmethod
    def _wrap_tool(func):
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools not installed")

        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(func)
        try:
            schema = dict(tool.get_openai_tool_schema())
        except Exception:
            schema = {
                "type": "function",
                "function": {
                    "name": func.__name__,
                    "description": func.__doc__ or func.__name__,
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }

        function_schema = schema.setdefault("function", {})
        function_schema["name"] = func.__name__
        function_schema.setdefault("description", func.__doc__ or func.__name__)
        tool.openai_tool_schema = schema
        return tool

