"""
Enhanced Polymarket Toolkit for CAMEL Agents - Pure CAMEL-AI Implementation.

Provides comprehensive tools for accessing Polymarket prediction markets with
full CAMEL framework integration. Designed for seamless multi-agent usage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING
import asyncio
import concurrent.futures
from datetime import datetime

try:
    from camel.toolkits.base import BaseToolkit
    from camel.toolkits.function_tool import FunctionTool
    from camel.logger import get_logger
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:
    BaseToolkit = object  # type: ignore
    FunctionTool = None
    CAMEL_TOOLS_AVAILABLE = False

if TYPE_CHECKING:
    from camel.toolkits.function_tool import FunctionTool as FunctionToolType
else:
    FunctionToolType = Any

from core.logging import log
from core.clients.polymarket_client import PolymarketClient

logger = get_logger(__name__)


def run_async(coro, timeout: float = 30.0) -> Any:
    """
    Run async coroutine safely in any context.
    
    Handles:
    - Already running event loop (runs in thread)
    - No event loop (creates new one)
    - Error cases
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()
                
                future = executor.submit(run_in_thread)
                return future.result(timeout=timeout)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            
            future = executor.submit(run_in_thread)
            return future.result(timeout=timeout)


class EnhancedPolymarketToolkit(BaseToolkit):
    """Enhanced Polymarket toolkit for CAMEL agents.
    
    Provides market discovery, analysis, portfolio management, and trading tools.
    """

    def __init__(self, timeout: Optional[float] = None):
        """Initialize toolkit.
        
        Args:
            timeout: Request timeout in seconds (default: 30.0)
        """
        super().__init__(timeout=timeout or 30.0)
        self.client = PolymarketClient(timeout=self.timeout)
        self._initialized = False

    async def _async_initialize(self) -> None:
        """Initialize toolkit (async)."""
        try:
            self._initialized = True
        except Exception as e:
            log.warning(f"Toolkit initialization: {e}")
            self._initialized = False

    def initialize(self) -> None:
        """Initialize toolkit (sync wrapper)."""
        run_async(self._async_initialize(), timeout=self.timeout)

    # ========================================================================
    # MARKET DISCOVERY
    # ========================================================================

    def search_markets(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Search for markets by keyword."""
        def _normalize_market(market: Dict[str, Any]) -> Dict[str, Any]:
            title = market.get("title") or market.get("question") or market.get("name") or ""
            volume = market.get("volume_24h")
            if volume is None and isinstance(market.get("volume"), dict):
                volume = market.get("volume", {}).get("sum")
            return {
                **market,
                "market_id": market.get("market_id") or market.get("id") or market.get("condition_id"),
                "title": title,
                "volume_24h": volume,
            }

        async def _search():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                if not query or len(query) < 1:
                    return {"success": False, "error": "Query required (min 1 char)"}
                
                results = await self.client.search_markets(
                    query=query,
                    limit=max(1, min(limit, 100))
                )
                normalized = [_normalize_market(m) for m in results]
                
                return {
                    "success": True,
                    "markets": normalized,
                    "count": len(normalized),
                    "query": query
                }
            except Exception as e:
                log.error(f"Search error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_search(), timeout=self.timeout)

    def get_trending_markets(
        self,
        timeframe: str = "24hr",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get trending markets by volume."""
        async def _trending():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                valid = ["24hr", "7d", "30d"]
                tf = timeframe if timeframe in valid else "24h"
                
                results = await self.client.get_trending_markets(
                    timeframe=tf,
                    limit=max(1, min(limit, 100))
                )
                
                return {
                    "success": True,
                    "markets": results,
                    "count": len(results),
                    "timeframe": tf
                }
            except Exception as e:
                log.error(f"Trending error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_trending(), timeout=self.timeout)

    def get_markets_by_category(
        self,
        category: str,
        active_only: bool = True,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Filter markets by category."""
        async def _by_category():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                results = await self.client.get_trending_markets(
                    slug=category,
                    limit=max(1, min(limit, 100))
                )
                
                return {
                    "success": True,
                    "markets": results,
                    "count": len(results),
                    "category": category
                }
            except Exception as e:
                log.error(f"Category error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_by_category(), timeout=self.timeout)


    # ========================================================================
    # MARKET ANALYSIS
    # ========================================================================
    def get_market_details(self, market_id: str) -> Dict[str, Any]:
        """Get market details."""
        async def _details():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                if not market_id:
                    return {"success": False, "error": "market_id required"}
                
                result = await self.client.get_market_details(market_id=market_id)
                return {"success": True, "market": result, "market_id": market_id}
            except Exception as e:
                log.error(f"Details error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_details(), timeout=self.timeout)

    def get_orderbook(
        self,
        market_id: str,
        depth: int = 10
    ) -> Dict[str, Any]:
        """Get orderbook for market."""
        async def _orderbook():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                if not market_id:
                    return {"success": False, "error": "market_id required"}
                
                market_details = await self.client.get_market_details(market_id=market_id)
                if not market_details:
                    return {"status": "error", "message": "Market not found"}
                
                token_ids = await self.client.get_outcome_token_ids(market_id)
                token_id = token_ids.get("YES")
                if not token_id:
                    return {"success": False, "error": "YES token ID not found in market details"}
                
                result = await self.client.get_orderbook(
                    token_id=token_id,
                    depth=max(1, min(depth, 50))
                )
                return {"success": True, "orderbook": result, "market_id": market_id}
            except Exception as e:
                log.error(f"Orderbook error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_orderbook(), timeout=self.timeout)

    def calculate_market_opportunity(
        self,
        market_id: str,
        confidence_threshold: float = 0.55
    ) -> Dict[str, Any]:
        """Calculate opportunity score for market."""
        async def _opportunity():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                if not market_id:
                    return {"success": False, "error": "market_id required"}
                
                market = await self.client.get_market_details(market_id=market_id)
                
                token_ids = await self.client.get_outcome_token_ids(market_id)
                token_id = token_ids.get("YES")
                if not token_id:
                    return {"success": False, "error": "YES token ID not found in market details"}

                orderbook = await self.client.get_orderbook(token_id=token_id)
                
                yes_price = market.get("yes_price", 0.5)
                no_price = 1 - yes_price
                volume = market.get("volume",{}).get('sum', 0)
                liquidity = orderbook.get("liquidity_score", 0) if orderbook else 0
                
                spread = abs(yes_price - no_price)
                opportunity_score = min(1.0, (volume / 10000.0) * (liquidity / 100.0))
                
                if yes_price > confidence_threshold:
                    signal = "BUY_YES"
                    confidence = yes_price
                elif no_price > confidence_threshold:
                    signal = "BUY_NO"
                    confidence = no_price
                else:
                    signal = "HOLD"
                    confidence = max(yes_price, no_price)
                
                return {
                    "success": True,
                    "market_id": market_id,
                    "opportunity_score": opportunity_score,
                    "signal": signal,
                    "confidence": confidence,
                    "spread": spread,
                    "volume_24h": volume
                }
            except Exception as e:
                log.error(f"Opportunity error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_opportunity(), timeout=self.timeout)

    # ========================================================================
    # PORTFOLIO
    # ========================================================================

    def monitor_positions(self) -> Dict[str, Any]:
        """
        Monitor current open positions.
        NOTE: Not supported in native py-clob-client path yet.
        """
        async def _monitor():
            return {
                "status": "not_supported",
                "message": "Position monitoring is not available via native client yet.",
                "open_positions": [],
            }
        
        return run_async(_monitor(), timeout=self.timeout)

    def get_position_history(self, limit: int = 50, asset_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Get closed/historical positions.
        NOTE: Not supported in native py-clob-client path yet.
        """
        async def _get_history():
            return {
                "status": "not_supported",
                "message": "Position history is not available via native client yet.",
                "history": [],
                "limit": limit,
                "asset_filter": asset_filter,
            }
        return run_async(_get_history(), timeout=self.timeout)

    def get_user_positions(self, user_address: str) -> Dict[str, Any]:
        """Get positions for user."""
        async def _positions():
            return {
                "status": "not_supported",
                "message": "User positions are not available via native client yet.",
                "positions": [],
                "count": 0,
                "user_address": user_address,
            }
        
        return run_async(_positions(), timeout=self.timeout)

    def calculate_portfolio_pnl(self, user_address: str) -> Dict[str, Any]:
        """Calculate portfolio P&L."""
        async def _pnl():
            return {
                "status": "not_supported",
                "message": "Portfolio P&L is not available via native client yet.",
                "pnl": {},
                "user_address": user_address,
            }
        
        return run_async(_pnl(), timeout=self.timeout)

    def get_portfolio_value(self, user_address: str) -> Dict[str, Any]:
        """Get portfolio total value."""
        async def _value():
            return {
                "status": "not_supported",
                "message": "Portfolio value is not available via native client yet.",
                "portfolio": {},
                "user_address": user_address,
            }
        
        return run_async(_value(), timeout=self.timeout)

    # ========================================================================
    # TRADING
    # ========================================================================
    # use low level wallet knowledge + per trade options 
    def suggest_trade_size(
        self,
        market_id: str,
        portfolio_value: float,
        confidence: float,
        max_exposure_pct: float = 5.0
    ) -> Dict[str, Any]:
        """Calculate optimal trade size."""
        async def _size():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                if not market_id or portfolio_value <= 0:
                    return {"success": False, "error": "Invalid inputs"}
                
                confidence = max(0.0, min(1.0, confidence))
                max_exposure = (portfolio_value * max_exposure_pct) / 100.0
                
                if confidence < 0.55:
                    position_size = 0
                elif confidence < 0.65:
                    position_size = max_exposure * 0.25
                elif confidence < 0.75:
                    position_size = max_exposure * 0.50
                else:
                    position_size = max_exposure * 0.75
                
                return {
                    "success": True,
                    "suggested_size": position_size,
                    "max_allowed": max_exposure,
                    "confidence": confidence,
                    "sizing_strategy": "kelly_variant"
                }
            except Exception as e:
                log.error(f"Sizing error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_size(), timeout=self.timeout)


    def make_position(
        self,
        market_id: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        condition_id: Optional[str] = None,
        slug: Optional[str] = None,
        market_maker_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close existing position.
        
        Args:
            market_id: ID of market
            side: "YES" or "NO" (shares to sell)
            size: Number of shares to sell
            price: Optional limit price (defaults to 0.5 if omitted)
            condition_id: Optional condition ID (alternative identifier)
            slug: Optional market slug (alternative identifier)
            market_maker_address: Optional market maker address (alternative identifier)
        
        Returns:
            Trade execution result with exit details
        """
        # use the low level toolkit ? or implement close logic here using client
        async def _close_position():
            try:
                if not self._initialized:
                    await self._async_initialize() 
                
                if side not in ["YES", "NO"]:
                    log.warning(f"[POLYMARKET] Invalid side: {side}")
                    return {"success": False, "error": "side must be YES or NO"}
                
                if size <= 0:
                    log.warning(f"[POLYMARKET] Invalid size: {size}")
                    return {"success": False, "error": "size must be > 0"}
                
                market_key = market_id or condition_id or slug or market_maker_address or ""
                if not market_key:
                    return {"success": False, "error": "market_id (or condition_id/slug/market_maker_address) required"}
                log.info(f"[POLYMARKET] Closing position: market={market_key[:8]}..., side={side}, size={size}")
                
                token_ids = await self.client.get_outcome_token_ids(
                    market_id=market_id,
                    condition_id=condition_id,
                    slug=slug,
                    market_maker_address=market_maker_address,
                )
                if side == "YES":
                    token_id = token_ids[0]
                elif side == "NO":
                    token_id = token_ids[1] 
                    
                if not token_id:
                    return {"success": False, "error": f"{side} token ID not found"}

                order_price = 0.5 if price is None else float(price)
                trade_result = await self.client.place_order(
                    token_id=token_id,
                    side=side,
                    quantity=size,
                    price=order_price,
                )
                
                log.info(f"[POLYMARKET] Position closed: {trade_result.get('id', 'unknown')}")
                
                return {
                    "success": True,
                    "transaction_id": trade_result.get("id"),
                    "market_id": market_id,
                    "side": side,
                    "size": size,
                    "token_id": token_id,
                    "exit_price": trade_result.get("price", order_price),
                    "proceeds": trade_result.get("price", order_price) * size,
                }
            except Exception as e:
                log.error(f"[POLYMARKET] Close error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_close_position(), timeout=self.timeout)

    def get_position_details(
        self,
        market_id: str,
        user_address: str
    ) -> Dict[str, Any]:
        """Get detailed position info for specific market.
        
        Args:
            market_id: ID of market
            user_address: User wallet address
        
        Returns:
            Position details including entry, current value, P&L
        """
        async def _position_details():
            return {
                "status": "not_supported",
                "message": "Position details are not available via native client yet.",
                "market_id": market_id,
                "user_address": user_address,
            }
        
        return run_async(_position_details(), timeout=self.timeout)

    # ========================================================================
    # UTILITIES
    # ========================================================================

    def get_market_categories(self) -> Dict[str, Any]:
        """Get available categories."""
        return {
            "success": True,
            "categories": [
                "Politics", "Sports", "Crypto", "Markets",
                "Technology", "Entertainment", "Society", "Science"
            ],
            "count": 8
        }

    def get_wallet_balances(self) -> Dict[str, Any]:
        """Get wallet balances (USDC + native token)."""
        try:
            usdc = self.client.get_usdc_balance()
        except Exception as e:
            usdc = None
            log.warning(f"USDC balance error: {e}")
        try:
            native = self.client.get_eth_balance()
        except Exception as e:
            native = None
            log.warning(f"Native balance error: {e}")
        return {
            "success": True,
            "usdc": usdc,
            "native": native,
        }

    def get_polymarket_vault_balance(self, token_id: str) -> Dict[str, Any]:
        """Get Polymarket vault balance (free + locked) for a token_id."""
        try:
            balances = self.client.get_polymarket_usdc_balance(token_id=token_id)
            return {"success": True, "token_id": token_id, "balances": balances}
        except Exception as e:
            log.error(f"Vault balance error: {e}")
            return {"success": False, "error": str(e), "token_id": token_id}

    def format_market_summary(self, market_id: str) -> Dict[str, Any]:
        """Format market summary for display."""
        async def _summary():
            try:
                if not self._initialized:
                    await self._async_initialize()
                
                market = await self.client.get_market_details(market_id=market_id)
                
                return {
                    "success": True,
                    "market_id": market_id,
                    "title": market.get("title")
                    or market.get("question")
                    or market.get("name")
                    or "",
                    "description": market.get("description", ""),
                    "yes_price": market.get("yes_price", 0.5),
                    "no_price": 1-market.get("yes_price", 0.5),
                    "volume_24h": market.get("volume", {}).get('sum',0),
                    "liquidity": market.get("liquidity", 0),
                    "closing_date": market.get("end_date_time", ""),
                    "categories": market.get("category", [])
                }
            except Exception as e:
                log.error(f"Summary error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return run_async(_summary(), timeout=self.timeout)

    # ========================================================================
    # CAMEL REGISTRATION
    # ========================================================================

    def get_tools(self) -> List["FunctionToolType"]:
        """Return FunctionTool objects for CAMEL agents."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            logger.warning("CAMEL tools not available")
            return []
        
        toolkit = self
        
        try:
            from core.camel_tools.async_wrapper import create_function_tool
        except ImportError:
            logger.warning("async_wrapper not found, using basic tools")
            create_function_tool = FunctionTool
        
        def _make_tool(func, name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None):
            func.__name__ = name
            func.__doc__ = description
            schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required or [],
                        "additionalProperties": False,
                    },
                },
            }
            if create_function_tool is FunctionTool:
                tool = create_function_tool(func)
                tool.openai_tool_schema = schema
            else:
                try:
                    tool = create_function_tool(func, tool_name=name, description=description, explicit_schema=schema)
                except Exception:
                    tool = create_function_tool(func, tool_name=name, description=description)
                    tool.openai_tool_schema = schema
            return tool

        tools = []
        
        # Search tool
        def search_tool(query: str, limit: int = 20) -> Dict[str, Any]:
            """Search markets by keyword"""
            return toolkit.search_markets(query=query, limit=limit)
        
        tools.append(_make_tool(
            search_tool,
            name="polymarket_search_markets",
            description="Search Polymarket markets by keyword.",
            properties={
                "query": {"type": "string", "description": "Search query string."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max number of markets to return."},
            },
            required=["query"],
        ))
        
        # Trending tool
        def trending_tool(timeframe: str = "24h", limit: int = 10) -> Dict[str, Any]:
            """Get trending markets"""
            return toolkit.get_trending_markets(timeframe=timeframe, limit=limit)
        
        tools.append(_make_tool(
            trending_tool,
            name="polymarket_trending_markets",
            description="Get trending Polymarket markets by volume.",
            properties={
                "timeframe": {
                    "type": "string",
                    "enum": ["24h", "24hr", "7d", "30d"],
                    "description": "Timeframe window.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max number of markets to return."},
            },
            required=[],
        ))
        
        def market_data_tool(market_id: str, depth: int = 10) -> Dict[str, Any]:
            """Get market details and orderbook snapshot."""
            details = toolkit.get_market_details(market_id=market_id)
            orderbook = toolkit.get_orderbook(market_id=market_id, depth=depth)
            success = bool(details.get("success")) and bool(orderbook.get("success"))
            return {
                "success": success,
                "market_id": market_id,
                "market": details.get("market"),
                "orderbook": orderbook.get("orderbook"),
                "errors": {
                    "details": details.get("error"),
                    "orderbook": orderbook.get("error"),
                },
            }
        
        tools.append(_make_tool(
            market_data_tool,
            name="polymarket_market_snapshot",
            description="Get market details and a YES orderbook snapshot.",
            properties={
                "market_id": {"type": "string", "description": "Polymarket market ID (condition_id)."},
                "depth": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Orderbook depth to fetch."},
            },
            required=["market_id"],
        ))
        
        # Details tool
        def details_tool(market_id: str) -> Dict[str, Any]:
            """Get market details"""
            return toolkit.get_market_details(market_id=market_id)
        
        tools.append(_make_tool(
            details_tool,
            name="polymarket_market_details",
            description="Get market details including prices and metadata.",
            properties={
                "market_id": {"type": "string", "description": "Polymarket market ID (condition_id)."},
            },
            required=["market_id"],
        ))
        
        # Opportunity tool
        def opportunity_tool(market_id: str, confidence_threshold: float = 0.55) -> Dict[str, Any]:
            """Calculate opportunity"""
            return toolkit.calculate_market_opportunity(
                market_id=market_id,
                confidence_threshold=confidence_threshold
            )
        
        tools.append(_make_tool(
            opportunity_tool,
            name="polymarket_opportunity_score",
            description="Calculate opportunity score and trade signal for a market.",
            properties={
                "market_id": {"type": "string", "description": "Polymarket market ID (condition_id)."},
                "confidence_threshold": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Threshold for BUY_YES/BUY_NO signal.",
                },
            },
            required=["market_id"],
        ))

        # order tool
        def order_tool(
            market_id: str,
            side: str,
            size: float,
            price: Optional[float] = None,
            condition_id: Optional[str] = None,
            slug: Optional[str] = None,
            market_maker_address: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Close a position in a market (SELL outcome shares)."""
            return toolkit.make_position(
                market_id=market_id,
                side=side,
                size=size,
                price=price,
                condition_id=condition_id,
                slug=slug,
                market_maker_address=market_maker_address,
            )
        
        order_tool.__name__ = "close_polymarket_position"
        order_tool.__doc__ = (
            "Close a position in a market by SELLing outcome shares. "
            "Use side='YES' or side='NO' to choose the outcome token. "
            "Size is number of shares to sell. Optional price is the limit price (defaults to 0.5)."
        )
        order_tool_handle = create_function_tool(order_tool)
        order_tool_handle.openai_tool_schema = {
            "type": "function",
            "function": {
                "name": "close_polymarket_position",
                "description": order_tool.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "market_id": {
                            "type": "string",
                            "description": "REQUIRED: Polymarket market ID (condition_id).",
                        },
                        "condition_id": {
                            "type": "string",
                            "description": "Optional condition ID (alternative identifier).",
                        },
                        "slug": {
                            "type": "string",
                            "description": "Optional market slug (alternative identifier).",
                        },
                        "market_maker_address": {
                            "type": "string",
                            "description": "Optional market maker address (0x...).",
                        },
                        "side": {
                            "type": "string",
                            "enum": ["YES", "NO"],
                            "description": "REQUIRED: Outcome token to sell ('YES' or 'NO').",
                        },
                        "size": {
                            "type": "number",
                            "minimum": 0,
                            "description": "REQUIRED: Number of shares to sell.",
                        },
                        "price": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                            "description": "Optional limit price between 0 and 1. Defaults to 0.5 if omitted.",
                        },
                    },
                    "required": ["market_id", "side", "size"],
                    "additionalProperties": False,
                },
            },
        }
        tools.append(order_tool_handle)
        
        # Sizing tool
        def sizing_tool(
            market_id: str,
            portfolio_value: float,
            confidence: float
        ) -> Dict[str, Any]:
            """Calculate position size"""
            return toolkit.suggest_trade_size(
                market_id=market_id,
                portfolio_value=portfolio_value,
                confidence=confidence
            )
        
        tools.append(_make_tool(
            sizing_tool,
            name="polymarket_suggest_trade_size",
            description="Calculate an optimal trade size based on portfolio value and confidence.",
            properties={
                "market_id": {"type": "string", "description": "Polymarket market ID (condition_id)."},
                "portfolio_value": {"type": "number", "minimum": 0, "description": "Total portfolio value in USD."},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Model confidence (0-1)."},
            },
            required=["market_id", "portfolio_value", "confidence"],
        ))

        # Wallet balances tool
        def balances_tool() -> Dict[str, Any]:
            """Get wallet balances (USDC + native token)."""
            return toolkit.get_wallet_balances()

        tools.append(_make_tool(
            balances_tool,
            name="polymarket_wallet_balances",
            description="Get wallet balances (USDC + native token).",
            properties={},
            required=[],
        ))

        # Vault balance tool
        def vault_balance_tool(token_id: str) -> Dict[str, Any]:
            """Get Polymarket vault balance (free + locked) for a token_id."""
            return toolkit.get_polymarket_vault_balance(token_id=token_id)

        tools.append(_make_tool(
            vault_balance_tool,
            name="polymarket_vault_balance",
            description="Get Polymarket vault balance (free + locked) for a token_id.",
            properties={
                "token_id": {"type": "string", "description": "Outcome token ID."},
            },
            required=["token_id"],
        ))
        
        logger.info(f"✅ Loaded {len(tools)} Polymarket tools for CAMEL (including trading)")
        return tools


# Backward compatibility alias
PolymarketToolkit = EnhancedPolymarketToolkit

__all__ = ["EnhancedPolymarketToolkit", "PolymarketToolkit"]
