"""
Wallet Review Toolkit for CAMEL Agents.

Provides tools for reading wallet distributions and agentic logs from Redis
to enable review agents to judge results and update agentic weights.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from core.logging import log

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


class WalletReviewToolkit(BaseToolkit):
    r"""A toolkit for reading wallet distributions and agentic logs from Redis.
    
    Provides tools for review agents to:
    - Read wallet distributions for strategies
    - Read agentic conversation logs and decisions
    - Read performance metrics
    - Update agentic weights based on performance
    """
    
    def __init__(self, redis_client_override=None, timeout: Optional[float] = None):
        r"""Initializes the WalletReviewToolkit and sets up the Redis client.
        
        Args:
            redis_client_override: Optional RedisClient instance for testing
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        # Use a fresh RedisClient instance to avoid cross-event-loop issues.
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
            logger.debug(f"Redis connection in WalletReviewToolkit: {e}")
    
    def get_wallet_distribution(
        self,
        strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Read wallet distribution(s) from Redis.
        
        Reads wallet distributions stored at keys: response_format:wallet:{strategy}:combined
        If strategy is not specified, returns all available wallet distributions.
        
        Args:
            strategy: Optional strategy name (e.g., "wallet_balancing", "momentum_sniper").
                     If None, returns all strategies.
                     
        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - strategies (dict): Dictionary mapping strategy names to wallet distribution data
                - count (int): Number of strategies found
                - error (str): Error message if success is False
        """
        import asyncio
        
        async def _async_read():
            try:
                await self.initialize()
                
                strategies = {}
                
                if strategy:
                    # Read specific strategy
                    key = f"response_format:wallet:{strategy}:combined"
                    data = await self.redis.get_json(key)
                    if data:
                        strategies[strategy] = data
                else:
                    # Read all strategies
                    cursor = 0
                    while True:
                        cursor, batch = await self.redis.redis.scan(
                            cursor=cursor,
                            match="response_format:wallet:*:combined",
                            count=200
                        )
                        for key in batch:
                            # Extract strategy name from key: response_format:wallet:{strategy}:combined
                            if isinstance(key, bytes):
                                key = key.decode()
                            parts = key.split(":")
                            if len(parts) >= 4 and parts[0] == "response_format" and parts[1] == "wallet":
                                strategy_name = parts[2]
                                data = await self.redis.get_json(key)
                                if data:
                                    strategies[strategy_name] = data
                        if cursor == 0:
                            break
                
                return {
                    "success": True,
                    "strategies": strategies,
                    "count": len(strategies)
                }
            except Exception as e:
                log.error(f"Error reading wallet distributions: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "strategies": {},
                    "count": 0
                }
        
        # Run async operation
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Create a new event loop in the thread
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(_async_read())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(_async_read())
        except RuntimeError:
            return asyncio.run(_async_read())
    
    def get_agentic_logs(
        self,
        agent_name: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Read agentic conversation logs from Redis.
        
        Reads logs stored at keys: conversations:{agent_name}:{conversation_id}
        or agentic:decision:{decision_id}
        
        Args:
            agent_name: Optional agent name filter (e.g., "Fact Extractor", "Trend Analyzer").
                       If None, returns logs from all agents.
            limit: Maximum number of logs to return. Default: 20
                     
        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - logs (list): List of conversation logs with enhanced fields
                - count (int): Number of logs found
                - error (str): Error message if success is False
        """
        import asyncio
        
        async def _async_read():
            try:
                await self.initialize()
                
                logs = []
                
                # Read from agentic:decision:* keys (enhanced logging)
                cursor = 0
                keys_found = []
                
                while True:
                    cursor, batch = await self.redis.redis.scan(
                        cursor=cursor,
                        match="agentic:decision:*",
                        count=200
                    )
                    if batch:
                        keys_found.extend(batch)
                    if cursor == 0 or len(keys_found) >= limit * 2:
                        break
                
                # Also read from conversations:* keys
                if agent_name:
                    pattern = f"conversations:{agent_name}:*"
                else:
                    pattern = "conversations:*:*"
                
                cursor = 0
                while True:
                    cursor, batch = await self.redis.redis.scan(
                        cursor=cursor,
                        match=pattern,
                        count=200
                    )
                    if batch:
                        keys_found.extend(batch)
                    if cursor == 0 or len(keys_found) >= limit * 2:
                        break
                
                # Read and parse logs
                for key in keys_found[:limit]:
                    try:
                        if isinstance(key, bytes):
                            key = key.decode()
                        
                        data = await self.redis.get_json(key)
                        if data:
                            # Filter by agent_name if specified
                            if agent_name:
                                log_agent = data.get("agent_name", "")
                                if agent_name.lower() not in log_agent.lower():
                                    continue
                            
                            logs.append({
                                "key": key,
                                "agent_name": data.get("agent_name", "unknown"),
                                "title": data.get("title"),
                                "user_explanation": data.get("user_explanation", data.get("message", "")),
                                "message": data.get("message", ""),
                                "timestamp": data.get("timestamp"),
                                "tools_used": data.get("tools_used", []),
                                "agents_involved": data.get("agents_involved", []),
                                "citations": data.get("citations", []),
                                "decision_metadata": data.get("decision_metadata", {}),
                                "decision_id": data.get("decision_id", key.split(":")[-1] if ":" in key else key),
                            })
                    except Exception as e:
                        log.debug(f"Error reading log from key {key}: {e}")
                        continue
                
                # Sort by timestamp (most recent first)
                logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
                logs = logs[:limit]
                
                return {
                    "success": True,
                    "logs": logs,
                    "count": len(logs)
                }
            except Exception as e:
                log.error(f"Error reading agentic logs: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "logs": [],
                    "count": 0
                }
        
        # Run async operation
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Create a new event loop in the thread
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(_async_read())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(_async_read())
        except RuntimeError:
            return asyncio.run(_async_read())
    
    def update_agentic_weight(
        self,
        tool_name: str,
        weight: float
    ) -> Dict[str, Any]:
        """
        Update agentic weight for a tool based on performance review.
        
        Stores tool weights in Redis at key: tool_weights:{tool_name}
        Weights are typically in range [0.0, 1.0], where:
        - 1.0 = fully trusted (contributes to good decisions)
        - 0.5 = neutral (default)
        - 0.0 = not trusted (contributes to poor decisions)
        
        Args:
            tool_name: Name of the tool (e.g., "get_stock_forecast", "get_action_recommendation")
            weight: Weight value (0.0-1.0). Default: 0.5
                     
        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - tool_name (str): The tool name
                - weight (float): The weight that was set
                - error (str): Error message if success is False
        """
        import asyncio
        
        async def _async_update():
            try:
                await self.initialize()
                
                # Clamp weight to [0.0, 1.0]
                weight_clamped = max(0.0, min(1.0, weight))
                
                key = f"tool_weights:{tool_name}"
                await self.redis.set(key, str(weight_clamped), expire=86400 * 30)  # 30 days TTL
                
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "weight": weight_clamped,
                    "message": f"Updated weight for {tool_name} to {weight_clamped:.2f}"
                }
            except Exception as e:
                log.error(f"Error updating agentic weight: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "tool_name": tool_name,
                    "weight": weight
                }
        
        # Run async operation
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Create a new event loop in the thread
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(_async_update())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(_async_update())
        except RuntimeError:
            return asyncio.run(_async_update())
    
    def get_agentic_weight(
        self,
        tool_name: str
    ) -> Dict[str, Any]:
        """
        Get current agentic weight for a tool.
        
        Reads tool weight from Redis at key: tool_weights:{tool_name}
        
        Args:
            tool_name: Name of the tool
                     
        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - tool_name (str): The tool name
                - weight (float): The current weight (default: 0.5 if not set)
                - error (str): Error message if success is False
        """
        import asyncio
        
        async def _async_read():
            try:
                await self.initialize()
                
                key = f"tool_weights:{tool_name}"
                weight_str = await self.redis.get(key)
                
                if weight_str:
                    try:
                        weight = float(weight_str)
                    except ValueError:
                        weight = 0.5  # Default
                else:
                    weight = 0.5  # Default if not set
                
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "weight": weight
                }
            except Exception as e:
                log.error(f"Error reading agentic weight: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "tool_name": tool_name,
                    "weight": 0.5
                }
        
        # Run async operation
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Create a new event loop in the thread
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(_async_read())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(_async_read())
        except RuntimeError:
            return asyncio.run(_async_read())
    
    def get_wallet_distribution_tool(self):
        """Get tool for reading wallet distributions."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_wallet_distribution(
            strategy: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Read wallet distribution(s) from Redis for performance review.
            
            Reads wallet distributions stored at keys: response_format:wallet:{strategy}:combined
            Use this tool to review previous wallet distributions and calculate performance metrics.
            
            Args:
                strategy: Optional strategy name (e.g., "wallet_balancing", "momentum_sniper").
                         If None, returns all available wallet distributions.
            """
            # Call the async operation directly instead of going through sync wrapper
            try:
                await toolkit_instance.initialize()
                
                strategies = {}
                
                if strategy:
                    # Read specific strategy
                    key = f"response_format:wallet:{strategy}:combined"
                    data = await toolkit_instance.redis.get_json(key)
                    if data:
                        strategies[strategy] = data
                else:
                    # Read all strategies
                    cursor = 0
                    while True:
                        cursor, batch = await toolkit_instance.redis.redis.scan(
                            cursor=cursor,
                            match="response_format:wallet:*:combined",
                            count=200
                        )
                        for key in batch:
                            # Extract strategy name from key: response_format:wallet:{strategy}:combined
                            if isinstance(key, bytes):
                                key = key.decode()
                            parts = key.split(":")
                            if len(parts) >= 4 and parts[0] == "response_format" and parts[1] == "wallet":
                                strategy_name = parts[2]
                                data = await toolkit_instance.redis.get_json(key)
                                if data:
                                    strategies[strategy_name] = data
                        if cursor == 0:
                            break
                
                return {
                    "success": True,
                    "strategies": strategies,
                    "count": len(strategies)
                }
            except Exception as e:
                log.error(f"Error reading wallet distributions: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "strategies": {},
                    "count": 0
                }
        
        get_wallet_distribution.__name__ = "get_wallet_distribution"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_wallet_distribution)
        
        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        # OpenAI function schemas don't support 'default' or 'nullable' in properties.
        # Optional parameters are those NOT in the 'required' array.
        # IMPORTANT: strategy is optional (has default value None), so it should NOT be in required array
        # Pattern similar to yahoo_finance_toolkit.py - manual schema creation
        schema = {
            "type": "function",
            "function": {
                "name": "get_wallet_distribution",
                "description": (
                    "Read wallet distribution(s) from Redis for performance review.\n\n"
                    "Reads wallet distributions stored at keys: response_format:wallet:{strategy}:combined\n"
                    "Use this tool to review previous wallet distributions and calculate performance metrics.\n\n"
                    "Args:\n"
                    "  strategy: Optional strategy name (e.g., 'wallet_balancing', 'momentum_sniper'). "
                    "If not provided, returns all available wallet distributions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "strategy": {
                            "type": "string",
                            "description": "Optional strategy name (e.g., 'wallet_balancing', 'momentum_sniper'). If not provided, returns all strategies."
                        },
                    },
                    "required": [],  # strategy is optional (has default value None) - empty array means no required params
                },
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
    
    def get_agentic_logs_tool(self):
        """Get tool for reading agentic logs."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_agentic_logs(
            agent_name: Optional[str] = None,
            limit: int = 20
        ) -> Dict[str, Any]:
            """
            Read agentic conversation logs from Redis for performance review.
            
            Reads logs with enhanced fields (title, user_explanation, citations, tools_used, etc.)
            from keys: conversations:{agent_name}:{conversation_id} or agentic:decision:{decision_id}
            
            Use this tool to review agent decisions and analyze decision quality.
            
            Args:
                agent_name: Optional agent name filter (e.g., "Fact Extractor", "Trend Analyzer").
                           If None, returns logs from all agents.
                limit: Maximum number of logs to return. Default: 20
            """
            return toolkit_instance.get_agentic_logs(agent_name, limit)
        
        get_agentic_logs.__name__ = "get_agentic_logs"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_agentic_logs)
        
        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # OpenAI function schemas require strict adherence: every property must be in 'required' if not optional
        # Since agent_name is Optional[str] = None, it should NOT be in required
        # Since limit has a default, it should NOT be in required
        schema = {
            "type": "function",
            "function": {
                "name": get_agentic_logs.__name__,
                "description": get_agentic_logs.__doc__ or "Read agentic conversation logs from Redis for performance review",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Optional agent name filter (e.g., 'Fact Extractor', 'Trend Analyzer'). If omitted, returns logs from all agents."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of logs to return. Defaults to 20 if not specified.",
                            "minimum": 1,
                            "maximum": 100
                        }
                    },
                    "required": [],  # Both parameters are optional (agent_name defaults to None, limit defaults to 20)
                    "additionalProperties": False
                }
            }
        }
        
        # Override the auto-generated schema to ensure compliance
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
        return tool
    
    def update_agentic_weight_tool(self):
        """Get tool for updating agentic weights."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def update_agentic_weight(
            tool_name: str,
            weight: float = 0.5
        ) -> Dict[str, Any]:
            """
            Update agentic weight for a tool based on performance review.
            
            Stores tool weights in Redis. Weights are in range [0.0, 1.0]:
            - 1.0 = fully trusted (contributes to good decisions)
            - 0.5 = neutral (default)
            - 0.0 = not trusted (contributes to poor decisions)
            
            Use this tool after reviewing wallet distributions and logs to adjust tool weights.
            
            Args:
                tool_name: Name of the tool (e.g., "get_stock_forecast", "get_action_recommendation")
                weight: Weight value (0.0-1.0). Default: 0.5
            """
            return toolkit_instance.update_agentic_weight(tool_name, weight)
        
        update_agentic_weight.__name__ = "update_agentic_weight"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(update_agentic_weight)
        
        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # OpenAI function schemas require strict adherence: every property must be in 'required' if not optional
        # tool_name is required (no default), weight is optional (has default 0.5)
        schema = {
            "type": "function",
            "function": {
                "name": update_agentic_weight.__name__,
                "description": update_agentic_weight.__doc__ or "Update agentic weight for a tool based on performance review",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool (e.g., 'get_stock_forecast', 'get_action_recommendation')"
                        },
                        "weight": {
                            "type": "number",
                            "description": "Weight value (0.0-1.0). Defaults to 0.5 if not specified.",
                        }
                    },
                    "required": ["tool_name"],  # Only tool_name is required, weight has default so it's optional
                    "additionalProperties": False
                }
            }
        }
        
        # Override the auto-generated schema to ensure compliance
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
        return tool
    
    def get_agentic_weight_tool(self):
        """Get tool for reading agentic weights."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_agentic_weight(
            tool_name: str
        ) -> Dict[str, Any]:
            """
            Get current agentic weight for a tool.
            
            Reads tool weight from Redis. Returns 0.5 (neutral) if weight is not set.
            
            Args:
                tool_name: Name of the tool
            """
            # Call the async operation directly instead of going through sync wrapper
            try:
                await toolkit_instance.initialize()
                
                key = f"tool_weights:{tool_name}"
                weight_str = await toolkit_instance.redis.get(key)
                
                if weight_str:
                    try:
                        weight = float(weight_str)
                    except ValueError:
                        weight = 0.5  # Default
                else:
                    weight = 0.5  # Default if not set
                
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "weight": weight
                }
            except Exception as e:
                log.error(f"Error reading agentic weight: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "tool_name": tool_name,
                    "weight": 0.5
                }
        
        get_agentic_weight.__name__ = "get_agentic_weight"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_agentic_weight)
        
        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # tool_name is required (no default)
        schema = {
            "type": "function",
            "function": {
                "name": get_agentic_weight.__name__,
                "description": get_agentic_weight.__doc__ or "Get current agentic weight for a tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool"
                        }
                    },
                    "required": ["tool_name"],  # tool_name is required (no default)
                    "additionalProperties": False
                }
            }
        }
        
        # Override the auto-generated schema to ensure compliance
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
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
        
        return [
            self.get_wallet_distribution_tool(),
            self.get_agentic_logs_tool(),
            self.update_agentic_weight_tool(),
            self.get_agentic_weight_tool(),
        ]
    
    def get_all_tools(self) -> List[FunctionTool]:
        """Alias for get_tools() for backward compatibility."""
        return self.get_tools()


__all__ = ["WalletReviewToolkit"]

