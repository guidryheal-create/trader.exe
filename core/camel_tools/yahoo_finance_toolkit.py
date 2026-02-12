"""
Yahoo Finance MCP Toolkit for CAMEL Agents.

Provides tools for querying financial news and market data via Yahoo Finance MCP.
Uses proper CAMEL toolkit patterns with BaseToolkit and FunctionTool.
Focuses on finance, business, and crypto-related data.
"""
from typing import Dict, Any, List, Optional
from core.logging import log
from core.config import settings
from core.clients.yahoo_finance_client import YahooFinanceMCPClient, YahooFinanceMCPError

try:
    from camel.toolkits.base import BaseToolkit
    from camel.toolkits.function_tool import FunctionTool
    from camel.logger import get_logger
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    BaseToolkit = object  # type: ignore
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False

logger = get_logger(__name__)


class YahooFinanceMCPToolkit(BaseToolkit):
    r"""A toolkit for interacting with Yahoo Finance MCP to get financial news and market data.
    
    Provides tools for:
    - Searching financial news articles
    - Getting real-time stock/crypto quotes
    - Retrieving historical price data
    """
    
    def __init__(self, timeout: Optional[float] = None):
        r"""Initializes the YahooFinanceMCPToolkit and sets up the Yahoo Finance client.
        
        Args:
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        config = {
            "command": settings.yahoo_finance_mcp_command,
            "args": settings.yahoo_finance_mcp_args,
            "timeout": 30.0,
            "retry_attempts": 3
        }
        self.yahoo_client = YahooFinanceMCPClient(config)
        self._initialized = False
    
    async def initialize(self):
        """Initialize the Yahoo Finance client connection."""
        if not self._initialized:
            # Test connection with a simple quote
            try:
                await self.yahoo_client.get_quote("BTC-USD")
                self._initialized = True
                log.info("Yahoo Finance MCP toolkit initialized")
            except Exception as e:
                log.warning(f"Yahoo Finance MCP initialization test failed: {e}")
                # Still mark as initialized to allow graceful degradation
                self._initialized = True
    
    def get_search_news_tool(self):
        """Get tool for searching financial news."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def search_financial_news(
            query: str,
            limit: int = 10
        ) -> Dict[str, Any]:
            """
            Search for financial news articles from Yahoo Finance.
            
            Retrieves recent news articles related to the search query, including
            headlines, summaries, publication dates, and source links. Focus on
            finance, business, and crypto-related news.
            
            Args:
                query: Search query (e.g., "Bitcoin", "crypto market", "BTC price", "Ethereum news")
                limit: Maximum number of results to return (1-50). Default: 10
            """
            await toolkit_instance.initialize()
            try:
                articles = await toolkit_instance.yahoo_client.search_news(query, limit=max(1, min(limit, 50)))
                return {
                    "success": True,
                    "query": query,
                    "articles": articles,
                    "count": len(articles)
                }
            except YahooFinanceMCPError as e:
                log.error(f"Yahoo Finance MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "query": query,
                    "articles": [],
                    "count": 0
                }
            except Exception as e:
                log.error(f"Error searching financial news: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "query": query,
                    "articles": [],
                    "count": 0
                }
        
        search_financial_news.__name__ = "search_financial_news"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(search_financial_news)
        
        # ✅ CRITICAL: Always override schema to ensure OpenAI compliance
        # OpenAI function schemas don't support 'default' in properties.
        # Optional parameters are those NOT in the 'required' array.
        # The function itself handles default values, not the schema.
        schema = {
            "type": "function",
            "function": {
                "name": search_financial_news.__name__,
                "description": search_financial_news.__doc__ or search_financial_news.__name__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'Bitcoin', 'crypto market', 'BTC price')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (1-50). Defaults to 10 if not specified.",
                        },
                    },
                    "required": ["query"],  # Only 'query' is required, 'limit' is optional
                },
            },
        }
        # ✅ Force schema override to ensure OpenAI receives correct schema
        tool.openai_tool_schema = schema
        return tool
    
    def get_quote_tool(self):
        """Get tool for getting stock/crypto quotes."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_financial_quote(
            symbol: str
        ) -> Dict[str, Any]:
            """
            Get real-time quote for a stock or cryptocurrency.
            
            Retrieves current price, volume, market cap, and other market data
            for the specified symbol.
            
            Args:
                symbol: Stock or crypto symbol (e.g., "BTC-USD", "AAPL", "ETH-USD")
            """
            await toolkit_instance.initialize()
            try:
                result = await toolkit_instance.yahoo_client.get_quote(symbol)
                return {
                    "success": True,
                    "symbol": symbol,
                    **result
                }
            except YahooFinanceMCPError as e:
                log.error(f"Yahoo Finance MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "symbol": symbol
                }
            except Exception as e:
                log.error(f"Error getting quote for {symbol}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "symbol": symbol
                }
        
        get_financial_quote.__name__ = "get_financial_quote"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_financial_quote)
        
        try:  # pragma: no cover - schema normalisation
            schema = dict(tool.get_openai_tool_schema())
        except Exception:
            schema = {
                "type": "function",
                "function": {
                    "name": get_financial_quote.__name__,
                    "description": get_financial_quote.__doc__ or get_financial_quote.__name__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Stock or crypto symbol (e.g., 'BTC-USD', 'AAPL', 'ETH-USD')"},
                        },
                        "required": ["symbol"],
                    },
                },
            }
        schema["function"]["name"] = get_financial_quote.__name__
        tool.openai_tool_schema = schema
        return tool
    
    def get_tools(self) -> List[FunctionTool]:
        r"""Returns a list of FunctionTool objects representing the
        functions in the toolkit.

        Returns:
            List[FunctionTool]: A list of FunctionTool objects
                representing the functions in the toolkit.
        """
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            logger.warning("CAMEL tools not available, returning empty list")
            return []
        
        return [
            self.get_search_news_tool(),
            self.get_quote_tool(),
            # get_historical_data_tool removed - not used
        ]
    
    def get_all_tools(self) -> List[FunctionTool]:
        """Alias for get_tools() for backward compatibility."""
        return self.get_tools()


# Global toolkit instance for backward compatibility
_toolkit_instance: Optional[YahooFinanceMCPToolkit] = None


def get_yahoo_finance_toolkit() -> YahooFinanceMCPToolkit:
    """Get or create the global Yahoo Finance toolkit instance."""
    global _toolkit_instance
    if _toolkit_instance is None:
        _toolkit_instance = YahooFinanceMCPToolkit()
    return _toolkit_instance


__all__ = ["YahooFinanceMCPToolkit", "get_yahoo_finance_toolkit"]
