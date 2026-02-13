"""
ROI Analyzer Toolkit for CAMEL Review Agents.

Provides tools for analyzing wallet distribution ROI and updating agent weights
based on performance.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
import json

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


class ROIAnalyzerToolkit(BaseToolkit):
    r"""A toolkit for analyzing ROI from wallet distributions and updating agent weights.
    
    Provides tools for review agents to:
    - Analyze ROI from previous wallet distributions
    - Update agent weights based on performance
    - Generate advice for next cycle
    """
    
    def __init__(self, redis_client_override=None, timeout: Optional[float] = None):
        r"""Initializes the ROIAnalyzerToolkit and sets up the Redis client.
        
        Args:
            redis_client_override: Optional RedisClient instance for testing
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        if redis_client_override:
            self.redis = redis_client_override
        else:
            from core.clients.redis_client import RedisClient
            self.redis = RedisClient()
    
    async def initialize(self) -> None:
        """Initialize the Redis client connection."""
        try:
            await self.redis.connect()
        except Exception as e:
            log.warning(f"ROI Analyzer Toolkit Redis connection failed: {e}")
    
    def register_cycle_roi(
        self,
        strategy: str,
        cycle_id: Optional[str] = None,
        agent_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Register ROI for a cycle by tracking wallet distribution prices.
        
        At end of cycle, registers historical ROI by:
        1. Getting wallet distribution from Redis
        2. Fetching current prices (T) for all tickers
        3. Storing ROI record with T prices
        4. On next cycle or T+1, updates with T+1 prices and calculates ROI
        
        Args:
            strategy: Strategy name (e.g., 'wallet_balancing')
            cycle_id: Optional cycle ID (auto-generated if not provided)
            agent_weights: Optional dict of agent weights at this cycle
        
        Returns:
            Dictionary with success status and ROI record details
        """
        import asyncio
        import uuid
        
        async def _async_register():
            try:
                await self.initialize()
                
                # Generate cycle_id if not provided
                if not cycle_id:
                    cycle_id_value = f"{strategy}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
                else:
                    cycle_id_value = cycle_id
                
                # Get wallet distribution from Redis
                wallet_key = f"response_format:wallet:{strategy}:combined"
                wallet_data = await self.redis.get_json(wallet_key)
                
                if not wallet_data:
                    return {
                        "success": False,
                        "error": f"No wallet distribution found for strategy: {strategy}"
                    }
                
                wallet_dist = wallet_data.get("wallet_distribution", {})
                if not wallet_dist:
                    return {
                        "success": False,
                        "error": "Wallet distribution is empty"
                    }
                
                timestamp = datetime.now(timezone.utc)
                timestamp_str = wallet_data.get("timestamp") or timestamp.isoformat()
                
                # Get agent weights from Redis if not provided
                agent_weights_dict = agent_weights if agent_weights is not None else {}
                if not agent_weights_dict:
                    # Try to get weights from Redis
                    try:
                        cursor = 0
                        while True:
                            cursor, batch = await self.redis.redis.scan(
                                cursor=cursor,
                                match="agent_weight:*",
                                count=200
                            )
                            for key in batch:
                                if isinstance(key, bytes):
                                    key = key.decode()
                                weight_data = await self.redis.get_json(key)
                                if weight_data:
                                    agent_name = weight_data.get("agent_name", key.replace("agent_weight:", ""))
                                    agent_weights_dict[agent_name] = weight_data.get("weight", 1.0)
                            if cursor == 0:
                                break
                    except Exception as e:
                        log.debug(f"Could not fetch agent weights: {e}")
                
                # Fetch current prices for all tickers
                from core.clients.forecasting_client import ForecastingClient
                from core.settings.config import settings
                
                forecasting_client = ForecastingClient({
                    "base_url": settings.mcp_api_url,
                    "api_key": settings.mcp_api_key,
                    "timeout": 30.0
                })
                await forecasting_client.connect()
                
                ticker_data = {}
                for ticker, allocation_pct in wallet_dist.items():
                    if not ticker or allocation_pct <= 0:
                        continue
                    
                    try:
                        # Get current price using action recommendation
                        action_data = await forecasting_client.get_action_recommendation(ticker, "days")
                        buy_price = action_data.get("current_price")
                        
                        if not buy_price:
                            # Fallback to forecast
                            forecast_data = await forecasting_client.get_stock_forecast(ticker, "days")
                            if forecast_data and forecast_data.get("forecast_timeline"):
                                buy_price = forecast_data["forecast_timeline"][0].get("forecast_price")
                        
                        if buy_price:
                            buy_price = float(buy_price)
                            ticker_data[ticker] = {
                                "allocation_pct": float(allocation_pct),
                                "buy_price": buy_price,
                                "t1_price": None,  # Will be updated on T+1
                                "latest_price": buy_price,  # Initially same as buy_price
                                "t1_roi": None,
                                "latest_roi": 0.0,  # No change initially
                                "timedelta_hours": None
                            }
                        else:
                            log.warning(f"Could not fetch price for {ticker}, skipping ROI tracking")
                    except Exception as e:
                        log.warning(f"Error fetching price for {ticker}: {e}")
                        continue
                
                # Check for previous cycle to update T+1 prices
                # Get all ROI records for this strategy
                roi_history_key = f"roi:history:{strategy}:list"
                existing_cycles = await self.redis.lrange(roi_history_key, 0, -1)
                
                # Update T+1 prices for previous cycles (if ~24h has passed)
                now = datetime.now(timezone.utc)
                for cycle_id_str in existing_cycles:
                    if isinstance(cycle_id_str, bytes):
                        cycle_id_str = cycle_id_str.decode()
                    
                    prev_roi_key = f"roi:history:{strategy}:{cycle_id_str}"
                    prev_roi = await self.redis.get_json(prev_roi_key)
                    
                    if prev_roi:
                        prev_timestamp_str = prev_roi.get("timestamp")
                        if prev_timestamp_str:
                            try:
                                prev_timestamp = datetime.fromisoformat(prev_timestamp_str.replace("Z", "+00:00"))
                                hours_elapsed = (now - prev_timestamp).total_seconds() / 3600.0
                                
                                # If ~24h has passed, update T+1 prices (check between 20-30 hours)
                                if 20 <= hours_elapsed <= 30 and not prev_roi.get("t1_updated", False):
                                    updated_tickers = {}
                                    for ticker, ticker_info in prev_roi.get("tickers", {}).items():
                                        try:
                                            action_data = await forecasting_client.get_action_recommendation(ticker, "days")
                                            t1_price = action_data.get("current_price")
                                            
                                            if not t1_price:
                                                forecast_data = await forecasting_client.get_stock_forecast(ticker, "days")
                                                if forecast_data and forecast_data.get("forecast_timeline"):
                                                    t1_price = forecast_data["forecast_timeline"][0].get("forecast_price")
                                            
                                            if t1_price and ticker_info.get("buy_price"):
                                                t1_price = float(t1_price)
                                                buy_price = float(ticker_info["buy_price"])
                                                t1_roi = ((t1_price - buy_price) / buy_price) * 100.0
                                                
                                                updated_tickers[ticker] = ticker_info.copy()
                                                updated_tickers[ticker]["t1_price"] = t1_price
                                                updated_tickers[ticker]["t1_roi"] = t1_roi
                                                updated_tickers[ticker]["timedelta_hours"] = hours_elapsed
                                                updated_tickers[ticker]["latest_price"] = t1_price
                                                updated_tickers[ticker]["latest_roi"] = t1_roi
                                        
                                        except Exception as e:
                                            log.debug(f"Error updating T+1 price for {ticker}: {e}")
                                            continue
                                    
                                    if updated_tickers:
                                        prev_roi["tickers"] = updated_tickers
                                        prev_roi["t1_updated"] = True
                                        
                                        # Calculate aggregate strategy ROI
                                        total_allocation = sum(t.get("allocation_pct", 0) for t in updated_tickers.values())
                                        if total_allocation > 0:
                                            weighted_roi = sum(
                                                t.get("t1_roi", 0) * (t.get("allocation_pct", 0) / total_allocation)
                                                for t in updated_tickers.values()
                                            )
                                            prev_roi["strategy_roi"] = weighted_roi
                                        
                                        await self.redis.set_json(prev_roi_key, prev_roi, expire=86400 * 30)
                                        log.info(f"Updated T+1 ROI for cycle {cycle_id_str}")
                            except (ValueError, AttributeError):
                                pass
                
                # Calculate aggregate strategy ROI for current cycle (initial, will be 0)
                total_allocation = sum(t.get("allocation_pct", 0) for t in ticker_data.values())
                strategy_roi = 0.0  # No ROI yet, will be calculated at T+1
                
                # Get latest advice if available
                advice_data = await self.redis.get_json("review_advice:latest")
                advice = advice_data.get("recommendations", "") if advice_data else ""
                
                # Create ROI record
                roi_record = {
                    "cycle_id": cycle_id_value,
                    "timestamp": timestamp_str,
                    "strategy": strategy,
                    "agent_weights": agent_weights_dict,
                    "tickers": ticker_data,
                    "strategy_roi": strategy_roi,
                    "advice": advice,
                    "t1_updated": False
                }
                
                # Store ROI record
                roi_key = f"roi:history:{strategy}:{cycle_id_value}"
                await self.redis.set_json(roi_key, roi_record, expire=86400 * 30)  # 30 days TTL
                
                # Add to history list (FIFO - keep only last 10 cycles)
                await self.redis.lpush(roi_history_key, cycle_id_value)
                await self.redis.expire(roi_history_key, 86400 * 30)
                
                # Trim to keep only last 10 cycles
                await self.redis.ltrim(roi_history_key, 0, 9)
                
                log.info(f"Registered ROI for cycle {cycle_id_value} (strategy: {strategy}, {len(ticker_data)} tickers)")
                
                return {
                    "success": True,
                    "cycle_id": cycle_id_value,
                    "strategy": strategy,
                    "tickers_tracked": len(ticker_data),
                    "timestamp": timestamp_str
                }
                
            except Exception as e:
                log.error(f"Error registering cycle ROI: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e)
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
                            return new_loop.run_until_complete(_async_register())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=60.0)
            else:
                return loop.run_until_complete(_async_register())
        except RuntimeError:
            # No event loop - create one in a thread to avoid conflicts
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_async_register())
                    finally:
                        new_loop.close()
                
                future = executor.submit(run_in_thread)
                return future.result(timeout=60.0)
    
    def analyze_wallet_roi(
        self,
        strategy: Optional[str] = None,
        time_window_hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Analyze ROI from wallet distributions in the previous time window.
        
        Args:
            strategy: Strategy name to analyze (e.g., 'wallet_balancing', 'trend_follower').
                     If None, analyzes all strategies.
            time_window_hours: Time window in hours to look back (default: 24 hours)
        
        Returns:
            Dictionary with ROI analysis results or waiting message if insufficient data
        """
        import asyncio
        
        async def _async_analyze():
            try:
                await self.initialize()
                
                # Get current time and calculate time window
                now = datetime.now(timezone.utc)
                window_start = now - timedelta(hours=time_window_hours)
                
                # Get wallet distributions from Redis
                strategies_to_check = []
                if strategy:
                    strategies_to_check = [strategy]
                else:
                    # Get all strategies
                    cursor = 0
                    while True:
                        cursor, batch = await self.redis.redis.scan(
                            cursor=cursor,
                            match="response_format:wallet:*:combined",
                            count=200
                        )
                        for key in batch:
                            if isinstance(key, bytes):
                                key = key.decode()
                            parts = key.split(":")
                            if len(parts) >= 4 and parts[0] == "response_format" and parts[1] == "wallet":
                                strategy_name = parts[2]
                                if strategy_name not in strategies_to_check:
                                    strategies_to_check.append(strategy_name)
                        if cursor == 0:
                            break
                
                if not strategies_to_check:
                    return {
                        "success": True,
                        "status": "waiting",
                        "message": "Waiting for more evaluation - no wallet distributions found",
                        "strategies_analyzed": [],
                        "roi_data": {}
                    }
                
                # Analyze each strategy using historical ROI records
                roi_results = {}
                total_roi = 0.0
                strategy_count = 0
                
                for strat in strategies_to_check:
                    # Get ROI history for this strategy
                    roi_history_key = f"roi:history:{strat}:list"
                    cycle_ids = await self.redis.lrange(roi_history_key, 0, 9)  # Get last 10 cycles
                    
                    if not cycle_ids:
                        # No ROI history yet, check wallet distribution as fallback
                        key = f"response_format:wallet:{strat}:combined"
                        wallet_data = await self.redis.get_json(key)
                        
                        if wallet_data:
                            wallet_timestamp_str = wallet_data.get("timestamp")
                            if wallet_timestamp_str:
                                try:
                                    wallet_timestamp = datetime.fromisoformat(
                                        wallet_timestamp_str.replace("Z", "+00:00")
                                    )
                                    if wallet_timestamp >= window_start:
                                        roi_results[strat] = {
                                            "strategy": strat,
                                            "status": "waiting",
                                            "message": "ROI tracking not yet available - waiting for T+1 price data",
                                            "wallet_distribution": wallet_data.get("wallet_distribution", {}),
                                            "timestamp": wallet_timestamp_str
                                        }
                                        strategy_count += 1
                                except (ValueError, AttributeError):
                                    pass
                        continue
                    
                    # Process ROI records
                    strategy_rois = []
                    ticker_rois = {}  # Aggregate per-ticker ROI across cycles
                    
                    for cycle_id_bytes in cycle_ids:
                        if isinstance(cycle_id_bytes, bytes):
                            cycle_id_str = cycle_id_bytes.decode()
                        else:
                            cycle_id_str = str(cycle_id_bytes)
                        
                        roi_key = f"roi:history:{strat}:{cycle_id_str}"
                        roi_record = await self.redis.get_json(roi_key)
                        
                        if not roi_record:
                            continue
                        
                        record_timestamp_str = roi_record.get("timestamp")
                        if record_timestamp_str:
                            try:
                                record_timestamp = datetime.fromisoformat(
                                    record_timestamp_str.replace("Z", "+00:00")
                                )
                                if record_timestamp < window_start:
                                    continue  # Skip old records
                            except (ValueError, AttributeError):
                                pass
                        
                        # Get strategy ROI (prefer T+1 ROI if available, else latest ROI)
                        strategy_roi = roi_record.get("strategy_roi", 0.0)
                        if strategy_roi != 0.0:
                            strategy_rois.append(strategy_roi)
                        
                        # Aggregate per-ticker ROI
                        for ticker, ticker_info in roi_record.get("tickers", {}).items():
                            if ticker not in ticker_rois:
                                ticker_rois[ticker] = {
                                    "allocation_pct": ticker_info.get("allocation_pct", 0.0),
                                    "buy_price": ticker_info.get("buy_price"),
                                    "t1_roi": [],
                                    "latest_roi": [],
                                    "cycles_tracked": 0
                                }
                            
                            # Use T+1 ROI if available, else latest ROI
                            t1_roi = ticker_info.get("t1_roi")
                            latest_roi = ticker_info.get("latest_roi", 0.0)
                            
                            if t1_roi is not None:
                                ticker_rois[ticker]["t1_roi"].append(t1_roi)
                            if latest_roi is not None:
                                ticker_rois[ticker]["latest_roi"].append(latest_roi)
                            
                            ticker_rois[ticker]["cycles_tracked"] += 1
                    
                    # Calculate averages
                    avg_strategy_roi = sum(strategy_rois) / len(strategy_rois) if strategy_rois else 0.0
                    
                    # Calculate per-ticker average ROI
                    ticker_roi_summary = {}
                    for ticker, ticker_data in ticker_rois.items():
                        t1_rois = ticker_data["t1_roi"]
                        latest_rois = ticker_data["latest_roi"]
                        
                        avg_t1_roi = sum(t1_rois) / len(t1_rois) if t1_rois else None
                        avg_latest_roi = sum(latest_rois) / len(latest_rois) if latest_rois else 0.0
                        
                        ticker_roi_summary[ticker] = {
                            "allocation_pct": ticker_data["allocation_pct"],
                            "buy_price": ticker_data["buy_price"],
                            "avg_t1_roi": avg_t1_roi,
                            "avg_latest_roi": avg_latest_roi,
                            "cycles_tracked": ticker_data["cycles_tracked"]
                        }
                    
                    if strategy_rois or ticker_roi_summary:
                        roi_results[strat] = {
                            "strategy": strat,
                            "avg_strategy_roi": avg_strategy_roi,
                            "ticker_rois": ticker_roi_summary,
                            "cycles_analyzed": len(strategy_rois),
                            "timestamp": record_timestamp_str if 'record_timestamp_str' in locals() else None
                        }
                        total_roi += avg_strategy_roi
                        strategy_count += 1
                
                if strategy_count == 0:
                    return {
                        "success": True,
                        "status": "waiting",
                        "message": f"Waiting for more evaluation - no wallet distributions found in the last {time_window_hours} hours",
                        "strategies_analyzed": [],
                        "roi_data": {}
                    }
                
                if strategy_count == 0:
                    return {
                        "success": True,
                        "status": "waiting",
                        "message": f"Waiting for more evaluation - no ROI data found in the last {time_window_hours} hours",
                        "strategies_analyzed": [],
                        "roi_data": {}
                    }
                
                # Calculate overall average ROI
                avg_total_roi = total_roi / strategy_count if strategy_count > 0 else 0.0
                
                return {
                    "success": True,
                    "status": "complete",
                    "message": f"Analyzed {strategy_count} strategy(ies) with ROI data",
                    "strategies_analyzed": list(roi_results.keys()),
                    "roi_data": roi_results,
                    "avg_total_roi": avg_total_roi,
                    "time_window_hours": time_window_hours
                }
                
            except Exception as e:
                log.error(f"Error analyzing wallet ROI: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "status": "error"
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
                            return new_loop.run_until_complete(_async_analyze())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(_async_analyze())
        except RuntimeError:
            # No event loop - create one in a thread to avoid conflicts
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_async_analyze())
                    finally:
                        new_loop.close()
                
                future = executor.submit(run_in_thread)
                return future.result(timeout=30.0)
    
    def update_agent_weight(
        self,
        agent_name: str,
        weight: float,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Update the weight of an agent based on performance review.
        
        Agent weights influence how much their decisions contribute to final wallet distributions.
        Weights should be between 0.0 and 1.0.
        
        Args:
            agent_name: Name of the agent (e.g., 'Fact Extractor', 'Trend Analyzer', 'Sentiment Analyst', 'Risk Analyzer', 'Fusion Synthesizer')
            weight: New weight value (0.0 to 1.0). Higher weights = more influence.
            reason: Optional reason for the weight update (e.g., 'Good performance in trend analysis')
        
        Returns:
            Dictionary with success status and updated weight
        """
        import asyncio
        
        async def _async_update():
            try:
                await self.initialize()
                
                # Validate weight
                if not (0.0 <= weight <= 1.0):
                    return {
                        "success": False,
                        "error": f"Weight must be between 0.0 and 1.0, got {weight}"
                    }
                
                # Store agent weight in Redis
                key = f"agent_weight:{agent_name}"
                weight_data = {
                    "agent_name": agent_name,
                    "weight": weight,
                    "reason": reason,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                await self.redis.set_json(key, weight_data, expire=86400 * 30)  # 30 days TTL
                
                log.info(f"Updated agent weight: {agent_name} = {weight} (reason: {reason})")
                
                return {
                    "success": True,
                    "agent_name": agent_name,
                    "weight": weight,
                    "reason": reason,
                    "updated_at": weight_data["updated_at"]
                }
                
            except Exception as e:
                log.error(f"Error updating agent weight: {e}")
                return {
                    "success": False,
                    "error": str(e)
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
            # No event loop - create one in a thread to avoid conflicts
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_async_update())
                    finally:
                        new_loop.close()
                
                future = executor.submit(run_in_thread)
                return future.result(timeout=30.0)
    
    def generate_advice(
        self,
        analysis_summary: str,
        performance_insights: str,
    ) -> Dict[str, Any]:
        """
        Generate advice for the next cycle based on ROI analysis and performance insights.
        
        This advice will be stored and can be retrieved by agents in the next cycle.
        
        Args:
            analysis_summary: Summary of ROI analysis (e.g., 'BTC performed well, ETH underperformed')
            performance_insights: Performance insights (e.g., 'Trend Analyzer had high accuracy, Risk Analyzer was too conservative')
        
        Returns:
            Dictionary with success status and generated advice
        """
        import asyncio
        
        async def _async_generate():
            try:
                await self.initialize()
                
                # Generate advice
                advice = {
                    "analysis_summary": analysis_summary,
                    "performance_insights": performance_insights,
                    "recommendations": self._generate_recommendations(analysis_summary, performance_insights),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "cycle_id": datetime.now(timezone.utc).strftime("%Y%m%d")
                }
                
                # Store advice in Redis
                key = "review_advice:latest"
                await self.redis.set_json(key, advice, expire=86400 * 7)  # 7 days TTL
                
                # Also store with cycle ID for history
                cycle_key = f"review_advice:{advice['cycle_id']}"
                await self.redis.set_json(cycle_key, advice, expire=86400 * 30)  # 30 days TTL
                
                log.info(f"Generated review advice for cycle {advice['cycle_id']}")
                
                return {
                    "success": True,
                    "advice": advice
                }
                
            except Exception as e:
                log.error(f"Error generating advice: {e}")
                return {
                    "success": False,
                    "error": str(e)
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
                            return new_loop.run_until_complete(_async_generate())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(_async_generate())
        except RuntimeError:
            # No event loop - create one in a thread to avoid conflicts
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_async_generate())
                    finally:
                        new_loop.close()
                
                future = executor.submit(run_in_thread)
                return future.result(timeout=30.0)
    
    def get_latest_advice(self) -> Dict[str, Any]:
        """
        Retrieve the latest advice generated by the review agent for the next cycle.
        
        Returns:
            Dictionary with latest advice or message if no advice available
        """
        import asyncio
        
        async def _async_get():
            try:
                await self.initialize()
                
                # Get latest advice
                key = "review_advice:latest"
                advice = await self.redis.get_json(key)
                
                if not advice:
                    return {
                        "success": True,
                        "has_advice": False,
                        "message": "No advice available yet - waiting for review agent analysis"
                    }
                
                return {
                    "success": True,
                    "has_advice": True,
                    "advice": advice
                }
                
            except Exception as e:
                log.error(f"Error getting latest advice: {e}")
                return {
                    "success": False,
                    "error": str(e)
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
                            return new_loop.run_until_complete(_async_get())
                        finally:
                            new_loop.close()
                    
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30.0)
            else:
                return loop.run_until_complete(_async_get())
        except RuntimeError:
            # No event loop - create one in a thread to avoid conflicts
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_async_get())
                    finally:
                        new_loop.close()
                
                future = executor.submit(run_in_thread)
                return future.result(timeout=30.0)
    
    def _generate_recommendations(
        self,
        analysis_summary: str,
        performance_insights: str,
    ) -> str:
        """Generate recommendations based on analysis and insights."""
        recommendations = []
        
        # Simple rule-based recommendations
        if "performed well" in analysis_summary.lower() or "high accuracy" in performance_insights.lower():
            recommendations.append("Continue current strategy approach")
        
        if "underperformed" in analysis_summary.lower() or "too conservative" in performance_insights.lower():
            recommendations.append("Consider adjusting risk parameters")
        
        if "trend" in performance_insights.lower() and "high" in performance_insights.lower():
            recommendations.append("Increase weight on trend analysis signals")
        
        if "risk" in performance_insights.lower() and "conservative" in performance_insights.lower():
            recommendations.append("Review risk assessment thresholds")
        
        if not recommendations:
            recommendations.append("Monitor market conditions and adjust as needed")
        
        return "; ".join(recommendations)
    
    def get_tools(self) -> List[FunctionTool]:
        """Returns a list of FunctionTool objects for ROI analysis operations."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            logger.warning("CAMEL tools not available, returning empty list")
            return []
        
        toolkit_instance = self
        
        # Analyze wallet ROI tool
        def analyze_wallet_roi(
            strategy: Optional[str] = None,
            time_window_hours: int = 24,
        ) -> Dict[str, Any]:
            """Analyze ROI from wallet distributions in the previous time window.
            
            Returns ROI analysis or a waiting message if insufficient data is available.
            
            Args:
                strategy: Strategy name to analyze (e.g., 'wallet_balancing'). If None, analyzes all strategies.
                time_window_hours: Time window in hours to look back (default: 24 hours)
            """
            return toolkit_instance.analyze_wallet_roi(strategy, time_window_hours)
        
        analyze_wallet_roi.__name__ = "analyze_wallet_roi"
        from core.camel_tools.async_wrapper import create_function_tool
        analyze_roi_tool = create_function_tool(analyze_wallet_roi)
        
        # Override schema for analyze_wallet_roi
        schema_analyze = {
            "type": "function",
            "function": {
                "name": "analyze_wallet_roi",
                "description": (
                    "Analyze ROI from wallet distributions in the previous time window.\n\n"
                    "Returns ROI analysis results or a waiting message if insufficient data is available.\n"
                    "If no wallet distributions are found in the time window, returns a message indicating "
                    "that more evaluation is needed.\n\n"
                    "Args:\n"
                    "  strategy: Strategy name to analyze (e.g., 'wallet_balancing', 'trend_follower'). "
                    "If None, analyzes all strategies.\n"
                    "  time_window_hours: Time window in hours to look back (default: 24 hours)"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "strategy": {
                            "type": "string",
                            "description": "Strategy name to analyze (optional, analyzes all if not provided)"
                        },
                        "time_window_hours": {
                            "type": "integer",
                            "description": "Time window in hours to look back (default: 24)",
                            "default": 24
                        }
                    },
                    "required": []
                }
            }
        }
        analyze_roi_tool.openai_tool_schema = schema_analyze
        if hasattr(analyze_roi_tool, '_openai_tool_schema'):
            analyze_roi_tool._openai_tool_schema = schema_analyze
        if hasattr(analyze_roi_tool, '_schema'):
            analyze_roi_tool._schema = schema_analyze
        
        # Update agent weight tool
        def update_agent_weight(
            agent_name: str,
            weight: float,
            reason: str = "",
        ) -> Dict[str, Any]:
            """Update the weight of an agent based on performance review.
            
            Agent weights influence how much their decisions contribute to final wallet distributions.
            
            Args:
                agent_name: Name of the agent (e.g., 'Fact Extractor', 'Trend Analyzer')
                weight: New weight value (0.0 to 1.0). Higher weights = more influence.
                reason: Optional reason for the weight update
            """
            return toolkit_instance.update_agent_weight(agent_name, weight, reason)
        
        update_agent_weight.__name__ = "update_agent_weight"
        update_weight_tool = create_function_tool(update_agent_weight)
        
        # Override schema for update_agent_weight
        schema_update = {
            "type": "function",
            "function": {
                "name": "update_agent_weight",
                "description": (
                    "Update the weight of an agent based on performance review.\n\n"
                    "Agent weights influence how much their decisions contribute to final wallet distributions. "
                    "Weights should be between 0.0 and 1.0. Higher weights mean more influence on decisions.\n\n"
                    "Available agents: 'Fact Extractor', 'Trend Analyzer', 'Sentiment Analyst', 'Risk Analyzer', 'Fusion Synthesizer'\n\n"
                    "Args:\n"
                    "  agent_name: Name of the agent to update\n"
                    "  weight: New weight value (0.0 to 1.0)\n"
                    "  reason: Optional reason for the weight update"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the agent (e.g., 'Fact Extractor', 'Trend Analyzer', 'Sentiment Analyst', 'Risk Analyzer', 'Fusion Synthesizer')"
                        },
                        "weight": {
                            "type": "number",
                            "description": "New weight value (0.0 to 1.0). Higher weights = more influence.",
                            "minimum": 0.0,
                            "maximum": 1.0
                        },
                        "reason": {
                            "type": "string",
                            "description": "Optional reason for the weight update (e.g., 'Good performance in trend analysis')",
                            "default": ""
                        }
                    },
                    "required": ["agent_name", "weight"]
                }
            }
        }
        update_weight_tool.openai_tool_schema = schema_update
        if hasattr(update_weight_tool, '_openai_tool_schema'):
            update_weight_tool._openai_tool_schema = schema_update
        if hasattr(update_weight_tool, '_schema'):
            update_weight_tool._schema = schema_update
        
        # Generate advice tool
        def generate_advice(
            analysis_summary: str,
            performance_insights: str,
        ) -> Dict[str, Any]:
            """Generate advice for the next cycle based on ROI analysis and performance insights.
            
            This advice will be stored and can be retrieved by agents in the next cycle.
            
            Args:
                analysis_summary: Summary of ROI analysis (e.g., 'BTC performed well, ETH underperformed')
                performance_insights: Performance insights (e.g., 'Trend Analyzer had high accuracy')
            """
            return toolkit_instance.generate_advice(analysis_summary, performance_insights)
        
        generate_advice.__name__ = "generate_advice"
        advice_tool = create_function_tool(generate_advice)
        
        # Override schema for generate_advice
        schema_advice = {
            "type": "function",
            "function": {
                "name": "generate_advice",
                "description": (
                    "Generate advice for the next cycle based on ROI analysis and performance insights.\n\n"
                    "This advice will be stored in Redis and can be retrieved by agents in the next cycle "
                    "to improve their decision-making. Keep the description concise but actionable.\n\n"
                    "Args:\n"
                    "  analysis_summary: Brief summary of ROI analysis (e.g., 'BTC performed well, ETH underperformed')\n"
                    "  performance_insights: Performance insights about agents (e.g., 'Trend Analyzer had high accuracy, Risk Analyzer was too conservative')"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "analysis_summary": {
                            "type": "string",
                            "description": "Brief summary of ROI analysis"
                        },
                        "performance_insights": {
                            "type": "string",
                            "description": "Performance insights about agents and their decisions"
                        }
                    },
                    "required": ["analysis_summary", "performance_insights"]
                }
            }
        }
        advice_tool.openai_tool_schema = schema_advice
        if hasattr(advice_tool, '_openai_tool_schema'):
            advice_tool._openai_tool_schema = schema_advice
        if hasattr(advice_tool, '_schema'):
            advice_tool._schema = schema_advice
        
        # Get latest advice tool (for other agents to retrieve advice)
        def get_latest_advice() -> Dict[str, Any]:
            """Retrieve the latest advice generated by the review agent for the next cycle.
            
            Returns the most recent advice including analysis summary, performance insights, and recommendations.
            """
            return toolkit_instance.get_latest_advice()
        
        get_latest_advice.__name__ = "get_latest_advice"
        get_advice_tool = create_function_tool(get_latest_advice)
        
        # Override schema for get_latest_advice
        schema_get_advice = {
            "type": "function",
            "function": {
                "name": "get_latest_advice",
                "description": (
                    "Retrieve the latest advice generated by the review agent for the next cycle.\n\n"
                    "Returns the most recent advice including analysis summary, performance insights, and recommendations. "
                    "Use this at the start of a new cycle to understand what worked well and what needs improvement.\n\n"
                    "If no advice is available yet, returns a message indicating that review analysis is pending."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        get_advice_tool.openai_tool_schema = schema_get_advice
        if hasattr(get_advice_tool, '_openai_tool_schema'):
            get_advice_tool._openai_tool_schema = schema_get_advice
        if hasattr(get_advice_tool, '_schema'):
            get_advice_tool._schema = schema_get_advice
        
        return [
            analyze_roi_tool,
            update_weight_tool,
            advice_tool,
            get_advice_tool,
        ]

