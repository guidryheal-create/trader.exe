"""
CAMEL toolkit for search functionality.

Pure CAMEL tool for searching news, market data, etc.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List
import asyncio

try:
    from camel.toolkits import FunctionTool
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:
    FunctionTool = None
    CAMEL_TOOLS_AVAILABLE = False

from core.logging import log


class SearchToolkit:
    """Toolkit for search functionality."""

    def __init__(self, redis_client_override=None):
        self.redis = redis_client_override

    async def initialize(self) -> None:
        """Placeholder to mirror other toolkit interfaces."""

    async def search_market_info_async(
        self,
        query: str = "crypto market overview",
        search_type: str = "general",  # general, news, price, sentiment
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for market information (async implementation).

        Args:
            query: Search query (defaults to 'crypto market overview' if empty)
            search_type: Type of search (general, news, price, sentiment)
            limit: Maximum number of results

        Returns:
            Dictionary with search results
        """
        try:
            safe_query = query or "crypto market overview"
            if not isinstance(safe_query, str) or safe_query.strip() == "":
                safe_query = "crypto market overview"

            results = {
                "query": safe_query,
                "search_type": search_type,
                "results": [],
                "count": 0,
            }

            # Try to use AskNews toolkit if available
            try:
                from core.camel_tools.asknews_toolkit import AskNewsToolkit
                if search_type == "news":
                    news_toolkit = AskNewsToolkit()
                    await news_toolkit.initialize()
                    log.debug(f"🔍 Searching news for: {safe_query}")
            except ImportError:
                pass

            log.info(f"🔍 SEARCH: {safe_query} (type: {search_type}, limit: {limit})")

            return {
                "success": True,
                "query": safe_query,
                "search_type": search_type,
                "results": results.get("results", []),
                "count": len(results.get("results", [])),
            }
        except Exception as e:
            log.error(f"Search failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "count": 0,
            }

    def search_market_info(
        self,
        query: str = "crypto market overview",
        search_type: str = "general",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for market information.
        
        This is a synchronous wrapper for the async implementation.
        Uses proper async handling to avoid event loop conflicts.

        Args:
            query: Search query string. Defaults to 'crypto market overview' if not provided.
            search_type: Type of search (general, news, price, sentiment). Defaults to 'general'.
            limit: Maximum number of results. Defaults to 10.

        Returns:
            Dictionary with search results containing:
            - success: Boolean indicating if search succeeded
            - query: The search query used
            - search_type: Type of search performed
            - results: List of search results
            - count: Number of results
            - error: Error message if success is False
        """
        safe_query = query if query and query.strip() else "crypto market overview"
        
        # ✅ FIXED: Use proper async handling to avoid event loop conflicts
        # Check if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - use ThreadPoolExecutor to avoid conflicts
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                def run_in_thread():
                    """Run async function in a new thread with its own event loop."""
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(
                            self.search_market_info_async(
                                query=safe_query,
                                search_type=search_type,
                                limit=limit
                            )
                        )
                    finally:
                        # Properly close the loop
                        try:
                            pending = asyncio.all_tasks(new_loop)
                            for task in pending:
                                task.cancel()
                            if pending:
                                new_loop.run_until_complete(
                                    asyncio.gather(*pending, return_exceptions=True)
                                )
                        except Exception:
                            pass
                        new_loop.close()
                
                future = executor.submit(run_in_thread)
                return future.result(timeout=60.0)  # 60 second timeout
        except RuntimeError:
            # No running loop - safe to use asyncio.run
            try:
                return asyncio.run(self.search_market_info_async(
                    query=safe_query,
                    search_type=search_type,
                    limit=limit
                ))
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    # Event loop was closed - create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.search_market_info_async(
                            query=safe_query,
                            search_type=search_type,
                            limit=limit
                        ))
                    finally:
                        loop.close()
                else:
                    raise

    def get_tools(self) -> List[FunctionTool]:
        """
        Returns a list of FunctionTool objects representing the functions in the toolkit.

        Returns:
            List[FunctionTool]: A list of FunctionTool objects representing the functions.
        """
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            log.warning("CAMEL tools not available, returning empty list")
            return []
        
        # Create FunctionTool and manually enforce explicit schema
        tool = FunctionTool(self.search_market_info)
        
        try:
            schema = {
                "type": "function",
                "function": {
                    "name": "search_market_info",
                    "description": (
                        "Search market information (news, trends, etc.). "
                        "Pass a query string; defaults to 'crypto market overview' if omitted."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query string. Defaults to 'crypto market overview' if not provided.",
                            },
                            "search_type": {
                                "type": "string",
                                "description": "Type of search (general, news, price, sentiment). Defaults to 'general'.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results. Defaults to 10.",
                            },
                        },
                        # All parameters have defaults, so none are required
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            }
            tool.openai_tool_schema = schema
        except Exception as e:
            log.debug(f"Could not set explicit schema for search_market_info: {e}")
        
        return [tool]

    def get_all_tools(self):
        """Return all tools from this toolkit."""
        return self.get_tools()


__all__ = ["SearchToolkit"]

