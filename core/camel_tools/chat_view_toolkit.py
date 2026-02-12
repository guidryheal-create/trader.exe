"""
Chat View Toolkit for CAMEL Agents.

Provides read-only tools for chat service to view:
- Agentic logs/conversations
- Wallet distributions
- Shared memory (workspace memory/RAG)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from camel.toolkits.base import BaseToolkit
    from camel.toolkits.function_tool import FunctionTool
    from camel.logger import get_logger
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:
    BaseToolkit = object  # type: ignore
    FunctionTool = None
    CAMEL_TOOLS_AVAILABLE = False

from core.logging import log
from core.redis_client import RedisClient
from core.memory.workspace_memory import WorkspaceMemory
from api.services.agentic_service import AgenticService
from api.services.wallet_service import WalletService

logger = get_logger(__name__)


class ChatViewToolkit(BaseToolkit):
    r"""A toolkit for read-only viewing of agentic data for chat service.
    
    Provides tools to view (not edit):
    - Agentic conversation logs
    - Wallet distributions
    - Shared workspace memory (RAG)
    """

    def __init__(self, redis_client_override=None, timeout: Optional[float] = None):
        r"""Initializes the ChatViewToolkit.
        
        Args:
            redis_client_override: Optional RedisClient instance for testing
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        if redis_client_override:
            self.redis = redis_client_override
        else:
            self.redis = RedisClient()
        self.workspace_memory = WorkspaceMemory(self.redis)
        self.agentic_service = AgenticService(self.redis)
        self.wallet_service = WalletService(self.redis)

    async def initialize(self) -> None:
        """Initialize the Redis client connection."""
        try:
            await self.redis.connect()
        except Exception as e:
            logger.debug(f"Redis connection in ChatViewToolkit: {e}")

    def view_agentic_logs(
        self,
        ticker: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """View agentic conversation logs (read-only).
        
        Retrieves agentic decision logs from Redis. This is a read-only operation.
        Chat history is NOT inserted into workforce memory system.
        
        Args:
            ticker: Optional ticker filter (e.g., "BTC-USD"). If None, returns logs for all tickers.
            limit: Maximum number of logs to return. Default: 10
        
        Returns:
            Dictionary with success status and list of conversations
        """
        import asyncio
        
        async def _async_view():
            try:
                await self.redis.connect()
                
                # Use agentic_service to get conversations
                response = await self.agentic_service.get_conversations(
                    ticker=ticker,
                    limit=limit,
                    request_id="chat_view"
                )
                
                # Convert to simple format for chat
                conversations = []
                for conv in response.conversations[:limit]:
                    conversations.append({
                        "decision_id": conv.decision_id,
                        "ticker": conv.ticker,
                        "timestamp": conv.timestamp,
                        "interval": conv.interval,
                        "title": getattr(conv, "title", None),
                        "user_explanation": getattr(conv, "user_explanation", None),
                        "final_decision": {
                            "action": conv.final_decision.action if conv.final_decision else "HOLD",
                            "confidence": conv.final_decision.confidence if conv.final_decision else 0.0,
                            "explanation": conv.final_decision.explanation if conv.final_decision else ""
                        },
                        "tags": getattr(conv, "tags", []),
                        "source": getattr(conv, "source", "agentic_workforce")
                    })
                
                return {
                    "success": True,
                    "conversations": conversations,
                    "count": len(conversations)
                }
            except Exception as e:
                log.error(f"Error viewing agentic logs: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "conversations": []
                }
        
        # Run async function
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, _async_view())
                    return future.result(timeout=10)
            else:
                return asyncio.run(_async_view())
        except RuntimeError:
            return asyncio.run(_async_view())

    def view_wallet_distribution(
        self,
        strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """View wallet distribution (read-only).
        
        Retrieves the latest wallet distribution from Redis. This is a read-only operation.
        
        Args:
            strategy: Optional strategy filter (e.g., "wallet_balancing"). If None, returns latest distribution.
        
        Returns:
            Dictionary with success status and wallet distribution data
        """
        import asyncio
        
        async def _async_view():
            try:
                await self.redis.connect()
                
                # Use wallet_service to get distribution
                result = await self.wallet_service.get_distribution(strategy=strategy)
                
                if result and result.get("distributions"):
                    # Return the first/latest distribution
                    latest = result["distributions"][0] if result["distributions"] else {}
                    return {
                        "success": True,
                        "wallet_distribution": latest.get("wallet_distribution", {}),
                        "reserve_pct": latest.get("reserve_pct", 0.1),
                        "ai_explanation": latest.get("ai_explanation", ""),
                        "strategy": latest.get("strategy", strategy or "unknown"),
                        "timestamp": latest.get("timestamp", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": "No wallet distribution found",
                        "wallet_distribution": {}
                    }
            except Exception as e:
                log.error(f"Error viewing wallet distribution: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "wallet_distribution": {}
                }
        
        # Run async function
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, _async_view())
                    return future.result(timeout=10)
            else:
                return asyncio.run(_async_view())
        except RuntimeError:
            return asyncio.run(_async_view())

    def read_shared_memory(
        self,
        ticker: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Read shared workspace memory (RAG) for a ticker (read-only).
        
        Retrieves workspace memory records for a ticker. This is a read-only operation.
        Chat history is NOT inserted into workspace memory.
        
        Args:
            ticker: Ticker symbol (e.g., "BTC-USD")
            limit: Maximum number of records to return. Default: 10
        
        Returns:
            Dictionary with success status and list of memory records
        """
        import asyncio
        
        async def _async_read():
            try:
                await self.redis.connect()
                
                # Use workspace_memory to read records (weighted RAG)
                records = await self.workspace_memory.read_records_weighted(ticker=ticker, limit=limit)
                
                return {
                    "success": True,
                    "ticker": ticker,
                    "records": records,
                    "count": len(records)
                }
            except Exception as e:
                log.error(f"Error reading shared memory for {ticker}: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "records": []
                }
        
        # Run async function
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, _async_read())
                    return future.result(timeout=10)
            else:
                return asyncio.run(_async_read())
        except RuntimeError:
            return asyncio.run(_async_read())

    def get_tools(self) -> List[FunctionTool]:
        """Returns a list of FunctionTool objects for chat view operations."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            logger.warning("CAMEL tools not available, returning empty list")
            return []
        
        toolkit_instance = self
        
        # View agentic logs tool
        def view_agentic_logs(
            ticker: str = "",
            limit: int = 10
        ) -> Dict[str, Any]:
            """View agentic conversation logs (read-only). Retrieves agentic decision logs from Redis. Chat history is NOT inserted into workforce memory system.
            
            Args:
                ticker: Optional ticker filter (e.g., "BTC-USD"). Leave empty for all tickers.
                limit: Maximum number of logs to return (default: 10)
            """
            return toolkit_instance.view_agentic_logs(
                ticker=ticker if ticker else None,
                limit=limit
            )
        
        view_agentic_logs.__name__ = "view_agentic_logs"
        from core.camel_tools.async_wrapper import create_function_tool
        
        explicit_schema_logs = {
            "type": "function",
            "function": {
                "name": "view_agentic_logs",
                "description": "View agentic conversation logs (read-only). Retrieves agentic decision logs from Redis. Chat history is NOT inserted into workforce memory system.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Optional ticker filter (e.g., 'BTC-USD'). Leave empty string for all tickers."
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of logs to return (default: 10)",
                            "minimum": 1,
                            "maximum": 50
                        }
                    },
                    "required": ["ticker", "limit"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        view_logs_tool = create_function_tool(view_agentic_logs, explicit_schema=explicit_schema_logs)
        
        # View wallet distribution tool
        def view_wallet_distribution(
            strategy: str = ""
        ) -> Dict[str, Any]:
            """View wallet distribution (read-only). Retrieves the latest wallet distribution from Redis.
            
            Args:
                strategy: Optional strategy filter (e.g., 'wallet_balancing'). Leave empty for latest.
            """
            return toolkit_instance.view_wallet_distribution(
                strategy=strategy if strategy else None
            )
        
        view_wallet_distribution.__name__ = "view_wallet_distribution"
        
        explicit_schema_wallet = {
            "type": "function",
            "function": {
                "name": "view_wallet_distribution",
                "description": "View wallet distribution (read-only). Retrieves the latest wallet distribution from Redis.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "strategy": {
                            "type": "string",
                            "description": "Optional strategy filter (e.g., 'wallet_balancing'). Leave empty string for latest distribution."
                        }
                    },
                    "required": ["strategy"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        view_wallet_tool = create_function_tool(view_wallet_distribution, explicit_schema=explicit_schema_wallet)
        
        # Read shared memory tool
        def read_shared_memory(
            ticker: str,
            limit: int = 10
        ) -> Dict[str, Any]:
            """Read shared workspace memory (RAG) for a ticker (read-only). Retrieves workspace memory records. Chat history is NOT inserted into workspace memory.
            
            Args:
                ticker: Ticker symbol (e.g., 'BTC-USD')
                limit: Maximum number of records to return (default: 10)
            """
            return toolkit_instance.read_shared_memory(ticker=ticker, limit=limit)
        
        read_shared_memory.__name__ = "read_shared_memory"
        
        explicit_schema_memory = {
            "type": "function",
            "function": {
                "name": "read_shared_memory",
                "description": "Read shared workspace memory (RAG) for a ticker (read-only). Retrieves workspace memory records. Chat history is NOT inserted into workspace memory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Ticker symbol (e.g., 'BTC-USD')"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of records to return (default: 10)",
                            "minimum": 1,
                            "maximum": 50
                        }
                    },
                    "required": ["ticker", "limit"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        read_memory_tool = create_function_tool(read_shared_memory, explicit_schema=explicit_schema_memory)
        
        return [
            view_logs_tool,
            view_wallet_tool,
            read_memory_tool,
        ]


__all__ = ["ChatViewToolkit"]

