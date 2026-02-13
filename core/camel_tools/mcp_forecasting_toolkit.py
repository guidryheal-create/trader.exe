"""
MCP Forecasting Toolkit for CAMEL

Provides CAMEL-compatible tools for interacting with the MCP forecasting API.
Enhanced with T-3 to T+3 timeline processing, compact CSV format, and better data structures
for agentic system compatibility.
"""
from typing import Dict, Any, List, Optional, Annotated, Literal
from pydantic import Field
from datetime import datetime, timezone, timedelta
from core.settings.config import settings
from core.logging import log
from core.clients.forecasting_client import ForecastingClient, ForecastingAPIError
from core.utils.asset_layers import get_layer1_assets, get_layer2_assets
from core.utils.dqn_ranking import rank_best_signals, rank_best_vs_worst_signals

# Standard crypto universe used in examples/prompts for trend/DQN tools
CRYPTO_STANDARD = (
    "crypto-standard",
    [
        "SAND-USD",
        "IMX-USD",
        "GALA-USD",
        "AXS-USD",
        "MANA-USD",
        "AAVE-USD",
        "ETH-USD",
        "BTC-USD",
        "XRP-USD",
        "ADA-USD",
        "SOL-USD",
        "SUI-USD",
        "DAI-USD",
    ],
)

try:
    from camel.toolkits import FunctionTool  # type: ignore
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False
    log.warning("CAMEL function tools not available. Install with: pip install 'camel-ai[tools]'")


class MCPForecastingToolkit:
    """Toolkit for MCP forecasting API endpoints."""
    
    def __init__(self, forecasting_client: Optional[ForecastingClient] = None, timeout: Optional[float] = None):
        """
        Initialize the toolkit.
        
        Args:
            forecasting_client: Optional ForecastingClient instance
            timeout: Optional timeout for requests
        """
        # ✅ Ensure API key is loaded from settings
        api_key = settings.mcp_api_key
        if not api_key:
            log.warning("MCP_API_KEY not found in settings. API requests may fail with 401 Unauthorized.")
        
        # ✅ Create client with increased timeout for reliability
        self.forecasting_client = forecasting_client or ForecastingClient({
            "base_url": settings.mcp_api_url,
            "api_key": api_key,  # Use from settings
            "mock_mode": settings.use_mock_services,
            "timeout": 60.0,  # Increased timeout for reliability
            "retry_attempts": 3,
            "retry_delay": 2.0
        })
        self._initialized = False
    
    async def initialize(self):
        """Initialize the forecasting client."""
        if not self._initialized:
            # ✅ CRITICAL: Ensure client is connected before use
            if not self.forecasting_client.client:
                await self.forecasting_client.connect()
            self._initialized = True
            log.info(f"✅ MCP Forecasting Toolkit initialized with base_url: {self.forecasting_client.base_url}")
    
    async def _ensure_connected(self):
        """
        Ensure the forecasting client is connected before making requests.
        
        ✅ Event Loop Isolation:
        - Each tool call runs in an isolated thread with its own event loop (via async_wrapper)
        - httpx.AsyncClient is bound to the event loop at creation time
        - We check if the client is bound to the current loop, and recreate if needed
        """
        if not self.forecasting_client.client:
            try:
                await self.forecasting_client.connect()
                self._initialized = True
            except Exception as e:
                log.warning(f"[MCPForecastingToolkit] Failed to connect client: {e}")
                self._initialized = False
                await self.initialize()
    
    def get_stock_forecast_tool(self):
        """Get tool for retrieving stock forecasts."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_stock_forecast(
            ticker: Annotated[str, Field(description=(
                "REQUIRED: Stock ticker symbol (e.g., 'BTC', 'ETH', 'SOL'). Extract from task: look for 'TICKER: BTC' "
                "or 'ticker: BTC' or just 'BTC' in the task text. Use the ticker symbol directly "
                "(e.g., 'BTC' not 'BTC-USD' unless explicitly stated). "
                f"Available crypto assets (standard set): {', '.join(CRYPTO_STANDARD[1])}."
            ))],
            interval: Annotated[
                str,
                Field(
                    description=(
                        "REQUIRED: Time interval. Must be one of: 'minutes', 'thirty', 'hours', or 'days'. "
                        "Extract from task: look for 'INTERVAL: days' or 'interval: days' or 'daily' in task text. "
                        "For daily analysis tasks, use 'days'."
                    )
                ),
            ]
        ) -> Dict[str, Any]:
            """
            Get price forecast for a specific ticker and interval from the MCP forecasting API.
            
            **CRITICAL**: Both ticker and interval are REQUIRED parameters. You MUST extract them from the task context.
            
            **Parameter Extraction Rules:**
            1. **ticker**: 
               - Look for "TICKER: BTC" or "ticker: BTC" or "ticker: 'BTC'" in task → use "BTC"
               - If task mentions "BTC", "ETH", "SOL", etc. → use that symbol as ticker
               - Examples: "BTC" → ticker="BTC", "ETH-USD" → ticker="ETH"
            
            2. **interval**:
               - Look for "INTERVAL: days" or "interval: days" or "interval: 'days'" in task → use "days"
               - If task mentions "daily" or "daily analysis" → use interval="days"
               - If task mentions "hourly" → use interval="hours"
               - Default: If no interval specified but task is about daily trading → use "days"
            
            **Examples:**
            - Task contains "TICKER: BTC" and "INTERVAL: days" → ticker="BTC", interval="days"
            - Task: "Analyze BTC for daily trading" → ticker="BTC", interval="days"
            - Task: "Get forecast for SOL" → ticker="SOL", interval="days" (default for daily)
            
            **IMPORTANT**: If you cannot find ticker or interval in the task, DO NOT call this function. Return an error instead.
            
            Args:
                ticker: Stock ticker symbol (REQUIRED - extract from task, examples: "BTC", "ETH", "SOL")
                interval: Time interval (REQUIRED - extract from task, must be: "minutes", "thirty", "hours", or "days")
                
            Returns:
                Forecast data including price predictions and confidence
            """
            try:
                # ✅ Validate required parameters
                if not ticker or ticker.strip() == "":
                    raise ValueError("ticker parameter is REQUIRED. Extract from task context (look for 'TICKER:' or ticker symbol like 'BTC', 'ETH', etc.)")
                # Normalize interval: default to 'days' for daily cycle if missing/invalid
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                
                # Convert ticker format if needed
                api_ticker = f"{ticker}-USD" if not ticker.endswith("-USD") else ticker
                
                # ✅ CRITICAL: Ensure client is connected before making requests
                try:
                    await toolkit_instance._ensure_connected()
                except Exception as connect_error:
                    log.error(f"[MCPForecastingToolkit] Connection error: {connect_error}")
                    return {
                        "success": False,
                        "error": f"Connection failed: {connect_error}",
                        "ticker": ticker,
                        "interval": interval_norm
                    }
                
                # ✅ Make request - event loop isolation is handled by async_wrapper
                result = await toolkit_instance.forecasting_client.get_stock_forecast(api_ticker, interval_norm)
                
                # ✅ Parse forecast data into T-3 to T+3 window (CSV-like structure) to keep prompts small
                forecast_data = result.get("forecast_data", [])
                if isinstance(forecast_data, list) and forecast_data:
                    now = datetime.now(timezone.utc)
                    
                    # Parse timestamps and calculate T deltas
                    parsed_forecasts = []
                    for entry in forecast_data:
                        if isinstance(entry, dict):
                            timestamp_str = entry.get("timestamp") or entry.get("Date") or entry.get("date")
                            if timestamp_str:
                                try:
                                    # Parse ISO timestamp
                                    if isinstance(timestamp_str, str):
                                        if "T" in timestamp_str:
                                            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                                        else:
                                            ts = datetime.strptime(timestamp_str, "%Y-%m-%d")
                                            ts = ts.replace(tzinfo=timezone.utc)
                                    else:
                                        continue
                                    
                                    # Calculate T delta (days from now)
                                    delta = (ts - now).total_seconds() / 86400
                                    t_delta = int(round(delta))
                                    
                                    # Only include T-3 to T+3 range
                                    if -3 <= t_delta <= 3:
                                        parsed_forecasts.append({
                                            "T": t_delta,
                                            "timestamp": ts.isoformat(),
                                            "forecast_price": entry.get("forecast") or entry.get("forecasting") or entry.get("price"),
                                            "actual_price": entry.get("close") or entry.get("price"),
                                            "prediction_date": entry.get("pred_date") or entry.get("prediction_time"),
                                        })
                                except Exception as e:
                                    log.debug(f"Failed to parse timestamp {timestamp_str}: {e}")
                                    continue
                    
                    # Sort by T delta
                    parsed_forecasts.sort(key=lambda x: x["T"])

                    # Fallback: if no entries in T-3..T+3, compress to latest 6 points
                    if not parsed_forecasts:
                        try:
                            def _parse_ts(ts_raw: Any) -> Optional[datetime]:
                                if not ts_raw:
                                    return None
                                if isinstance(ts_raw, str):
                                    if "T" in ts_raw:
                                        return datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                                    return datetime.strptime(ts_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                return None

                            enriched = []
                            for entry in forecast_data:
                                if not isinstance(entry, dict):
                                    continue
                                ts_raw = entry.get("timestamp") or entry.get("Date") or entry.get("date")
                                ts_parsed = _parse_ts(ts_raw)
                                if ts_parsed:
                                    enriched.append((ts_parsed, entry))

                            enriched.sort(key=lambda x: x[0])
                            latest = enriched[-6:]
                            
                            for idx, (ts_parsed, entry) in enumerate(latest):
                                t_delta = idx - (len(latest) - 1)
                                if -3 <= t_delta <= 3:
                                    parsed_forecasts.append({
                                        "T": t_delta,
                                        "timestamp": ts_parsed.isoformat(),
                                        "forecast_price": entry.get("forecast") or entry.get("forecasting") or entry.get("price"),
                                        "actual_price": entry.get("close") or entry.get("price"),
                                        "prediction_date": entry.get("pred_date") or entry.get("prediction_time"),
                                    })
                            parsed_forecasts.sort(key=lambda x: x["T"])
                        except Exception as e:
                            log.debug(f"Fallback compacting forecast window failed: {e}")
                    
                    # Keep only the single most relevant point (prefer T+1; else closest to T)
                    selected_entry = None
                    future_entries = [f for f in parsed_forecasts if f["T"] >= 1]
                    if future_entries:
                        selected_entry = sorted(future_entries, key=lambda x: x["T"])[0]
                    elif parsed_forecasts:
                        selected_entry = sorted(parsed_forecasts, key=lambda x: abs(x["T"]))[0]
                    
                    compact_list = [selected_entry] if selected_entry else []
                    
                    # Add structured summary and compact data
                    result["forecast_timeline"] = compact_list
                    result["t_range"] = {
                        "min": compact_list[0]["T"] if compact_list else None,
                        "max": compact_list[0]["T"] if compact_list else None,
                    }
                    # Compact CSV (single row) for minimal tokens
                    csv_rows = ["T,ts_utc,pred_date,forecast_price,actual_price"]
                    for f in compact_list:
                        csv_rows.append(
                            f'{f["T"]},{f["timestamp"]},{f.get("prediction_date") or ""},{f.get("forecast_price") or ""},{f.get("actual_price") or ""}'
                        )
                    result["forecast_csv_window"] = "\n".join(csv_rows)
                    result["agentic_csv"] = result["forecast_csv_window"]
                    # Replace raw forecast_data with compact single-point window to avoid prompt bloat
                    result["forecast_data_compact"] = compact_list
                    result["forecast_data"] = compact_list
                
                return {
                    "success": True,
                    "ticker": ticker,
                    "interval": interval_norm,
                    "forecast": result
                }
            except ForecastingAPIError as e:
                log.error(f"Forecasting API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
            except Exception as e:
                log.error(f"Error getting stock forecast: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
        
        get_stock_forecast.__name__ = "get_stock_forecast"
        get_stock_forecast.__doc__ = (
            "Get price forecast for a specific ticker and interval from the MCP forecasting API. "
            "Returns forecast data in structured format with T-3 to T+3 timeline (T delta in days from current time). "
            "Each entry includes: T (days delta), timestamp, forecast_price, actual_price, prediction_date. "
            "Use this to analyze price trends from historical (T-3) to future predictions (T+3) while keeping context compact. "
            f"Available crypto assets (standard set): {', '.join(CRYPTO_STANDARD[1])}."
        )
        
        # ✅ Use create_function_tool for proper async handling
        from core.camel_tools.async_wrapper import create_function_tool
        
        # Build explicit schema
        schema = {
            "type": "function",
            "function": {
                "name": "get_stock_forecast",
                "description": get_stock_forecast.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "REQUIRED: Stock ticker symbol (e.g., 'BTC', 'ETH', 'SOL'). Extract from task: look for 'TICKER: BTC' or 'ticker: BTC' or just 'BTC' in the task text. Use the ticker symbol directly (e.g., 'BTC' not 'BTC-USD' unless explicitly stated). Available crypto assets (standard set): "
                                           + ", ".join(CRYPTO_STANDARD[1]) + ".",
                        },
                        "interval": {
                            "type": "string",
                            "description": "REQUIRED: Time interval. Must be one of: 'minutes', 'thirty', 'hours', or 'days'. Extract from task: look for 'INTERVAL: days' or 'interval: days' or 'daily' in task text. For daily analysis tasks, use 'days'.",
                            "enum": ["minutes", "thirty", "hours", "days"]
                        }
                    },
                    "required": ["ticker", "interval"],
                    "additionalProperties": False
                }
            }
        }
        
        tool = create_function_tool(
            get_stock_forecast,
            tool_name="get_stock_forecast",
            description=get_stock_forecast.__doc__
        )
        tool.openai_tool_schema = schema
        return tool
    
    def get_action_recommendation_tool(self):
        """Get tool for retrieving action recommendations."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_action_recommendation(
            ticker: Annotated[str, Field(description="REQUIRED: Stock ticker symbol (e.g., 'BTC', 'ETH', 'SOL'). Extract from task: look for 'TICKER: BTC' or 'ticker: BTC' or just 'BTC' in the task text. Use the ticker symbol directly (e.g., 'BTC' not 'BTC-USD' unless explicitly stated).")],
            interval: Annotated[str, Field(description="REQUIRED: Time interval. Must be one of: 'minutes', 'thirty', 'hours', or 'days'. Extract from task: look for 'INTERVAL: days' or 'interval: days' or 'daily' in task text. For daily analysis tasks, use 'days'.")]
        ) -> Dict[str, Any]:
            """
            Get DQN action recommendation (BUY/SELL/HOLD) with confidence, Q-values, and forecasting data.
            
            **CRITICAL**: Both ticker and interval are REQUIRED parameters. You MUST extract them from the task context.
            
            **Parameter Extraction Rules:**
            1. **ticker**: 
               - Look for "TICKER: BTC" or "ticker: BTC" or "ticker: 'BTC'" in task → use "BTC"
               - If task mentions "BTC", "ETH", "SOL", etc. → use that symbol as ticker
               - Examples: "BTC" → ticker="BTC", "ETH-USD" → ticker="ETH"
            
            2. **interval**:
               - Look for "INTERVAL: days" or "interval: days" or "interval: 'days'" in task → use "days"
               - If task mentions "daily" or "daily analysis" → use interval="days"
               - If task mentions "hourly" → use interval="hours"
               - Default: If no interval specified but task is about daily trading → use "days"
            
            **Examples:**
            - Task contains "TICKER: BTC" and "INTERVAL: days" → ticker="BTC", interval="days"
            - Task: "Analyze BTC for daily trading" → ticker="BTC", interval="days"
            - Task: "Get DQN recommendation for SOL" → ticker="SOL", interval="days" (default for daily)
            
            **IMPORTANT**: If you cannot find ticker or interval in the task, DO NOT call this function. Return an error instead.
            
            Args:
                ticker: Stock ticker symbol (REQUIRED - extract from task, examples: "BTC", "ETH", "SOL")
                interval: Time interval (REQUIRED - extract from task, must be: "minutes", "thirty", "hours", or "days")
                
            Returns:
                Action recommendation with confidence, Q-values, forecast distributions, and prediction timestamps
            """
            try:
                # ✅ Validate required parameters
                if not ticker or ticker.strip() == "":
                    raise ValueError("ticker parameter is REQUIRED. Extract from task context (look for 'TICKER:' or ticker symbol like 'BTC', 'ETH', etc.)")
                # Normalize interval: default to 'days' for daily cycle if missing/invalid
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                
                api_ticker = f"{ticker}-USD" if not ticker.endswith("-USD") else ticker
                
                # ✅ CRITICAL: Ensure client is connected before making requests
                try:
                    await toolkit_instance._ensure_connected()
                except Exception as connect_error:
                    log.error(f"[MCPForecastingToolkit] Connection error: {connect_error}")
                    return {
                        "success": False,
                        "error": f"Connection failed: {connect_error}",
                        "ticker": ticker,
                        "interval": interval_norm
                    }
                
                # ✅ Make request - event loop isolation is handled by async_wrapper
                result = await toolkit_instance.forecasting_client.get_action_recommendation(api_ticker, interval_norm)
                
                # Map action values to names
                action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
                action_value = result.get("action", 1)
                action_name = action_map.get(action_value, "HOLD")
                
                # ✅ Extract T+1 prediction date and forecasting distributions
                from datetime import datetime, timezone, timedelta
                
                # Calculate T+1 date based on interval
                interval_to_hours = {
                    "minutes": 1/60,  # 1 minute = 1/60 hour
                    "thirty": 0.5,   # 30 minutes = 0.5 hour
                    "hours": 1,       # 1 hour
                    "days": 24        # 1 day = 24 hours
                }
                hours_ahead = interval_to_hours.get(interval, 1)
                t_plus_1_date = (datetime.now(timezone.utc) + timedelta(hours=hours_ahead)).isoformat()
                
                # Extract Q-values as forecasting distribution (probability distribution over actions)
                q_values = result.get("q_values", [])
                forecast_distribution = {
                    "SELL": q_values[0] if len(q_values) > 0 else 0.33,
                    "HOLD": q_values[1] if len(q_values) > 1 else 0.33,
                    "BUY": q_values[2] if len(q_values) > 2 else 0.34
                }
                
                # Get prediction timestamp if available
                prediction_timestamp = result.get("updated_at") or result.get("prediction_timestamp")
                if prediction_timestamp and isinstance(prediction_timestamp, (int, float)):
                    # Convert timestamp to ISO format
                    pred_date = datetime.fromtimestamp(prediction_timestamp, tz=timezone.utc).isoformat()
                else:
                    pred_date = datetime.now(timezone.utc).isoformat()
                
                return {
                    "success": True,
                    "ticker": ticker,
                    "interval": interval_norm,
                    "action": action_value,
                    "action_name": action_name,
                    "confidence": result.get("action_confidence", 0.5),
                    "forecast_price": result.get("forecast_price"),
                    "current_price": result.get("current_price"),
                    "q_values": q_values,
                    # ✅ Enhanced DQN data with distributions and T+1 dates
                    "forecast_distribution": forecast_distribution,  # Probability distribution over SELL/HOLD/BUY
                    "t_plus_1_date": t_plus_1_date,  # Date/time when forecast applies (T+1)
                    "prediction_timestamp": pred_date,  # When prediction was made
                    "prediction_time_delta_seconds": result.get("prediction_time_delta_seconds"),  # Time since prediction
                }
            except ForecastingAPIError as e:
                log.error(f"Forecasting API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
            except Exception as e:
                log.error(f"Error getting action recommendation: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
        
        get_action_recommendation.__name__ = "get_action_recommendation"
        get_action_recommendation.__doc__ = (
            "Get DQN action recommendation (BUY/SELL/HOLD) with confidence, Q-values, forecasting distributions, "
            "T+1 prediction date, and price forecasts for a ticker. The underlying DQN policy is trained on a ~T+14 horizon "
            "(14-day forecast window), so treat this as a medium-term signal rather than an intraday tick. "
            "Returns comprehensive DQN data including probability distributions over actions and prediction timestamps. "
            f"Available crypto assets (standard set): {', '.join(CRYPTO_STANDARD[1])}."
        )
        
        # ✅ Use create_function_tool for proper async handling
        from core.camel_tools.async_wrapper import create_function_tool
        
        schema = {
            "type": "function",
            "function": {
                "name": "get_action_recommendation",
                "description": get_action_recommendation.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "REQUIRED: Stock ticker symbol (e.g., 'BTC', 'ETH', 'SOL'). Extract from task: look for 'TICKER: BTC' or 'ticker: BTC' or just 'BTC' in the task text. Use the ticker symbol directly (e.g., 'BTC' not 'BTC-USD' unless explicitly stated). Available crypto assets (standard set): "
                                           + ", ".join(CRYPTO_STANDARD[1]) + ".",
                        },
                        "interval": {
                            "type": "string",
                            "description": "REQUIRED: Time interval. Must be one of: 'minutes', 'thirty', 'hours', or 'days'. Extract from task: look for 'INTERVAL: days' or 'interval: days' or 'daily' in task text. For daily analysis tasks, use 'days'.",
                            "enum": ["minutes", "thirty", "hours", "days"]
                        }
                    },
                    "required": ["ticker", "interval"],
                    "additionalProperties": False
                }
            }
        }
        
        tool = create_function_tool(
            get_action_recommendation,
            tool_name="get_action_recommendation",
            description=get_action_recommendation.__doc__
        )
        tool.openai_tool_schema = schema
        return tool
    
    def get_trend_analysis_tool(self):
        """Get tool for trend analysis with %change calculations."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_trend_analysis(
            ticker: Annotated[str, Field(description=(
                "REQUIRED: Stock ticker symbol (e.g., 'BTC', 'ETH', 'SOL'). Extract from task: look for 'TICKER: BTC' "
                "or 'ticker: BTC' or just 'BTC' in the task text. Use the ticker symbol directly "
                "(e.g., 'BTC' not 'BTC-USD' unless explicitly stated). "
                f"Available crypto assets (standard set): {', '.join(CRYPTO_STANDARD[1])}."
            ))],
            interval: Annotated[
                str,
                Field(
                    description=(
                        "REQUIRED: Time interval. Must be one of: 'minutes', 'thirty', 'hours', or 'days'. "
                        "Extract from task: look for 'INTERVAL: days' or 'interval: days' or 'daily' in task text. "
                        "For daily analysis tasks, use 'days'."
                    )
                ),
            ]
        ) -> Dict[str, Any]:
            """
            Get trend analysis with %change variations relative to REAL T0 price (actual current market price).
            
            **KEY APPROACH**: Uses REAL T0 price as base (0% change), all forecasted variations (T+1 to T+14) 
            are calculated relative to this real baseline. This avoids bias by anchoring all forecasts to the same real price.
            
            Returns CSV format: ticker,T+1,T+2,...,T+14\nBTC-USD,+2%,+3%,+4%,...
            Only forecasted data (T+1 to T+14) is shown, but variations are based on real T0 price.
            This reduces data size by ~50% and makes variations immediately understandable.
            
            **IMPORTANT**: 
            - Base price (T0) is REAL (actual current market price) - not forecasted
            - All variations (T+1 to T+14) are FORECASTED relative to real T0
            - Only the trend matters - small decalage between real and forecast T0 is acceptable
            
            **CRITICAL**: Both ticker and interval are REQUIRED parameters. You MUST extract them from the task context.
            
            **Parameter Extraction Rules:**
            1. **ticker**: 
               - Look for "TICKER: BTC" or "ticker: BTC" or just "BTC" in task → use "BTC"
               - Examples: "BTC" → ticker="BTC", "ETH-USD" → ticker="ETH"
            
            2. **interval**:
               - Look for "INTERVAL: days" or "interval: days" or "daily" in task → use "days"
               - Default: If no interval specified but task is about daily trading → use "days"
            
            **Returns:**
            - real_t0_price: The actual current market price (REAL, not forecasted)
            - trend_direction: "bullish", "bearish", or "sideways"
            - trend_magnitude: "strong", "moderate", or "weak"
            - csv_format: CSV string with variations (ticker,T+1,T+2,...,T+14\nBTC-USD,+2%,+3%,...)
            - t_plus_1_to_14_forecasts: List of forecasts from T+1 to T+14 with %change relative to real T0
            - summary: Human-readable trend summary
            
            Args:
                ticker: Stock ticker symbol (REQUIRED - extract from task, examples: "BTC", "ETH", "SOL")
                interval: Time interval (REQUIRED - extract from task, must be: "minutes", "thirty", "hours", or "days")
                
            Returns:
                Trend analysis with %change calculations and direction indicators
            """
            try:
                # Validate required parameters
                if not ticker or ticker.strip() == "":
                    raise ValueError("ticker parameter is REQUIRED. Extract from task context (look for 'TICKER:' or ticker symbol like 'BTC', 'ETH', etc.)")
                # Normalize interval: default to 'days' for daily cycle if missing/invalid
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                
                # Convert ticker format if needed
                api_ticker = f"{ticker}-USD" if not ticker.endswith("-USD") else ticker
                
                # ✅ CRITICAL: Ensure client is connected before making requests
                try:
                    await toolkit_instance._ensure_connected()
                except Exception as connect_error:
                    log.error(f"[MCPForecastingToolkit] Connection error: {connect_error}")
                    return {
                        "success": False,
                        "error": f"Connection failed: {connect_error}",
                        "ticker": ticker,
                        "interval": interval_norm
                    }
                
                # ✅ Get trend analysis - uses REAL T0 price as base, all forecasted variations (T+1 to T+14) relative to real T0
                result = await toolkit_instance.forecasting_client.get_trend_analysis(api_ticker, interval_norm)
                
                return {
                    "success": True,
                    "ticker": ticker,
                    "interval": interval_norm,
                    "trend_analysis": result
                }
            except ForecastingAPIError as e:
                log.error(f"Forecasting API error: {e}")
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
            except Exception as e:
                log.error(f"Error getting trend analysis: {e}")
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
        
        get_trend_analysis.__name__ = "get_trend_analysis"
        get_trend_analysis.__doc__ = (
            "Get FORECASTED trend analysis with %change variations relative to REAL T0 price (actual current market price). "
            "Returns CSV: ticker,T+1,T+2,...,T+14\\nBTC-USD,+2%,+3%,+4%,... "
            "Uses REAL T0 price (actual current market price) as base (0% change), all forecasted variations (T+1 to T+14) "
            "are calculated relative to this real baseline. This avoids bias by anchoring all forecasts to the same real price. "
            "Only forecasted data (T+1 to T+14) is shown, but variations are based on real T0 price. "
            "**IMPORTANT**: Base (T0) is REAL (actual current market price), variations (T+1 to T+14) are FORECASTED relative to real T0. "
            "Only the trend matters - small decalage between real and forecast T0 is acceptable. "
            "Returns trend direction (bullish/bearish/sideways), magnitude (strong/moderate/weak), "
            "and CSV format with variations. Focus on T+1 to T+14 for trading decisions. "
            f"Available crypto assets (standard set): {', '.join(CRYPTO_STANDARD[1])}."
        )
        
        # ✅ Use create_function_tool for proper async handling
        from core.camel_tools.async_wrapper import create_function_tool
        
        schema = {
            "type": "function",
            "function": {
                "name": "get_trend_analysis",
                "description": (
                    "Get FORECASTED trend analysis with %change variations relative to REAL T0 price (actual current market price). "
                    "Returns CSV: ticker,T+1,T+2,...,T+14\\nBTC-USD,+2%,+3%,+4%,... "
                    "Uses REAL T0 price as base (0% change), all forecasted variations (T+1 to T+14) are calculated relative to this real baseline. "
                    "This avoids bias by anchoring all forecasts to the same real price. "
                    "Only forecasted data (T+1 to T+14) is shown, but variations are based on real T0 price. "
                    "**IMPORTANT**: Base (T0) is REAL, variations (T+1 to T+14) are FORECASTED relative to real T0. "
                    "Focus on T+1 to T+14 for trading decisions. Returns trend direction and magnitude. "
                    f"Available crypto assets: {', '.join(CRYPTO_STANDARD[1])}."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "REQUIRED: Stock ticker symbol (e.g., 'BTC', 'ETH', 'SOL'). Extract from task: look for 'TICKER: BTC' or 'ticker: BTC' or just 'BTC' in the task text. Use the ticker symbol directly (e.g., 'BTC' not 'BTC-USD' unless explicitly stated). Available crypto assets (standard set): "
                                           + ", ".join(CRYPTO_STANDARD[1]) + ".",
                        },
                        "interval": {
                            "type": "string",
                            "description": "REQUIRED: Time interval. Must be one of: 'minutes', 'thirty', 'hours', or 'days'. Extract from task: look for 'INTERVAL: days' or 'interval: days' or 'daily' in task text. For daily analysis tasks, use 'days'.",
                            "enum": ["minutes", "thirty", "hours", "days"]
                        }
                    },
                    "required": ["ticker", "interval"],
                    "additionalProperties": False
                }
            }
        }
        
        tool = create_function_tool(
            get_trend_analysis,
            tool_name="get_trend_analysis",
            description=get_trend_analysis.__doc__
        )
        tool.openai_tool_schema = schema
        return tool
    
    def list_available_tickers_tool(self):
        """Get tool for listing available tickers."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def list_available_tickers() -> Dict[str, Any]:
            """
            Get list of all available tickers with DQN data.
            
            Returns:
                List of available tickers with their metadata
            """
            try:
                tickers = await toolkit_instance.forecasting_client.get_available_tickers()
                
                # Filter tickers with DQN data if available
                tickers_with_dqn = [
                    ticker for ticker in tickers
                    if ticker.get("has_dqn", False) or isinstance(ticker, str)
                ]
                
                return {
                    "success": True,
                    "tickers": tickers_with_dqn,
                    "count": len(tickers_with_dqn)
                }
            except ForecastingAPIError as e:
                log.error(f"Forecasting API error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "tickers": [],
                    "count": 0
                }
            except Exception as e:
                log.error(f"Error listing tickers: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "tickers": [],
                    "count": 0
                }
        
        list_available_tickers.__name__ = "list_available_tickers"
        list_available_tickers.__doc__ = "Get list of all available tickers with DQN forecasting data"
        
        # ✅ Use create_function_tool for proper async handling
        from core.camel_tools.async_wrapper import create_function_tool
        
        tool = create_function_tool(list_available_tickers)
        return tool
    
    def get_metrics_tool(self):
        """Get tool for retrieving model metrics."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_metrics(
            ticker: Annotated[str, Field(description="Stock ticker symbol (e.g., BTC-USD)")],
            interval: Annotated[str, Field(description="Time interval: minutes, thirty, hours, or days")]
        ) -> Dict[str, Any]:
            """
            Get model performance metrics for a ticker.
            
            Args:
                ticker: Stock ticker symbol
                interval: Time interval
                
            Returns:
                Model performance metrics including accuracy, Sharpe ratio, etc.
            """
            try:
                # Normalize interval
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                
                api_ticker = f"{ticker}-USD" if not ticker.endswith("-USD") else ticker
                
                # ✅ CRITICAL: Ensure client is connected before making requests
                try:
                    await toolkit_instance._ensure_connected()
                except Exception as connect_error:
                    log.error(f"[MCPForecastingToolkit] Connection error: {connect_error}")
                    return {
                        "success": False,
                        "error": f"Connection failed: {connect_error}",
                        "ticker": ticker,
                        "interval": interval_norm
                    }
                
                result = await toolkit_instance.forecasting_client.get_model_metrics(api_ticker, interval_norm)
                
                return {
                    "success": True,
                    "ticker": ticker,
                    "interval": interval_norm,
                    "metrics": result
                }
            except ForecastingAPIError as e:
                log.error(f"Forecasting API error: {e}")
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
            except Exception as e:
                log.error(f"Error getting metrics: {e}")
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                return {
                    "success": False,
                    "error": str(e),
                    "ticker": ticker,
                    "interval": interval_norm
                }
        
        get_metrics.__name__ = "get_metrics"
        get_metrics.__doc__ = "Get model performance metrics (accuracy, Sharpe ratio, etc.) for a ticker"
        
        # ✅ Use create_function_tool for proper async handling
        from core.camel_tools.async_wrapper import create_function_tool
        
        tool = create_function_tool(get_metrics)
        return tool
    
    def get_best_signals_tool(self):
        """Get MCP tool for ranking best BUY/SELL DQN signals."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_best_signals(
            side: Annotated[str, Field(description="Signal side to rank: 'buy', 'sell', or 'both'.")] = "buy",
            limit: Annotated[int, Field(description="Maximum number of assets per side (1–50).")] = 10,
            interval: Annotated[str, Field(description="DQN interval: 'minutes', 'thirty', 'hours', or 'days'.")] = "days",
            universe: Annotated[Optional[List[str]], Field(description="Optional base tickers to restrict universe (e.g. ['BTC','ETH']).")] = None,
        ) -> Dict[str, Any]:
            try:
                side_norm: Literal["buy", "sell", "both"]
                if side not in ("buy", "sell", "both"):
                    side_norm = "buy"
                else:
                    side_norm = side  # type: ignore[assignment]
                limit_norm = max(1, min(int(limit), 50))
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                
                base_universe = universe or get_layer1_assets(enabled_only=True)
                if not base_universe:
                    return {
                        "success": False,
                        "error": "No assets available in universe",
                        "side": side_norm,
                        "limit": limit_norm,
                        "signals": [],
                    }
                
                await toolkit_instance._ensure_connected()
                raw_records = await toolkit_instance.forecasting_client.get_dqn_signals_for_universe(
                    base_tickers=base_universe,
                    interval=interval_norm,
                )
                ranked = rank_best_signals(raw_records, side_norm, limit_norm)
                ranked.update(
                    {
                        "success": True,
                        "interval": interval_norm,
                        "universe_size": len(base_universe),
                    }
                )
                return ranked
            except ForecastingAPIError as e:
                log.error(f"Forecasting API error in get_best_signals: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "side": side,
                    "limit": limit,
                    "signals": [],
                }
            except Exception as e:
                log.error(f"Error in get_best_signals: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "side": side,
                    "limit": limit,
                    "signals": [],
                }
        
        get_best_signals.__name__ = "get_best_signals"
        get_best_signals.__doc__ = (
            "Rank assets by DQN BUY/SELL signal strength over a small universe. "
            "Uses q_values[2] (BUY) and q_values[0] (SELL) with action_confidence fallbacks."
        )
        
        from core.camel_tools.async_wrapper import create_function_tool
        
        schema = {
            "type": "function",
            "function": {
                "name": "get_best_signals",
                "description": get_best_signals.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "side": {
                            "type": "string",
                            "enum": ["buy", "sell", "both"],
                            "description": "Signal side to rank.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Maximum assets per side (1–50).",
                        },
                        "interval": {
                            "type": "string",
                            "enum": ["minutes", "thirty", "hours", "days"],
                            "description": "DQN interval.",
                        },
                        "universe": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional base tickers to restrict universe.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        
        tool = create_function_tool(
            get_best_signals,
            tool_name="get_best_signals",
            description=get_best_signals.__doc__,
        )
        tool.openai_tool_schema = schema
        return tool
    
    def get_best_vs_worst_signals_tool(self):
        """Get MCP tool for ranking best vs worst BUY/SELL DQN signals."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_best_vs_worst_signals(
            side: Annotated[str, Field(description="Signal side to rank: 'buy', 'sell', or 'both'.")] = "buy",
            limit: Annotated[int, Field(description="Maximum assets per best/worst bucket (1–50).")] = 5,
            interval: Annotated[str, Field(description="DQN interval: 'minutes', 'thirty', 'hours', or 'days'.")] = "days",
            universe: Annotated[Optional[List[str]], Field(description="Optional base tickers to restrict universe.")] = None,
        ) -> Dict[str, Any]:
            try:
                side_norm: Literal["buy", "sell", "both"]
                if side not in ("buy", "sell", "both"):
                    side_norm = "buy"
                else:
                    side_norm = side  # type: ignore[assignment]
                limit_norm = max(1, min(int(limit), 50))
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                
                base_universe = universe or get_layer1_assets(enabled_only=True)
                if not base_universe:
                    return {
                        "success": False,
                        "error": "No assets available in universe",
                        "side": side_norm,
                        "limit": limit_norm,
                    }
                
                await toolkit_instance._ensure_connected()
                raw_records = await toolkit_instance.forecasting_client.get_dqn_signals_for_universe(
                    base_tickers=base_universe,
                    interval=interval_norm,
                )
                ranked = rank_best_vs_worst_signals(raw_records, side_norm, limit_norm)
                ranked.update(
                    {
                        "success": True,
                        "interval": interval_norm,
                        "universe_size": len(base_universe),
                    }
                )
                return ranked
            except ForecastingAPIError as e:
                log.error(f"Forecasting API error in get_best_vs_worst_signals: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "side": side,
                    "limit": limit,
                }
            except Exception as e:
                log.error(f"Error in get_best_vs_worst_signals: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "side": side,
                    "limit": limit,
                }
        
        get_best_vs_worst_signals.__name__ = "get_best_vs_worst_signals"
        get_best_vs_worst_signals.__doc__ = (
            "Rank best and worst assets by DQN BUY/SELL signal strength over a curated universe."
        )
        
        from core.camel_tools.async_wrapper import create_function_tool
        
        schema = {
            "type": "function",
            "function": {
                "name": "get_best_vs_worst_signals",
                "description": get_best_vs_worst_signals.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "side": {
                            "type": "string",
                            "enum": ["buy", "sell", "both"],
                            "description": "Signal side to rank.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Maximum assets per best/worst bucket (1–50).",
                        },
                        "interval": {
                            "type": "string",
                            "enum": ["minutes", "thirty", "hours", "days"],
                            "description": "DQN interval.",
                        },
                        "universe": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional base tickers to restrict universe.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        
        tool = create_function_tool(
            get_best_vs_worst_signals,
            tool_name="get_best_vs_worst_signals",
            description=get_best_vs_worst_signals.__doc__,
        )
        tool.openai_tool_schema = schema
        return tool
    
    def get_all_layer1_tool(self):
        """Get MCP tool returning curated L1 assets (optionally with latest DQN signals)."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_all_layer1(
            interval: Annotated[Optional[str], Field(description="Optional DQN interval for signals.")] = None,
            with_signals: Annotated[bool, Field(description="Whether to include latest DQN BUY/SELL scores.")] = False,
        ) -> Dict[str, Any]:
            try:
                bases = get_layer1_assets(enabled_only=True)
                if not bases:
                    return {
                        "success": False,
                        "error": "No L1 assets available",
                        "assets": [],
                    }
                
                interval_norm: Optional[str] = None
                if interval:
                    interval_norm = interval.strip().lower()
                    if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                        interval_norm = "days"
                
                if not with_signals or not interval_norm:
                    return {
                        "success": True,
                        "interval": interval_norm,
                        "assets": bases,
                    }
                
                await toolkit_instance._ensure_connected()
                raw_records = await toolkit_instance.forecasting_client.get_dqn_signals_for_universe(
                    base_tickers=bases,
                    interval=interval_norm,
                )
                ranked = rank_best_signals(raw_records, "both", len(bases))
                return {
                    "success": True,
                    "interval": interval_norm,
                    "assets": bases,
                    "ranked": ranked,
                }
            except Exception as e:
                log.error(f"Error in get_all_layer1: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "assets": [],
                }
        
        get_all_layer1.__name__ = "get_all_layer1"
        get_all_layer1.__doc__ = (
            "Return a curated set of L1 assets (e.g. BTC, ETH, SOL). "
            "Optionally include latest DQN BUY/SELL scores when interval and with_signals are provided."
        )
        
        from core.camel_tools.async_wrapper import create_function_tool
        
        schema = {
            "type": "function",
            "function": {
                "name": "get_all_layer1",
                "description": get_all_layer1.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "interval": {
                            "type": "string",
                            "enum": ["minutes", "thirty", "hours", "days"],
                            "description": "Optional DQN interval; required if with_signals=True.",
                        },
                        "with_signals": {
                            "type": "boolean",
                            "description": "Whether to include latest DQN BUY/SELL scores for each L1 asset.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        
        tool = create_function_tool(
            get_all_layer1,
            tool_name="get_all_layer1",
            description=get_all_layer1.__doc__,
        )
        tool.openai_tool_schema = schema
        return tool
    
    def get_layer2_signals_tool(self):
        """Get MCP tool for ranking L2 assets under a main network (e.g. ETH, SOL)."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")
        
        toolkit_instance = self
        
        async def get_layer2_signals(
            side: Annotated[str, Field(description="Signal side to rank: 'buy', 'sell', or 'both'.")] = "buy",
            network: Annotated[str, Field(description="Main network base ticker (e.g. 'ETH', 'SOL').")] = "ETH",
            limit: Annotated[int, Field(description="Maximum assets per side (1–50).")] = 10,
            interval: Annotated[str, Field(description="DQN interval: 'minutes', 'thirty', 'hours', or 'days'.")] = "days",
        ) -> Dict[str, Any]:
            try:
                side_norm: Literal["buy", "sell", "both"]
                if side not in ("buy", "sell", "both"):
                    side_norm = "buy"
                else:
                    side_norm = side  # type: ignore[assignment]
                limit_norm = max(1, min(int(limit), 50))
                interval_norm = (interval or "").strip().lower()
                if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                    interval_norm = "days"
                
                bases = get_layer2_assets(network, enabled_only=True)
                if not bases:
                    return {
                        "success": False,
                        "error": f"No L2 assets configured for network {network}",
                        "side": side_norm,
                        "limit": limit_norm,
                        "signals": [],
                    }
                
                await toolkit_instance._ensure_connected()
                raw_records = await toolkit_instance.forecasting_client.get_dqn_signals_for_universe(
                    base_tickers=bases,
                    interval=interval_norm,
                )
                ranked = rank_best_signals(raw_records, side_norm, limit_norm)
                ranked.update(
                    {
                        "success": True,
                        "interval": interval_norm,
                        "network": network.upper(),
                        "universe_size": len(bases),
                    }
                )
                return ranked
            except Exception as e:
                log.error(f"Error in get_layer2_signals: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "side": side,
                    "limit": limit,
                    "signals": [],
                }
        
        get_layer2_signals.__name__ = "get_layer2_signals"
        get_layer2_signals.__doc__ = (
            "Rank tokens in a given L2 ecosystem (e.g. ETH L2s) by DQN BUY/SELL signal strength."
        )
        
        from core.camel_tools.async_wrapper import create_function_tool
        
        schema = {
            "type": "function",
            "function": {
                "name": "get_layer2_signals",
                "description": get_layer2_signals.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "side": {
                            "type": "string",
                            "enum": ["buy", "sell", "both"],
                            "description": "Signal side to rank.",
                        },
                        "network": {
                            "type": "string",
                            "description": "Main network base ticker (e.g. 'ETH', 'SOL').",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Maximum assets per side (1–50).",
                        },
                        "interval": {
                            "type": "string",
                            "enum": ["minutes", "thirty", "hours", "days"],
                            "description": "DQN interval.",
                        },
                    },
                    "required": ["network"],
                    "additionalProperties": False,
                },
            },
        }
        
        tool = create_function_tool(
            get_layer2_signals,
            tool_name="get_layer2_signals",
            description=get_layer2_signals.__doc__,
        )
        tool.openai_tool_schema = schema
        return tool
    
    def get_all_stock_forecasts_tool(self):
        """Get tool for retrieving forecasts for multiple tickers with CSV summary."""
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL tools not installed")

        toolkit_instance = self

        async def get_all_stock_forecasts(tickers: List[str], interval: str = "days") -> Dict[str, Any]:
            """
            Fetch FORECASTED variations for multiple tickers (T-6 to T-1: past trend, T+1 to T+14: future forecast) relative to REAL T0 price.
            
            Returns data in CSV format: ticker,T-6,T-5,...,T-1,T+1,T+2,...,T+14\nBTC-USD,-0.5%,...,+2%,+3%,+4%,...\nETH-USD,-0.3%,...,+1.5%,+2.5%,+3.5%,...
            Uses REAL T0 price (actual current market price) as base (0% change), all forecasted variations are calculated 
            relative to this real baseline. This avoids bias by anchoring all forecasts to the same real price.
            Historical data (T-6 to T-1) shows past trend context, future data (T+1 to T+14) shows forecasted future.
            T0 column is omitted (it's 0% by definition relative to real T0). T0 is forecasted (not real) but very close to real T0.
            The small diff (forecasted T0 - real T0) explains why T0 column is omitted.
            
            **IMPORTANT**: 
            - Base (T0) is REAL (actual current market price), variations (T-6 to T-1, T+1 to T+14) are FORECASTED relative to real T0
            - T-6 to T-1 shows past trend context, T+1 to T+14 shows future forecast
            - T0 is forecasted (not real) but very close to real T0: forecasted T0 - real T0 = small diff
            """
            if not tickers or not isinstance(tickers, list):
                raise ValueError("tickers parameter is REQUIRED as a non-empty list of symbols.")
            if not interval or interval.strip() == "":
                raise ValueError("interval parameter is REQUIRED (e.g., 'days').")

            # Normalize interval
            interval_norm = (interval or "").strip().lower()
            if interval_norm not in ["minutes", "thirty", "hours", "days"]:
                interval_norm = "days"

            # ✅ CRITICAL: Ensure client is connected before making requests
            try:
                await toolkit_instance._ensure_connected()
            except Exception as connect_error:
                log.error(f"[MCPForecastingToolkit] Connection error: {connect_error}")
                return {
                    "success": False,
                    "error": f"Connection failed: {connect_error}",
                    "interval": interval_norm,
                    "tickers": tickers,
                    "forecast_csv_window": "",
                    "results": []
                }
            
            # ✅ Use get_trend_analysis for each ticker to get CSV format with variations
            # This is much more efficient - returns %change variations instead of absolute prices
            combined_csv_rows = []
            csv_header = None  # Will be set from first successful result
            per_ticker = []

            for ticker in tickers:
                api_ticker = f"{ticker}-USD" if isinstance(ticker, str) and not ticker.endswith("-USD") else ticker
                try:
                    # ✅ Use get_trend_analysis which returns CSV format with variations
                    trend_result = await toolkit_instance.forecasting_client.get_trend_analysis(api_ticker, interval_norm)
                    
                    # Extract CSV format from trend analysis
                    csv_format = trend_result.get("csv_format", "")
                    if csv_format:
                        csv_lines = csv_format.strip().split("\n")
                        if len(csv_lines) >= 2:
                            # First line is header, second line is data
                            if csv_header is None:
                                csv_header = csv_lines[0]  # Set header from first ticker
                                combined_csv_rows.append(csv_header)
                            
                            # Add data row (second line) - this contains ticker and variations
                            if len(csv_lines) >= 2:
                                combined_csv_rows.append(csv_lines[1])  # Data row: BTC-USD,-0.5%,...,+2%,+3%,+4%,... (T-6 to T-1, T+1 to T+14, relative to real T0)
                    
                    per_ticker.append({
                        "ticker": ticker,
                        "success": True,
                        "trend_analysis": trend_result,
                        "csv_format": csv_format,
                    })
                    
                except ForecastingAPIError as e:
                    log.warning(f"[MCPForecastingToolkit] Error getting trend analysis for {ticker}: {e}")
                    per_ticker.append({"ticker": ticker, "success": False, "error": str(e)})
                    continue
                except Exception as e:
                    # Log unexpected errors but continue processing other tickers
                    log.warning(f"[MCPForecastingToolkit] Unexpected error for {ticker}: {e}")
                    per_ticker.append({"ticker": ticker, "success": False, "error": str(e)})
                    continue

            # Build combined CSV (header + all data rows)
            combined_csv = "\n".join(combined_csv_rows) if combined_csv_rows else ""

            return {
                "success": True,
                "interval": interval_norm,
                "tickers": tickers,
                "data_type": "FORECASTED",  # ✅ Explicitly mark as forecasted
                "forecast_window": "T-6 to T-1 (past trend), T+1 to T+14 (future forecast)",  # ✅ Forecast window
                "forecast_csv_window": combined_csv,  # ✅ CSV format: ticker,T-6,T-5,...,T-1,T+1,T+2,...,T+14\nBTC-USD,-0.5%,...,+2%,+3%,... (relative to real T0)
                "results": per_ticker,
            }

        get_all_stock_forecasts.__name__ = "get_all_stock_forecasts"
        get_all_stock_forecasts.__doc__ = (
            "Fetch FORECASTED variations for multiple tickers (T-6 to T-1: past trend, T+1 to T+14: future forecast) relative to REAL T0 price. "
            "Returns CSV: ticker,T-6,T-5,...,T-1,T+1,T+2,...,T+14\\nBTC-USD,-0.5%,...,+2%,+3%,+4%,...\\nETH-USD,-0.3%,...,+1.5%,+2.5%,+3.5%,... "
            "Uses REAL T0 price (actual current market price) as base (0% change), all forecasted variations are calculated "
            "relative to this real baseline. This avoids bias by anchoring all forecasts to the same real price. "
            "Historical data (T-6 to T-1) shows past trend context, future data (T+1 to T+14) shows forecasted future. "
            "T0 column is omitted (it's 0% by definition relative to real T0). T0 is forecasted (not real) but very close to real T0. "
            "The small diff (forecasted T0 - real T0) explains why T0 column is omitted. "
            "**IMPORTANT**: Base (T0) is REAL, variations (T-6 to T-1, T+1 to T+14) are FORECASTED relative to real T0. "
            "Agentic consumers should use forecast_csv_window string to avoid JSON parsing."
        )

        from core.camel_tools.async_wrapper import create_function_tool

        schema = {
            "type": "function",
            "function": {
                "name": "get_all_stock_forecasts",
                "description": get_all_stock_forecasts.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tickers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "REQUIRED: list of ticker symbols (e.g., ['BTC','ETH','SOL']). Returns FORECASTED variations in CSV format (T+1 to T+14).",
                        },
                        "interval": {
                            "type": "string",
                            "description": "REQUIRED: Time interval. Must be one of: 'minutes', 'thirty', 'hours', or 'days'.",
                            "enum": ["minutes", "thirty", "hours", "days"]
                        }
                    },
                    "required": ["tickers", "interval"],
                    "additionalProperties": False
                }
            }
        }

        tool = create_function_tool(get_all_stock_forecasts)
        tool.openai_tool_schema = schema
        return tool
    
    def get_tools(self) -> List:
        """Get all tools in this toolkit as FunctionTool instances."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            log.warning("CAMEL tools not available, returning empty list")
            return []
        
        tools = []
        try:
            tools.append(self.get_stock_forecast_tool())
            tools.append(self.get_action_recommendation_tool())
            tools.append(self.get_trend_analysis_tool())
            tools.append(self.get_all_stock_forecasts_tool())
            tools.append(self.list_available_tickers_tool())
            tools.append(self.get_metrics_tool())
            tools.append(self.get_best_signals_tool())
            tools.append(self.get_best_vs_worst_signals_tool())
            tools.append(self.get_all_layer1_tool())
            tools.append(self.get_layer2_signals_tool())
            log.info(f"MCPForecastingToolkit: returning {len(tools)} FunctionTool instances with explicit schemas")
        except Exception as e:
            log.error(f"Failed to create MCP forecasting tools: {e}", exc_info=True)
        
        return tools
    
    def get_all_tools(self) -> List:
        """Alias for get_tools() for backward compatibility."""
        return self.get_tools()

