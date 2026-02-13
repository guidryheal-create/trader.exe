"""
Santiment API Toolkit for CAMEL Agents.

Provides tools for querying cryptocurrency sentiment, social volume, social dominance,
and trending words via Santiment GraphQL API.
Uses proper CAMEL toolkit patterns with BaseToolkit and FunctionTool.
"""
from typing import Dict, Any, List, Optional
from core.logging import log
from core.settings.config import settings
from core.clients.santiment_client import SantimentAPIClient, SantimentAPIError

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


class SantimentToolkit(BaseToolkit):
    r"""A toolkit for interacting with Santiment API to get cryptocurrency sentiment and social metrics.
    
    Provides tools for:
    - Getting sentiment balance for assets
    - Getting social volume (mentions) for assets
    - Getting social dominance (share of discussions) for assets
    - Detecting significant shifts in social volume
    - Getting trending words in crypto space
    """
    
    def __init__(self, timeout: Optional[float] = None):
        r"""Initializes the SantimentToolkit and sets up the Santiment API client.
        
        Args:
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        config = {
            "api_key": getattr(settings, 'sentiment_api_key', None),
            "timeout": 30.0,
            "retry_attempts": 3
        }
        try:
            self.santiment_client = SantimentAPIClient(config)
            self._initialized = False
        except (ValueError, Exception) as e:
            log.debug(f"Santiment API client not initialized (API key may not be set): {e}")
            self.santiment_client = None
            self._initialized = False
    
    async def initialize(self):
        """Initialize the Santiment API client connection."""
        if not self._initialized and self.santiment_client:
            # Test connection with a simple query
            try:
                # Try to get trending words as a lightweight test
                await self.santiment_client.get_trending_words(days=1, top_n=1)
                self._initialized = True
                log.info("Santiment API toolkit initialized")
            except Exception as e:
                log.warning(f"Santiment API initialization test failed: {e}")
                # Still mark as initialized to allow graceful degradation
                self._initialized = True
    
    def get_sentiment_balance_tool(self):
        """Get tool for retrieving sentiment balance."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_sentiment_balance(
            asset: str
        ) -> Dict[str, Any]:
            """
            Retrieve the sentiment balance (sentiment_balance_total) for a given cryptocurrency asset.
            
            The sentiment balance represents positive sentiment minus negative sentiment.
            Uses a fixed 1-day period (latest data only) for FREE tier compatibility.
            
            Args:
                asset: The cryptocurrency slug (e.g., "bitcoin", "ethereum", "solana"). Required.
            """
            # Fixed low value for FREE tier compatibility (1 day - latest data only)
            days = 1
            
            if not toolkit_instance.santiment_client:
                return {
                    "success": False,
                    "error": "Santiment API client not initialized. Check SENTIMENT_API environment variable.",
                    "asset": asset
                }
            
            await toolkit_instance.initialize()
            try:
                result = await toolkit_instance.santiment_client.get_sentiment_balance(asset, days)
                if result.get("success"):
                    avg_balance = result.get("average_balance", 0.0)
                    return {
                        "success": True,
                        "asset": asset,
                        "message": f"{asset.capitalize()}'s sentiment balance over the past {days} days is {avg_balance:.1f}.",
                        "average_balance": avg_balance,
                        "days": days
                    }
                else:
                    return result
            except SantimentAPIError as e:
                log.error(f"Santiment API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset
                }
            except Exception as e:
                log.error(f"Error getting sentiment balance for {asset}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset
                }
        
        get_sentiment_balance.__name__ = "get_sentiment_balance"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_sentiment_balance)
        
        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        # OpenAI function schemas don't support 'default' or 'nullable' in properties.
        # Optional parameters are those NOT in the 'required' array.
        # IMPORTANT: days is optional (has default value 7), so it should NOT be in required array
        # Pattern similar to wallet_review_toolkit.py - manual schema creation
        schema = {
            "type": "function",
            "function": {
                "name": "get_sentiment_balance",
                "description": (
                    "Retrieve the sentiment balance (sentiment_balance_total) for a given cryptocurrency asset.\n\n"
                    "The sentiment balance represents positive sentiment minus negative sentiment.\n"
                    "Uses a fixed 1-day period (latest data only) for FREE tier compatibility.\n\n"
                    "Args:\n"
                    "  asset: The cryptocurrency slug (e.g., 'bitcoin', 'ethereum', 'solana'). Required."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset": {
                            "type": "string",
                            "description": "The cryptocurrency slug (e.g., 'bitcoin', 'ethereum', 'solana')"
                        }
                    },
                    "required": ["asset"],
                    "additionalProperties": False
                },
                "strict": True
            },
        }
        
        # ✅ Force schema override BEFORE tool is used anywhere - completely replace auto-generated schema
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
        return tool
    
    def get_social_volume_tool(self):
        """Get tool for retrieving social volume."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_social_volume(
            asset: str
        ) -> Dict[str, Any]:
            """
            Retrieve the total social volume (social_volume_total) for a given cryptocurrency asset.
            
            Social volume calculates the total number of social data text documents (telegram messages,
            reddit posts, etc.) that contain the given search term at least once.
            Uses a fixed 1-day period (latest data only) for FREE tier compatibility.
            
            Args:
                asset: The cryptocurrency slug (e.g., "bitcoin", "ethereum", "solana"). Required.
            """
            # Fixed low value for FREE tier compatibility (1 day - latest data only)
            days = 1
            
            if not toolkit_instance.santiment_client:
                return {
                    "success": False,
                    "error": "Santiment API client not initialized. Check SENTIMENT_API environment variable.",
                    "asset": asset
                }
            
            await toolkit_instance.initialize()
            try:
                result = await toolkit_instance.santiment_client.get_social_volume(asset, days)
                if result.get("success"):
                    total_volume = result.get("total_volume", 0)
                    return {
                        "success": True,
                        "asset": asset,
                        "message": f"{asset.capitalize()}'s social volume over the past {days} days is {total_volume:,} mentions.",
                        "total_volume": total_volume,
                        "days": days
                    }
                else:
                    return result
            except SantimentAPIError as e:
                log.error(f"Santiment API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset
                }
            except Exception as e:
                log.error(f"Error getting social volume for {asset}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset
                }
        
        get_social_volume.__name__ = "get_social_volume"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_social_volume)
        
        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        schema = {
            "type": "function",
            "function": {
                "name": "get_social_volume",
                "description": (
                    "Retrieve the total social volume (social_volume_total) for a given cryptocurrency asset.\n\n"
                    "Social volume calculates the total number of social data text documents (telegram messages,\n"
                    "reddit posts, etc.) that contain the given search term at least once.\n"
                    "Uses a fixed 1-day period (latest data only) for FREE tier compatibility.\n\n"
                    "Args:\n"
                    "  asset: The cryptocurrency slug (e.g., 'bitcoin', 'ethereum', 'solana'). Required."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset": {
                            "type": "string",
                            "description": "The cryptocurrency slug (e.g., 'bitcoin', 'ethereum', 'solana')"
                        }
                    },
                    "required": ["asset"],
                    "additionalProperties": False
                },
                "strict": True
            },
        }
        
        # ✅ Force schema override BEFORE tool is used anywhere - completely replace auto-generated schema
        tool.openai_tool_schema = schema
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
        return tool
    
    def get_social_dominance_tool(self):
        """Get tool for retrieving social dominance."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_social_dominance(
            asset: str
        ) -> Dict[str, Any]:
            """
            Retrieve the social dominance (social_dominance_total) for a given cryptocurrency asset.
            
            Social Dominance shows the share of the discussions in crypto media that is referring
            to a particular asset or phrase.
            
            Args:
                asset: The cryptocurrency slug (e.g., "bitcoin", "ethereum", "solana"). Required.
            """
            # Fixed low value for FREE tier compatibility (1 day - latest data only)
            days = 1
            
            if not toolkit_instance.santiment_client:
                return {
                    "success": False,
                    "error": "Santiment API client not initialized. Check SENTIMENT_API environment variable.",
                    "asset": asset
                }
            
            await toolkit_instance.initialize()
            try:
                result = await toolkit_instance.santiment_client.get_social_dominance(asset, days)
                if result.get("success"):
                    avg_dominance = result.get("average_dominance", 0.0)
                    return {
                        "success": True,
                        "asset": asset,
                        "message": f"{asset.capitalize()}'s social dominance over the past {days} days is {avg_dominance:.1f}%.",
                        "average_dominance": avg_dominance,
                        "days": days
                    }
                else:
                    return result
            except SantimentAPIError as e:
                log.error(f"Santiment API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset
                }
            except Exception as e:
                log.error(f"Error getting social dominance for {asset}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset
                }
        
        get_social_dominance.__name__ = "get_social_dominance"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_social_dominance)
        
        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        # Schema uses basic types (string) as per OpenAI and CAMEL documentation
        schema = {
            "type": "function",
            "function": {
                "name": "get_social_dominance",
                "description": (
                    "Retrieve the social dominance (social_dominance_total) for a given cryptocurrency asset.\n\n"
                    "Social Dominance shows the share of the discussions in crypto media that is referring\n"
                    "to a particular asset or phrase. Uses a fixed 1-day period (latest data only) for FREE tier compatibility.\n\n"
                    "Args:\n"
                    "  asset: The cryptocurrency slug (e.g., 'bitcoin', 'ethereum', 'solana'). Required."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset": {
                            "type": "string",
                            "description": "The cryptocurrency slug (e.g., 'bitcoin', 'ethereum', 'solana')"
                        }
                    },
                    "required": ["asset"]
                },
            },
        }
        
        # ✅ Force schema override BEFORE tool is used anywhere - completely replace auto-generated schema
        tool.openai_tool_schema = schema
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
        return tool
    
    def alert_social_shift_tool(self):
        """Get tool for detecting social volume shifts."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def alert_social_shift(
            asset: str
        ) -> Dict[str, Any]:
            """
            Detect significant shifts (spikes or drops) in social volume for a given cryptocurrency asset.
            
            Compares the latest social volume to the previous average and alerts if the change
            exceeds the threshold percentage.
            Uses a fixed 1-day period (latest data only) for FREE tier compatibility.
            Uses a fixed threshold of 50.0% (50%) for FREE tier compatibility.
            
            Args:
                asset: The cryptocurrency slug (e.g., "bitcoin", "ethereum", "solana"). Required.
            """
            # Fixed low value for FREE tier compatibility (1 day - latest data only)
            days = 1
            # Fixed threshold for FREE tier compatibility (50% default)
            threshold = 50.0
            
            if not toolkit_instance.santiment_client:
                return {
                    "success": False,
                    "error": "Santiment API client not initialized. Check SENTIMENT_API environment variable.",
                    "asset": asset,
                    "shift_detected": False
                }
            
            await toolkit_instance.initialize()
            try:
                result = await toolkit_instance.santiment_client.alert_social_shift(asset, threshold, days)
                if result.get("success"):
                    shift_detected = result.get("shift_detected", False)
                    if shift_detected:
                        direction = result.get("direction", "change")
                        abs_change = result.get("abs_change_percent", 0.0)
                        latest_volume = result.get("latest_volume", 0)
                        prev_avg = result.get("previous_avg_volume", 0)
                        message = (
                            f"{asset.capitalize()}'s social volume {direction}d by {abs_change:.1f}% "
                            f"in the last 24 hours, from an average of {prev_avg:,.0f} to {latest_volume:,}."
                        )
                    else:
                        change_percent = result.get("change_percent", 0.0)
                        message = f"No significant shift detected for {asset.capitalize()}, change is {change_percent:.1f}%."
                    
                    result["message"] = message
                    return result
                else:
                    return result
            except SantimentAPIError as e:
                log.error(f"Santiment API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset,
                    "shift_detected": False
                }
            except Exception as e:
                log.error(f"Error detecting social shift for {asset}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "asset": asset,
                    "shift_detected": False
                }
        
        alert_social_shift.__name__ = "alert_social_shift"
        from core.camel_tools.async_wrapper import create_function_tool
        
        # Provide explicit schema following OpenAI format
        explicit_schema = {
            "type": "function",
            "function": {
                "name": "alert_social_shift",
                "description": "Detect significant shifts (spikes or drops) in social volume for a given cryptocurrency asset. Compares the latest social volume to the previous average and alerts if the change exceeds 50% threshold. Uses a fixed 1-day period (latest data only) for FREE tier compatibility.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset": {
                            "type": "string",
                            "description": "The cryptocurrency slug (e.g., 'bitcoin', 'ethereum', 'solana')"
                        }
                    },
                    "required": ["asset"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        
        tool = create_function_tool(alert_social_shift, explicit_schema=explicit_schema)
        
        return tool
    
    def get_trending_words_tool(self):
        """Get tool for retrieving trending words."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_trending_words(
            top_n: int = 5
        ) -> Dict[str, Any]:
            """
            Retrieve the top trending words in the cryptocurrency space over a specified period.
            
            Words are aggregated and ranked by score across the entire period.
            Uses a fixed 1-day period (latest data only) for FREE tier compatibility.
            
            Args:
                top_n: Number of top trending words to return. Default: 5
            """
            # Fixed low value for FREE tier compatibility (1 day - latest data only)
            days = 1
            
            if not toolkit_instance.santiment_client:
                return {
                    "success": False,
                    "error": "Santiment API client not initialized. Check SENTIMENT_API environment variable.",
                    "top_words": []
                }
            
            await toolkit_instance.initialize()
            try:
                result = await toolkit_instance.santiment_client.get_trending_words(days, top_n)
                if result.get("success"):
                    top_words = result.get("top_words", [])
                    words_list = [w["word"] for w in top_words]
                    message = f"Top {top_n} trending words over the past {days} days: {', '.join(words_list)}."
                    return {
                        "success": True,
                        "message": message,
                        "top_words": words_list,
                        "top_words_with_scores": top_words,
                        "days": days,
                        "top_n": top_n
                    }
                else:
                    return result
            except SantimentAPIError as e:
                log.error(f"Santiment API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "top_words": []
                }
            except Exception as e:
                log.error(f"Error getting trending words: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "top_words": []
                }
        
        get_trending_words.__name__ = "get_trending_words"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_trending_words)
        
        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        schema = {
            "type": "function",
            "function": {
                "name": "get_trending_words",
                "description": (
                    "Retrieve the top trending words in the cryptocurrency space over a specified period.\n\n"
                    "Words are aggregated and ranked by score across the entire period.\n"
                    "Uses a fixed 1-day period (latest data only) for FREE tier compatibility.\n\n"
                    "Args:\n"
                    "  top_n: Number of top trending words to return. Default: 5. Optional."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "top_n": {
                            "type": "integer",
                            "description": "Number of top trending words to return (default: 5)",
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": ["top_n"],
                    "additionalProperties": False
                },
                "strict": True
            },
        }
        
        # ✅ Force schema override BEFORE tool is used anywhere - completely replace auto-generated schema
        tool.openai_tool_schema = schema
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
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
        
        # Only return tools if client is initialized
        if not self.santiment_client:
            logger.warning("Santiment API client not initialized, returning empty list")
            return []
        
        return [
            self.get_sentiment_balance_tool(),
            self.get_social_volume_tool(),
            self.get_social_dominance_tool(),
            self.alert_social_shift_tool(),
            self.get_trending_words_tool(),
        ]
    
    def get_all_tools(self) -> List[FunctionTool]:
        """Alias for get_tools() for backward compatibility."""
        return self.get_tools()


__all__ = ["SantimentToolkit"]

