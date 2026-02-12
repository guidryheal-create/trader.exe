"""
Polymarket Data Toolkit for CAMEL Workforce - Market Scanning & Position Sizing.

Provides tools for:
- Market discovery and filtering
- Price analysis and volume tracking
- Position sizing based on wallet distribution
- Risk assessment and limits
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING
import asyncio
import concurrent.futures
import os
from datetime import datetime

try:
    from camel.toolkits.base import BaseToolkit
    from camel.toolkits.function_tool import FunctionTool
    from camel.logger import get_logger
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:
    BaseToolkit = object
    FunctionTool = None
    CAMEL_TOOLS_AVAILABLE = False

if TYPE_CHECKING:
    from camel.toolkits.function_tool import FunctionTool as FunctionToolType
else:
    FunctionToolType = Any

from core.logging import log
from core.clients.polymarket_client import PolymarketClient

logger = get_logger(__name__) if CAMEL_TOOLS_AVAILABLE else None


def run_async(coro, timeout: float = 30.0) -> Any:
    """Run async coroutine safely in any context."""
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


class PolymarketDataToolkit(BaseToolkit):
    """Polymarket data toolkit for market scanning and position sizing."""

    def __init__(self, timeout: Optional[float] = None):
        """Initialize toolkit."""
        super().__init__(timeout=timeout or 30.0)
        self.client = PolymarketClient(timeout=self.timeout)
        self._initialized = False

    async def _async_initialize(self) -> None:
        """Initialize toolkit (async)."""
        try:
            self._initialized = True
            log.info("PolymarketDataToolkit initialized")
        except Exception as e:
            log.warning(f"Toolkit initialization failed: {e}")
            self._initialized = False

    def initialize(self) -> None:
        """Initialize toolkit (sync wrapper)."""
        run_async(self._async_initialize(), timeout=self.timeout)

    # ========================================================================
    # MARKET SCANNING & DISCOVERY
    # ========================================================================

    def scan_markets_by_category(
        self, 
        category: str, 
        limit: int = 20,
        min_liquidity: float = 1000.0
    ) -> Dict[str, Any]:
        """Scan markets by category with liquidity filter."""
        async def _scan():
            try:
                markets = await self.client.get_trending_markets(
                    category=category, 
                    limit=limit
                )
                
                filtered = [
                    m for m in markets 
                    if m.get("liquidity", 0) >= min_liquidity
                ]
                
                return {
                    "status": "success",
                    "category": category,
                    "total_found": len(filtered),
                    "markets": filtered[:limit],
                    "min_liquidity_filter": min_liquidity
                }
            except Exception as e:
                log.error(f"Market scanning error: {e}")
                return {
                    "status": "error",
                    "message": str(e),
                    "markets": []
                }
        
        return run_async(_scan(), timeout=self.timeout)

    def search_high_conviction_markets(
        self,
        query: str,
        confidence_threshold: float = 0.65,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Search for markets matching query with confidence scoring."""
        async def _search():
            try:
                markets = await self.client.search_markets(
                    query=query, 
                    limit=limit * 2
                )
                
                results = []
                for m in markets:
                    confidence = self._score_market_confidence(m, query)
                    if confidence >= confidence_threshold:
                        results.append({
                            **m,
                            "confidence_score": confidence
                        })
                
                results.sort(
                    key=lambda x: x["confidence_score"], 
                    reverse=True
                )
                
                return {
                    "status": "success",
                    "query": query,
                    "confidence_threshold": confidence_threshold,
                    "results_found": len(results),
                    "markets": results[:limit]
                }
            except Exception as e:
                log.error(f"Search error: {e}")
                return {
                    "status": "error",
                    "message": str(e),
                    "markets": []
                }
        
        return run_async(_search(), timeout=self.timeout)

    def _score_market_confidence(self, market: Dict[str, Any], query: str) -> float:
        """Score market confidence based on various factors."""
        score = 0.5
        
        title = (
            market.get("title")
            or market.get("question")
            or market.get("name")
            or ""
        ).lower()
        if query.lower() in title:
            score += 0.2
        
        liquidity = market.get("liquidity", 0)
        if liquidity > 100000:
            score += 0.15
        elif liquidity > 10000:
            score += 0.1
        
        volume = market.get("volume_24h")
        if volume is None:
            volume = market.get("volume", {}).get("sum", 0) if isinstance(market.get("volume"), dict) else market.get("volume", 0)
        if volume > 50000:
            score += 0.1
        
        return min(score, 1.0)

    def get_market_data(self, market_id: str) -> Dict[str, Any]:
        """Get current market price, orderbook, and other data."""
        async def _get_data():
            try:
                market_details = await self.client.get_market_details(market_id=market_id)
                if not market_details:
                    return {"status": "error", "message": "Market not found"}

                token_ids = await self.client.get_outcome_token_ids(market_id)
                token_id = token_ids.get("YES")
                if not token_id:
                    return {"status": "error", "message": "YES token ID not found in market details"}

                orderbook = await self.client.get_orderbook(token_id=token_id)

                bid = orderbook["bids"][0]["price"] if orderbook["bids"] else None
                ask = orderbook["asks"][0]["price"] if orderbook["asks"] else None
                mid_price = (bid + ask) / 2 if bid and ask else None
                spread = (ask - bid) if bid and ask else None
                
                created_at_str = market_details.get("created_at")
                market_age_hours = None
                if created_at_str:
                    try:
                        # Assuming format like '2024-01-03T10:00:00Z'
                        created_at_dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        market_age_hours = (datetime.now(created_at_dt.tzinfo) - created_at_dt).total_seconds() / 3600
                    except ValueError:
                        log.warning(f"Could not parse market creation date: {created_at_str}")


                return {
                    "status": "success",
                    "market_id": market_id,
                    "title": market_details.get("title"),
                    "mid_price": mid_price,
                    "bid": bid,
                    "ask": ask,
                    "spread": spread,
                    "liquidity": market_details.get("liquidity"),
                    "volume_24h": market_details.get("volume", {}).get('sum'),
                    "market_age_hours": market_age_hours,
                    "orderbook": {
                        "bids": orderbook["bids"][:5],
                        "asks": orderbook["asks"][:5],
                    }
                }
            except Exception as e:
                log.error(f"Error getting market data for {market_id}: {e}")
                return {"status": "error", "message": str(e), "market_id": market_id}

        return run_async(_get_data(), timeout=self.timeout)


    # ========================================================================
    # POSITION SIZING & RISK MANAGEMENT
    # ========================================================================

    def calculate_position_sizes(
        self,
        markets: List[Dict[str, Any]],
        wallet_distribution: Dict[str, float],
        max_position_size_usd: float = 2000.0,
        max_total_exposure_usd: float = 5000.0
    ) -> Dict[str, Any]:
        """Calculate position sizes based on wallet distribution and risk limits."""
        positions = []
        total_exposure = 0.0
        
        for i, market in enumerate(markets):
            if total_exposure >= max_total_exposure_usd:
                log.info(f"Reached max exposure limit at {i+1} markets")
                break
            
            market_id = market.get("id", f"market_{i}")
            liquidity = market.get("liquidity", 10000)
            volume = market.get("volume", {}).get('sum', 0)
            
            remaining_budget = max_total_exposure_usd - total_exposure
            position_size = min(
                remaining_budget * 0.015,
                max_position_size_usd,
                liquidity * 0.05
            )
            
            if position_size < 100:
                continue
            
            mid_price = (
                market.get("mid_price")
                or market.get("yes_price")
                or market.get("last_price")
                or market.get("price")
                or 0.5
            )
            positions.append({
                "market_id": market_id,
                "market_title": market.get("title", "Unknown"),
                "position_size_usd": round(position_size, 2),
                "liquidity": liquidity,
                "volume_24h": volume,
                "mid_price": mid_price,
                "max_quantity": round(position_size / mid_price) if mid_price else 0,
                "risk_level": self._assess_risk_level(market)
            })
            
            total_exposure += position_size
        
        return {
            "status": "success",
            "total_positions": len(positions),
            "total_exposure_usd": round(total_exposure, 2),
            "max_exposure_usd": max_total_exposure_usd,
            "utilization_percent": round(
                (total_exposure / max_total_exposure_usd) * 100, 2
            ),
            "positions": positions,
            "safety_note": "DEMO_MODE" if os.getenv("DEMO_MODE", "").upper() == "TRUE" else "LIVE_TRADING"
        }

    def _assess_risk_level(self, market: Dict[str, Any]) -> str:
        """Assess market risk level."""
        liquidity = market.get("liquidity", 0)
        volume = market.get("volume_24h")
        if volume is None:
            volume = market.get("volume", {}).get("sum", 0) if isinstance(market.get("volume"), dict) else market.get("volume", 0)
        spread = market.get("spread", 0.1)
        
        risk_factors = 0
        
        if liquidity < 10000:
            risk_factors += 2
        elif liquidity < 50000:
            risk_factors += 1
        
        if volume < 5000:
            risk_factors += 1
        
        if spread > 0.05:
            risk_factors += 1
        
        if risk_factors >= 3:
            return "HIGH"
        elif risk_factors >= 1:
            return "MEDIUM"
        else:
            return "LOW"

    # ========================================================================
    # ORDER PLANNING & VALIDATION
    # ========================================================================

    def plan_order_batch(
        self,
        positions: List[Dict[str, Any]],
        order_type: str = "limit",
        price_offset: float = 0.02
    ) -> Dict[str, Any]:
        """Plan batch of orders for execution."""
        orders = []
        
        for pos in positions:
            if order_type == "limit":
                quantity = pos["max_quantity"]
                price = pos.get("mid_price", 0.5) * (1 - price_offset)
            else:
                quantity = pos["max_quantity"]
                price = pos.get("mid_price", 0.5)
            
            orders.append({
                "market_id": pos["market_id"],
                "side": "BUY",
                "quantity": max(1, int(quantity)),
                "price": round(price, 4),
                "order_type": order_type,
                "max_slippage": 0.05,
                "time_in_force": "immediate",
                "status": "ready"
            })
        
        return {
            "status": "ready_for_execution",
            "order_count": len(orders),
            "orders": orders,
            "estimated_total_cost_usd": round(
                sum(o["price"] * o["quantity"] for o in orders), 2
            ),
            "execution_mode": "DEMO" if os.getenv("DEMO_MODE", "").upper() == "TRUE" else "LIVE"
        }

    # ========================================================================
    # POSITION MONITORING
    # ========================================================================

    def monitor_positions(self) -> Dict[str, Any]:
        """
        Monitor current open positions by fetching recent trades.
        NOTE: This is a placeholder and does not return real positions yet.
        It returns recent trade history instead.
        """
        async def _monitor():
            if not self.client.is_authenticated:
                return {
                    "status": "error",
                    "message": "Client is not authenticated. Cannot fetch trades.",
                    "open_positions": []
                }
            try:
                # This is a placeholder. A full implementation would need to
                # reconstruct positions from all historical trades.
                recent_trades = await self.client.get_trades(params={"limit": 25})
                
                return {
                    "status": "success",
                    "message": "NOTE: Returning recent trades, not calculated positions.",
                    "recent_trades": recent_trades,
                    "update_time": datetime.utcnow().isoformat() + 'Z'
                }
            except Exception as e:
                log.error(f"Position monitoring error: {e}")
                return {
                    "status": "error",
                    "message": str(e),
                    "open_positions": []
                }
        
        return run_async(_monitor(), timeout=self.timeout)

    def get_position_history(self, limit: int = 50, asset_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Get closed/historical positions.
        NOTE: This is a placeholder and is not yet implemented.
        """
        async def _get_history():
            if not self.client.is_authenticated:
                return {
                    "status": "error",
                    "message": "Client is not authenticated. Cannot fetch trade history.",
                    "positions": []
                }
            try:
                # This is a placeholder. A full implementation would need to
                # reconstruct positions from all historical trades.
                params = {"limit": limit}
                if asset_filter:
                    params["market"] = asset_filter
                
                trade_history = await self.client.get_trades(params=params)

                return {
                    "status": "success",
                    "message": "NOTE: Returning raw trade history, not calculated positions.",
                    "history": trade_history,
                    "limit": limit,
                    "asset_filter": asset_filter
                }
            except Exception as e:
                log.error(f"Error getting position history: {e}")
                return {
                    "status": "error",
                    "message": str(e)
                }
        return run_async(_get_history(), timeout=self.timeout)


    # ========================================================================
    # TOOLKIT INTERFACE
    # ========================================================================

    def get_tools(self) -> List["FunctionToolType"]:
        """Get list of tools for CAMEL agents."""
        if not CAMEL_TOOLS_AVAILABLE:
            return []
        
        toolkit = self
        try:
            from core.camel_tools.async_wrapper import create_function_tool
        except ImportError:
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
        
        # Market scanning tool
        def scan_markets_tool(category: str, limit: int = 20, min_liquidity: float = 1000.0) -> Dict[str, Any]:
            """Scan Polymarket markets by category with liquidity filters"""
            return toolkit.scan_markets_by_category(
                category=category, 
                limit=limit, 
                min_liquidity=min_liquidity
            )
        
        tools.append(_make_tool(
            scan_markets_tool,
            name="polymarket_data_scan_by_category",
            description="Scan Polymarket markets by category with liquidity filters.",
            properties={
                "category": {"type": "string", "description": "Market category name."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max number of markets to return."},
                "min_liquidity": {"type": "number", "minimum": 0, "description": "Minimum liquidity filter."},
            },
            required=["category"],
        ))
        
        # Market search tool
        def search_conviction_tool(query: str, confidence_threshold: float = 0.65, limit: int = 10) -> Dict[str, Any]:
            """Search high-conviction markets matching query"""
            return toolkit.search_high_conviction_markets(
                query=query,
                confidence_threshold=confidence_threshold,
                limit=limit
            )
        
        tools.append(_make_tool(
            search_conviction_tool,
            name="polymarket_data_search_high_conviction",
            description="Search high-conviction markets matching a query.",
            properties={
                "query": {"type": "string", "description": "Search query string."},
                "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1, "description": "Minimum confidence score."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max number of markets to return."},
            },
            required=["query"],
        ))
        
        # Market data tool
        def market_data_tool(market_id: str) -> Dict[str, Any]:
            """Get detailed data for a specific market, including orderbook."""
            return toolkit.get_market_data(market_id=market_id)
        
        tools.append(_make_tool(
            market_data_tool,
            name="polymarket_data_market_snapshot",
            description="Get detailed data for a market, including orderbook snapshot.",
            properties={
                "market_id": {"type": "string", "description": "Polymarket market ID (condition_id)."},
            },
            required=["market_id"],
        ))
        
        # Position sizing tool
        def position_sizing_tool(
            markets_json: str,
            wallet_distribution_json: str,
            max_position_size_usd: float = 2000.0,
            max_total_exposure_usd: float = 5000.0,
        ) -> Dict[str, Any]:
            """Calculate position sizes based on wallet distribution and risk limits."""
            import json
            markets = json.loads(markets_json) if isinstance(markets_json, str) else markets_json
            wallet_distribution = (
                json.loads(wallet_distribution_json)
                if isinstance(wallet_distribution_json, str)
                else wallet_distribution_json
            )
            return toolkit.calculate_position_sizes(
                markets=markets,
                wallet_distribution=wallet_distribution,
                max_position_size_usd=max_position_size_usd,
                max_total_exposure_usd=max_total_exposure_usd,
            )
        
        tools.append(_make_tool(
            position_sizing_tool,
            name="polymarket_data_position_sizes",
            description="Calculate position sizes from markets and wallet distribution JSON.",
            properties={
                "markets_json": {"type": "string", "description": "JSON list of market objects."},
                "wallet_distribution_json": {"type": "string", "description": "JSON mapping of wallet distribution."},
                "max_position_size_usd": {"type": "number", "minimum": 0, "description": "Max USD per position."},
                "max_total_exposure_usd": {"type": "number", "minimum": 0, "description": "Max total USD exposure."},
            },
            required=["markets_json", "wallet_distribution_json"],
        ))
        
        # Order planning tool
        def order_planning_tool(positions_json: str, order_type: str = "limit", price_offset: float = 0.02) -> Dict[str, Any]:
            """Plan batch of orders ready for execution."""
            import json
            positions_list = json.loads(positions_json) if isinstance(positions_json, str) else positions_json
            return toolkit.plan_order_batch(
                positions=positions_list,
                order_type=order_type,
                price_offset=price_offset,
            )
        
        tools.append(_make_tool(
            order_planning_tool,
            name="polymarket_data_plan_orders",
            description="Plan a batch of orders from position sizing output.",
            properties={
                "positions_json": {"type": "string", "description": "JSON list of position objects."},
                "order_type": {"type": "string", "enum": ["limit", "market"], "description": "Order type."},
                "price_offset": {"type": "number", "minimum": 0, "description": "Limit price offset for limit orders."},
            },
            required=["positions_json"],
        ))
        
        # Position monitoring tool
        def monitor_pos_tool() -> Dict[str, Any]:
            """Monitor current open positions and P&L (currently returns recent trades)."""
            return toolkit.monitor_positions()
        
        tools.append(_make_tool(
            monitor_pos_tool,
            name="polymarket_data_monitor_positions",
            description="Monitor current open positions and P&L (returns recent trades).",
            properties={},
            required=[],
        ))
        
        # Position history tool
        def position_history_tool(limit: int = 50) -> Dict[str, Any]:
            """Get historical/closed positions (currently returns raw trade history)."""
            return toolkit.get_position_history(limit=limit)
        
        tools.append(_make_tool(
            position_history_tool,
            name="polymarket_data_position_history",
            description="Get historical/closed positions (raw trade history).",
            properties={
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Max trades to return."},
            },
            required=[],
        ))
        
        return tools
