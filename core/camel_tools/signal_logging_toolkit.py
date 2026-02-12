"""
CAMEL toolkit for logging buy/sell signals to frontend.

Pure CAMEL tool that agents can use to log trading signals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

try:
    from camel.toolkits.base import BaseToolkit
    from camel.toolkits.function_tool import FunctionTool
    from camel.logger import get_logger
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:
    BaseToolkit = object  # type: ignore
    FunctionTool = None
    CAMEL_TOOLS_AVAILABLE = False

from core.redis_client import redis_client
from core.logging import log

logger = get_logger(__name__)


class SignalLoggingToolkit(BaseToolkit):
    r"""A toolkit for logging buy/sell signals to frontend.
    
    This toolkit allows agents to log trading signals (BUY/SELL/HOLD) to Redis
    for frontend display and API access.
    """

    def __init__(self, redis_client_override=None, timeout: Optional[float] = None):
        r"""Initializes the SignalLoggingToolkit and sets up the Redis client.
        
        Args:
            redis_client_override: Optional RedisClient instance for testing
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        # Use a fresh RedisClient instance to avoid cross-event-loop issues.
        # If an override is provided (for testing), use it.
        if redis_client_override:
            self.redis = redis_client_override
        else:
            from core.redis_client import RedisClient
            self.redis = RedisClient()

    async def initialize(self) -> None:
        """Initialize the Redis client connection."""
        try:
            await self.redis.connect()
        except Exception as e:
            logger.debug(f"Redis connection in SignalLoggingToolkit: {e}")

    def get_log_signal_tool(self):
        """Get tool for logging buy/sell signals."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools not installed")

        async def log_trading_signal(
            ticker: str,
            signal: str,  # BUY, SELL, HOLD
            confidence: float,
            source: str = "agentic",
            explanation: str = "",
        ) -> Dict[str, Any]:
            """
            Log a trading signal (BUY/SELL/HOLD) to frontend.

            Args:
                ticker: Crypto ticker symbol (e.g., BTC, ETH)
                signal: Signal type (BUY, SELL, or HOLD)
                confidence: Confidence score (0.0 to 1.0)
                source: Signal source (default: "agentic")
                explanation: Human-readable explanation

            Returns:
                Dictionary with success status and signal ID
            """
            try:
                signal_upper = signal.upper()
                if signal_upper not in ["BUY", "SELL", "HOLD"]:
                    return {
                        "success": False,
                        "error": f"Invalid signal: {signal}. Must be BUY, SELL, or HOLD",
                    }

                ticker_upper = ticker.upper()
                timestamp = datetime.now(timezone.utc)
                signal_id = f"signal_{ticker_upper}_{signal_upper}_{int(timestamp.timestamp())}"

                signal_data = {
                    "ticker": ticker_upper,
                    "signal": signal_upper,
                    "confidence": float(confidence),
                    "source": source,
                    "explanation": explanation,
                    "timestamp": timestamp.isoformat(),
                    "signal_id": signal_id,
                }

                # ✅ FIXED: Create fresh Redis client in thread-local event loop to avoid cross-loop issues
                from core.redis_client import RedisClient
                thread_redis = RedisClient()
                await thread_redis.connect()

                # Store in Redis for frontend
                key = f"signals:{ticker_upper}:{signal_upper}"
                await thread_redis.set_json(key, signal_data, expire=86400 * 7)  # 7 days

                # Also store in signals list for frontend
                signals_list_key = f"signals:list:{signal_upper}"
                await thread_redis.lpush(signals_list_key, signal_id)
                await thread_redis.expire(signals_list_key, 86400 * 7)

                # Store full signal data
                signal_detail_key = f"signal:detail:{signal_id}"
                await thread_redis.set_json(signal_detail_key, signal_data, expire=86400 * 7)

                log.info(f"📊 SIGNAL LOGGED: {signal_upper} {ticker_upper} @ {confidence:.2%} ({source})")

                return {
                    "success": True,
                    "signal_id": signal_id,
                    "ticker": ticker_upper,
                    "signal": signal_upper,
                    "confidence": confidence,
                }
            except Exception as e:
                log.error(f"Failed to log signal: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                }

        # Use asyncio.to_thread pattern like CAMEL example
        import asyncio
        from typing import Optional
        
        def sync_log_trading_signal(
            ticker: str,
            signal: str,
            confidence: float,
            source: Optional[str] = "agentic",
            explanation: Optional[str] = "",
        ) -> Dict[str, Any]:
            """Synchronous wrapper for log_trading_signal."""
            # ✅ FIXED: Use proper async handling to avoid event loop conflicts
            async def _async_log():
                return await log_trading_signal(ticker, signal, confidence, source or "agentic", explanation or "")
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in async context - use ThreadPoolExecutor to run in separate thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        def run_in_thread():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                return new_loop.run_until_complete(_async_log())
                            finally:
                                new_loop.close()
                        
                        future = executor.submit(run_in_thread)
                        return future.result(timeout=10.0)
                else:
                    # No running loop - safe to use asyncio.run
                    return asyncio.run(_async_log())
            except RuntimeError:
                # No event loop at all - create one
                return asyncio.run(_async_log())
        
        sync_log_trading_signal.__name__ = "log_trading_signal"
        sync_log_trading_signal.__doc__ = log_trading_signal.__doc__
        
        # ✅ CAMEL NATIVE: Create FunctionTool and manually set explicit schema
        tool = FunctionTool(sync_log_trading_signal)
        
        try:
            # Manually set schema to ensure valid OpenAI schema
            schema = {
                "type": "function",
                "function": {
                    "name": "log_trading_signal",
                    "description": (
                        "Log a trading signal (BUY/SELL/HOLD) to frontend. "
                        "Stores the signal in Redis for frontend/API access."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Crypto ticker symbol (e.g., BTC, ETH)"
                            },
                            "signal": {
                                "type": "string",
                                "description": "Signal type (BUY, SELL, or HOLD)"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score (0.0 to 1.0)",
                            },
                            "source": {
                                "type": "string",
                                "description": "Signal source (default: 'agentic')"
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Human-readable explanation (default: empty string)"
                            },
                        },
                        "required": ["ticker", "signal", "confidence"],
                        "additionalProperties": False,
                    },
                },
            }
            tool.openai_tool_schema = schema
            logger.debug("✅ Set explicit schema for log_trading_signal")
        except Exception as e:
            logger.warning(f"Could not set explicit schema for log_trading_signal: {e}")
        
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
        return [self.get_log_signal_tool()]
    
    def get_all_tools(self) -> List[FunctionTool]:
        """Alias for get_tools() for backward compatibility."""
        return self.get_tools()


__all__ = ["SignalLoggingToolkit"]

