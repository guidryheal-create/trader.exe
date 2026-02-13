"""
Toolkit registry for CAMEL runtime.

This module exposes a registry that builds the FunctionTool collections
used by CAMEL ChatAgents and Workforces.  The registry de-duplicates tool
construction and keeps the mapping between logical capabilities and the
underlying service clients (forecasting MCP, DEX simulator, research
sources, etc.).
"""

from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any, Awaitable, Callable, Dict, List, Optional

from camel.toolkits import FunctionTool

from core.settings.config import settings
from core.clients.forecasting_client import ForecastingClient
from core.logging import log
from core.models import asset_registry
from core.clients.guidry_stats_client import guidry_cloud_stats
from core.camel_tools.market_data_toolkit import MarketDataToolkit
from core.camel_tools.api_forecasting_toolkit import APIForecastingToolkit
from core.camel_tools.review_pipeline_toolkit import ReviewPipelineToolkit
from core.camel_tools.signal_logging_toolkit import SignalLoggingToolkit
from core.camel_tools.search_toolkit import SearchToolkit
from core.camel_tools.polymarket_toolkit import EnhancedPolymarketToolkit
from core.camel_tools.polymarket_data_toolkit import PolymarketDataToolkit
from core.camel_tools.uviswap_toolkit import UviSwapToolkit
from core.camel_tools.watchlist_toolkit import WatchlistToolkit
from core.camel_tools.wallet_analysis_toolkit import WalletAnalysisToolkit
from core.camel_tools.auto_enhancement_toolkit import AutoEnhancementToolkit
from core.camel_runtime.utils import (
    ToolValidation,
    ClientInitialization,
    LoggingMarkers,
    ToolkitInitialization,
)

# ✅ Removed: conversation_logging_toolkit - no longer needed for RSS flux trading
# ✅ Removed: wallet_distribution_toolkit - deprecated, use Polymarket positions instead

try:
    from core.camel_tools.asknews_toolkit import AskNewsToolkit
except ImportError:  # pragma: no cover - optional dependency
    AskNewsToolkit = None  # type: ignore

try:
    from core.camel_tools.google_research_toolkit import GoogleResearchToolkit
except ImportError:  # pragma: no cover - optional dependency
    GoogleResearchToolkit = None  # type: ignore

try:
    from core.camel_tools.yahoo_finance_toolkit import get_yahoo_finance_toolkit
except ImportError:  # pragma: no cover - optional dependency
    get_yahoo_finance_toolkit = None  # type: ignore

# ✅ YouTube Transcript toolkit disabled - not needed for trading


AsyncFn = Callable[..., Awaitable[Any]]


class ToolkitRegistry:
    """
    Build and cache FunctionTool instances for CAMEL agents.

    The registry lazily initialises shared service clients (Forecasting MCP,
    DEX simulator, research APIs) and wraps the high level async functions as
    CAMEL `FunctionTool` objects as required by the official tooling
    interface.  This matches the guidance from the CAMEL docs that tools
    should be provided as `FunctionTool` instances rather than raw callables
    so that argument schemas can be inferred automatically.
    """

    def __init__(self) -> None:
        self._forecasting_client: Optional[ForecastingClient] = None
        self._tool_cache: Dict[str, FunctionTool] = {}
        self._lock = asyncio.Lock()
        self._api_toolkit: Optional[APIForecastingToolkit] = None
        self._asknews_toolkit: Optional[AskNewsToolkit] = None
        self._search_toolkit: Optional[GoogleResearchToolkit] = None
        self._review_toolkit: Optional[ReviewPipelineToolkit] = None
        self._signal_logging_toolkit: Optional[SignalLoggingToolkit] = None
        self._polymarket_toolkit: Optional[EnhancedPolymarketToolkit] = None
        self._polymarket_data_toolkit: Optional[PolymarketDataToolkit] = None
        self._uviswap_toolkit: Optional[UviSwapToolkit] = None
        self._watchlist_toolkit: Optional[WatchlistToolkit] = None
        self._wallet_analysis_toolkit: Optional[WalletAnalysisToolkit] = None
        self._auto_enhancement_toolkit: Optional[AutoEnhancementToolkit] = None
        self._search_toolkit_new: Optional[SearchToolkit] = None
        self._yahoo_finance_toolkit = None
        LoggingMarkers.info(LoggingMarkers.TOOLKIT_REGISTRY, "Initialized (removed conversation_logging, wallet_distribution)")

    def _is_forecasting_enabled(self) -> bool:
        """Return True if forecasting tools should be loaded."""
        return ClientInitialization.is_forecasting_enabled()

    async def ensure_clients(self) -> None:
        """Initialise shared service clients once."""
        async with self._lock:
            # Forecasting: skip entirely when FORECASTING_MODE=disabled (standalone Polymarket)
            if self._is_forecasting_enabled() and self._forecasting_client is None:
                use_mock = getattr(settings, "forecasting_mode", "api") == "mock"
                self._forecasting_client = ForecastingClient(
                    {
                        "base_url": settings.mcp_api_url,
                        "api_key": settings.mcp_api_key,
                        "mock_mode": use_mock,
                    }
                )
                try:
                    await self._forecasting_client.connect()
                    log.info("Toolkit registry connected Forecasting MCP client")
                except Exception as exc:
                    log.warning(
                        "Forecasting client connect failed: %s (forecasting tools disabled)",
                        exc,
                        exc_info=True,
                    )
                    self._forecasting_client = None

                if self._forecasting_client:
                    try:
                        self._api_toolkit = APIForecastingToolkit(self._forecasting_client)
                        await self._api_toolkit.initialize()
                        log.info("Toolkit registry prepared API Forecasting toolkit")
                    except Exception as exc:
                        log.error(
                            "API Forecasting toolkit initialization failed: %s",
                            exc,
                            exc_info=True,
                        )
                        self._api_toolkit = None
            elif not self._is_forecasting_enabled():
                log.info(
                    "Forecasting disabled (FORECASTING_MODE=disabled), skipping forecasting tools"
                )

            if self._asknews_toolkit is None and AskNewsToolkit is not None:
                try:
                    self._asknews_toolkit = AskNewsToolkit(api_key=settings.asknews_api_key)
                    await self._asknews_toolkit.initialize()
                    log.info("Toolkit registry prepared AskNews toolkit")
                except Exception as exc:
                    log.debug("AskNews toolkit initialisation failed: %s", exc)
                    self._asknews_toolkit = None

            # ✅ COMPLETELY DISABLED: Google Research Toolkit - not needed, has wrong tools
            # User explicitly requested complete removal - Google toolkit is not useful for trading
            self._search_toolkit = None
            LoggingMarkers.info(LoggingMarkers.TOOLKIT_REGISTRY, "✅ Google Research Toolkit COMPLETELY DISABLED")

            if self._review_toolkit is None:
                try:
                    self._review_toolkit = ReviewPipelineToolkit()
                    await self._review_toolkit.initialize()
                    log.info("Toolkit registry prepared Review pipeline toolkit")
                except Exception as exc:  # pragma: no cover - optional dependency
                    log.debug("Review pipeline toolkit initialisation failed: %s", exc)
                    self._review_toolkit = None

            # Initialize new toolkits
            if self._signal_logging_toolkit is None:
                try:
                    self._signal_logging_toolkit = SignalLoggingToolkit()
                    await self._signal_logging_toolkit.initialize()
                    log.info("Toolkit registry prepared Signal Logging toolkit")
                except Exception as exc:
                    log.debug("Signal Logging toolkit initialisation failed: %s", exc)
                    self._signal_logging_toolkit = None

            # ✅ Polymarket Toolkit - core for RSS flux trading
            if self._polymarket_toolkit is None:
                try:
                    self._polymarket_toolkit = EnhancedPolymarketToolkit()
                    self._polymarket_toolkit.initialize()
                    LoggingMarkers.info(LoggingMarkers.POLYMARKET, "Initialized toolkit (discovery + analysis + trading)")
                except Exception as exc:
                    LoggingMarkers.error(LoggingMarkers.POLYMARKET, "Toolkit init failed: %s", exc)
                    self._polymarket_toolkit = None

            # ✅ Polymarket Data Toolkit - focused market data + sizing helpers
            if self._polymarket_data_toolkit is None:
                try:
                    self._polymarket_data_toolkit = PolymarketDataToolkit()
                    self._polymarket_data_toolkit.initialize()
                    LoggingMarkers.info(LoggingMarkers.POLYMARKET, "Initialized data toolkit (market data + sizing)")
                except Exception as exc:
                    LoggingMarkers.error(LoggingMarkers.POLYMARKET, "Data toolkit init failed: %s", exc)
                    self._polymarket_data_toolkit = None

            # ✅ DEX toolkits for shared workforce usage
            if self._watchlist_toolkit is None:
                try:
                    self._watchlist_toolkit = WatchlistToolkit()
                    log.info("Toolkit registry prepared Watchlist toolkit")
                except Exception as exc:
                    log.warning("Watchlist toolkit initialization failed: %s", exc)
                    self._watchlist_toolkit = None

            if self._wallet_analysis_toolkit is None:
                try:
                    self._wallet_analysis_toolkit = WalletAnalysisToolkit(
                        redis_client=self._watchlist_toolkit.redis if self._watchlist_toolkit else None
                    )
                    log.info("Toolkit registry prepared Wallet Analysis toolkit")
                except Exception as exc:
                    log.warning("Wallet analysis toolkit initialization failed: %s", exc)
                    self._wallet_analysis_toolkit = None

            if self._auto_enhancement_toolkit is None:
                try:
                    self._auto_enhancement_toolkit = AutoEnhancementToolkit(
                        redis_client=self._watchlist_toolkit.redis if self._watchlist_toolkit else None
                    )
                    log.info("Toolkit registry prepared Auto Enhancement toolkit")
                except Exception as exc:
                    log.warning("Auto enhancement toolkit initialization failed: %s", exc)
                    self._auto_enhancement_toolkit = None

            if self._uviswap_toolkit is None:
                try:
                    self._uviswap_toolkit = UviSwapToolkit(watchlist_toolkit=self._watchlist_toolkit)
                    log.info("Toolkit registry prepared UviSwap toolkit")
                except Exception as exc:
                    # Likely missing wallet/rpc env; keep optional
                    log.warning("UviSwap toolkit initialization failed (optional): %s", exc)
                    self._uviswap_toolkit = None

            # ✅ REMOVED: conversation_logging_toolkit - no longer needed for RSS flux
            # ✅ REMOVED: wallet_distribution_toolkit - deprecated in favor of Polymarket positions

            if self._search_toolkit_new is None:
                try:
                    self._search_toolkit_new = SearchToolkit()
                    await self._search_toolkit_new.initialize()
                    log.info("Toolkit registry prepared Search toolkit")
                except Exception as exc:
                    log.debug("Search toolkit initialisation failed: %s", exc)
                    self._search_toolkit_new = None

            # Initialize Yahoo Finance toolkit
            if self._yahoo_finance_toolkit is None and get_yahoo_finance_toolkit is not None:
                try:
                    self._yahoo_finance_toolkit = get_yahoo_finance_toolkit()
                    await self._yahoo_finance_toolkit.initialize()
                    log.info("Toolkit registry prepared Yahoo Finance toolkit")
                except Exception as exc:
                    log.debug("Yahoo Finance toolkit initialisation failed: %s", exc)
                    self._yahoo_finance_toolkit = None


    async def get_default_toolset(self) -> List[FunctionTool]:
        """
        Return the default toolkit collection for the trading workforce.

        The returned list always contains fresh FunctionTool wrappers so that
        CAMEL can introspect parameter metadata, but the underlying async
        functions reuse shared clients.
        
        Tools are validated before being added to the toolset.
        """
        await self.ensure_clients()

        tools = []
        
        # ✅ Import tool validator
        from core.pipelines.tool_validator import validate_tool, validate_tool_schema
        
        # Build core tools with error handling and validation
        # Forecasting-dependent tools only when FORECASTING_MODE != "disabled"
        core_tools_map = {
            "get_guidry_cloud_api_stats": self._tool_get_guidry_stats,
        }
        if self._is_forecasting_enabled() and self._forecasting_client:
            core_tools_map.update({
                "list_supported_assets": self._tool_list_supported_assets,
                "get_ohlc": self._tool_get_ohlc,
                "get_model_metrics": self._tool_get_model_metrics,
            })


        for tool_name, tool_fn in core_tools_map.items():
            try:
                tool = self._tool(tool_name, tool_fn)
                
                # ✅ Validate tool before adding to toolset
                if not validate_tool(tool):
                    log.warning(f"Tool validation failed for {tool_name}, skipping")
                    continue
                
                if not validate_tool_schema(tool):
                    log.warning(f"Tool schema validation failed for {tool_name}, skipping")
                    continue
                
                tools.append(tool)
                log.debug(f"✅ Built and validated tool: {tool_name}")
            except Exception as e:
                log.error(f"Failed to build tool {tool_name}: {type(e).__name__}: {e}", exc_info=True)
                # Continue with other tools even if one fails
                continue

        # ✅ Add optional toolkit tools - verify they're FunctionTool instances and validate them
        FT = FunctionTool
        from core.pipelines.tool_validator import validate_tool, validate_tool_schema

        # Prefer explicit-schema API toolkit for forecasting/DQN
        if self._api_toolkit:
            try:
                api_tools = self._api_toolkit.get_all_tools()
                validated = []
                for t in api_tools:
                    if isinstance(t, FT) and validate_tool(t) and validate_tool_schema(t):
                        validated.append(t)
                    else:
                        log.warning("API toolkit tool failed validation or wrong type: %s", getattr(t, "name", "unknown"))
                tools.extend(validated)
                log.info("Added %d API forecasting tools with explicit schemas", len(validated))
            except Exception as exc:
                log.error("Failed to add API forecasting toolkit tools: %s", exc, exc_info=True)
        
        if self._asknews_toolkit:
            try:
                asknews_tools = self._asknews_toolkit.get_all_tools()
                # Verify all tools are FunctionTool instances and validate them
                valid_tools = []
                for t in asknews_tools:
                    if isinstance(t, FT):
                        if validate_tool(t) and validate_tool_schema(t):
                            valid_tools.append(t)
                        else:
                            log.warning(f"AskNews tool validation failed: {getattr(t, 'name', 'unknown')}")
                    else:
                        log.warning(f"AskNews toolkit returned invalid tool (not FunctionTool): {type(t)}")
                if len(valid_tools) != len(asknews_tools):
                    log.warning(f"AskNews toolkit: {len(asknews_tools) - len(valid_tools)} tools failed validation")
                tools.extend(valid_tools)
                log.debug(f"Added {len(valid_tools)} AskNews tools (all FunctionTool)")
            except Exception as e:
                log.warning(f"Failed to add AskNews tools: {e}", exc_info=True)
        
        # ✅ DISABLED: Google Research Toolkit is disabled - not useful for trading
        # if self._search_toolkit:
        #     ... (disabled)
        
        if self._review_toolkit:
            try:
                review_tools = self._review_toolkit.get_all_tools()
                # Verify all tools are FunctionTool instances and validate them
                valid_tools = []
                for t in review_tools:
                    if isinstance(t, FT):
                        if validate_tool(t) and validate_tool_schema(t):
                            valid_tools.append(t)
                        else:
                            log.warning(f"Review pipeline tool validation failed: {getattr(t, 'name', 'unknown')}")
                    else:
                        log.warning(f"Review pipeline toolkit returned invalid tool (not FunctionTool): {type(t)}")
                if len(valid_tools) != len(review_tools):
                    log.warning(f"Review pipeline toolkit: {len(review_tools) - len(valid_tools)} tools failed validation")
                tools.extend(valid_tools)
                log.debug(f"Added {len(valid_tools)} Review pipeline tools (all FunctionTool)")
            except Exception as e:
                log.warning(f"Failed to add Review pipeline tools: {e}", exc_info=True)

        # Add Signal Logging toolkit
        if self._signal_logging_toolkit:
            try:
                signal_tools = self._signal_logging_toolkit.get_all_tools()
                valid_tools = []
                for t in signal_tools:
                    if isinstance(t, FT):
                        if validate_tool(t) and validate_tool_schema(t):
                            valid_tools.append(t)
                tools.extend(valid_tools)
                log.debug(f"Added {len(valid_tools)} Signal Logging tools")
            except Exception as e:
                log.warning(f"Failed to add Signal Logging tools: {e}", exc_info=True)

        # ✅ Add Polymarket Toolkit - core trading tools
        if self._polymarket_toolkit:
            try:
                polymarket_tools = self._polymarket_toolkit.get_tools()
                valid_tools = []
                for t in polymarket_tools:
                    if isinstance(t, FT):
                        if validate_tool(t) and validate_tool_schema(t):
                            valid_tools.append(t)
                        else:
                            log.warning(f"Polymarket tool validation failed: {getattr(t, 'name', 'unknown')}")
                    else:
                        log.warning(f"Polymarket toolkit returned invalid tool (not FunctionTool): {type(t)}")
                tools.extend(valid_tools)
                log.info(f"[TOOLKIT REGISTRY] Added {len(valid_tools)} Polymarket trading tools")
            except Exception as e:
                log.error(f"[TOOLKIT REGISTRY] Failed to add Polymarket tools: {e}", exc_info=True)

        # ✅ Add Polymarket Data Toolkit tools
        if self._polymarket_data_toolkit:
            try:
                data_tools = self._polymarket_data_toolkit.get_tools()
                valid_tools = []
                for t in data_tools:
                    if isinstance(t, FT):
                        if validate_tool(t) and validate_tool_schema(t):
                            valid_tools.append(t)
                        else:
                            log.warning(f"Polymarket data tool validation failed: {getattr(t, 'name', 'unknown')}")
                    else:
                        log.warning(f"Polymarket data toolkit returned invalid tool (not FunctionTool): {type(t)}")
                tools.extend(valid_tools)
                log.info(f"[TOOLKIT REGISTRY] Added {len(valid_tools)} Polymarket data tools")
            except Exception as e:
                log.error(f"[TOOLKIT REGISTRY] Failed to add Polymarket data tools: {e}", exc_info=True)

        # ✅ Add DEX toolkits (shared workforce for both polymarket + dex processes)
        if self._uviswap_toolkit:
            try:
                uviswap_tools = self._uviswap_toolkit.get_tools()
                valid_tools = []
                for t in uviswap_tools:
                    if isinstance(t, FT) and validate_tool(t) and validate_tool_schema(t):
                        valid_tools.append(t)
                tools.extend(valid_tools)
                log.info("[TOOLKIT REGISTRY] Added %d UviSwap tools", len(valid_tools))
            except Exception as e:
                log.warning("Failed to add UviSwap tools: %s", e, exc_info=True)

        if self._watchlist_toolkit:
            try:
                watchlist_tools = self._watchlist_toolkit.get_tools()
                valid_tools = []
                for t in watchlist_tools:
                    if isinstance(t, FT) and validate_tool(t) and validate_tool_schema(t):
                        valid_tools.append(t)
                tools.extend(valid_tools)
                log.info("[TOOLKIT REGISTRY] Added %d Watchlist tools", len(valid_tools))
            except Exception as e:
                log.warning("Failed to add Watchlist tools: %s", e, exc_info=True)

        if self._wallet_analysis_toolkit:
            try:
                wallet_tools = self._wallet_analysis_toolkit.get_tools()
                valid_tools = []
                for t in wallet_tools:
                    if isinstance(t, FT) and validate_tool(t) and validate_tool_schema(t):
                        valid_tools.append(t)
                tools.extend(valid_tools)
                log.info("[TOOLKIT REGISTRY] Added %d Wallet analysis tools", len(valid_tools))
            except Exception as e:
                log.warning("Failed to add Wallet analysis tools: %s", e, exc_info=True)

        if self._auto_enhancement_toolkit:
            try:
                enhancement_tools = self._auto_enhancement_toolkit.get_tools()
                valid_tools = []
                for t in enhancement_tools:
                    if isinstance(t, FT) and validate_tool(t) and validate_tool_schema(t):
                        valid_tools.append(t)
                tools.extend(valid_tools)
                log.info("[TOOLKIT REGISTRY] Added %d Auto enhancement tools", len(valid_tools))
            except Exception as e:
                log.warning("Failed to add Auto enhancement tools: %s", e, exc_info=True)

        # ✅ REMOVED: Conversation Logging toolkit - no longer needed for RSS flux
        # ✅ REMOVED: Wallet Distribution toolkit - deprecated in favor of Polymarket positions

        # Add Search toolkit
        if self._search_toolkit_new:
            try:
                search_tools = self._search_toolkit_new.get_all_tools()
                valid_tools = []
                for t in search_tools:
                    if isinstance(t, FT):
                        if validate_tool(t) and validate_tool_schema(t):
                            valid_tools.append(t)
                tools.extend(valid_tools)
                log.debug(f"Added {len(valid_tools)} Search tools")
            except Exception as e:
                log.warning(f"Failed to add Search tools: {e}", exc_info=True)

        # Add Yahoo Finance toolkit tools
        if self._yahoo_finance_toolkit:
            try:
                yahoo_tool_fns = {
                    "search_financial_news": self._yahoo_finance_toolkit.get_search_news_tool(),
                    "get_financial_quote": self._yahoo_finance_toolkit.get_quote_tool(),
                    # get_historical_price_data removed - not used
                }
                valid_tools = []
                for tool_name, tool_fn in yahoo_tool_fns.items():
                    try:
                        tool = self._tool(tool_name, tool_fn)
                        if validate_tool(tool) and validate_tool_schema(tool):
                            valid_tools.append(tool)
                        else:
                            log.warning(f"Yahoo Finance tool validation failed: {tool_name}")
                    except Exception as e:
                        log.warning(f"Failed to build Yahoo Finance tool {tool_name}: {e}")
                if len(valid_tools) != len(yahoo_tool_fns):
                    log.warning(f"Yahoo Finance toolkit: {len(yahoo_tool_fns) - len(valid_tools)} tools failed validation")
                tools.extend(valid_tools)
                log.debug(f"Added {len(valid_tools)} Yahoo Finance tools (all FunctionTool)")
            except Exception as e:
                log.warning(f"Failed to add Yahoo Finance tools: {e}", exc_info=True)


        # ✅ Final validation: ensure ALL tools are FunctionTool instances
        from camel.toolkits import FunctionTool as FT
        valid_tools = [t for t in tools if isinstance(t, FT)]
        invalid_count = len(tools) - len(valid_tools)
        
        if invalid_count > 0:
            log.error(f"❌ {invalid_count} tools are NOT FunctionTool instances! This will cause CAMEL workforce initialization to fail.")
            log.error("Invalid tools:")
            for tool in tools:
                if not isinstance(tool, FT):
                    log.error(f"  - {type(tool)}: {tool}")
            # Return only valid tools to prevent workforce initialization failure
            tools = valid_tools
        
        # ✅ Filter out irrelevant/broken tools
        # These tools cause workforce failures or are not relevant for trading
        # ✅ Use ToolValidation utility to filter irrelevant tools
        filtered_tools, removed_count = ToolValidation.validate_and_filter_tools(tools, require_function_tool=True)
        if removed_count > 0:
            LoggingMarkers.info(
                LoggingMarkers.TOOLKIT_REGISTRY,
                f"Filtered out {removed_count} irrelevant/broken tools. {len(filtered_tools)} trading-relevant tools remain"
            )
            tools = filtered_tools
        
        LoggingMarkers.info(LoggingMarkers.TOOLKIT_REGISTRY, f"Built {len(tools)} total FunctionTool instances for CAMEL workforce")
        return tools

    # ------------------------------------------------------------------
    # Direct helpers for non-CAMEL callers (legacy agents/pipelines)
    # ------------------------------------------------------------------

    async def get_stock_forecast(self, ticker: str, interval: str) -> Dict[str, Any]:
        await self.ensure_clients()
        return await self._tool_get_stock_forecast(ticker, interval)

    async def get_action_recommendation(self, ticker: str, interval: str) -> Dict[str, Any]:
        await self.ensure_clients()
        return await self._tool_get_action_recommendation(ticker, interval)

    async def list_supported_assets(self) -> Dict[str, Any]:
        await self.ensure_clients()
        return await self._tool_list_supported_assets()

    async def get_ohlc(self, ticker: str, interval: str, limit: int = 200) -> Dict[str, Any]:
        await self.ensure_clients()
        return await self._tool_get_ohlc(ticker, interval, limit)

    async def get_model_metrics(self, ticker: str, interval: str) -> Dict[str, Any]:
        await self.ensure_clients()
        return await self._tool_get_model_metrics(ticker, interval)

    def _tool(self, name: str, fn: AsyncFn) -> FunctionTool:
        """
        Wrap an async function into a FunctionTool, caching the schema.

        CAMEL's FunctionTool handles the automatic argument inspection and
        JSON schema generation.  The registry memoises wrappers so repeated
        requests do not rebuild the schema.
        
        ✅ PURE CAMEL: Uses shared async wrapper for proper event loop handling.
        Handles both functions and methods correctly.
        """
        if name in self._tool_cache:
            return self._tool_cache[name]

        try:
            # ✅ Handle methods vs functions: if it's a method, wrap it as a function
            import inspect
            if inspect.ismethod(fn):
                # Create a wrapper function that calls the method
                async def method_wrapper(*args, **kwargs):
                    return await fn(*args, **kwargs)
                method_wrapper.__name__ = name
                method_wrapper.__doc__ = fn.__doc__
                fn_to_wrap = method_wrapper
            else:
                fn_to_wrap = fn
                # Ensure function has __name__ attribute
                if not hasattr(fn_to_wrap, '__name__'):
                    fn_to_wrap.__name__ = name
            
            # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
            from core.camel_tools.async_wrapper import create_function_tool
            tool = create_function_tool(fn_to_wrap, tool_name=name)
        except (TypeError, AttributeError) as exc:
            log.error("Failed to wrap tool %s: %s", name, exc)
            raise

        # Normalise schema/name so downstream agents see stable identifiers.
        # ✅ CRITICAL: Ensure full docstring is in the description field for LLM
        try:
            schema = tool.get_openai_tool_schema()
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning("Unable to fetch schema for tool %s: %s", name, exc)
            schema = None

        if schema:
            schema = dict(schema)
            function_schema = dict(schema.get("function", {}))
            function_schema["name"] = name
            
            # ✅ CRITICAL: Include full docstring in description so LLM sees parameter extraction instructions
            # The docstring contains critical parameter extraction rules
            doc = None
            if inspect.ismethod(fn):
                doc = fn.__doc__
            elif hasattr(fn, '__doc__'):
                doc = fn.__doc__
            
            if doc:
                # Use the full docstring as description (includes parameter extraction rules)
                function_schema["description"] = doc.strip()
            elif "description" not in function_schema or not function_schema["description"]:
                # Fallback to function name if no docstring
                function_schema["description"] = name
            
            schema["function"] = function_schema
            tool.openai_tool_schema = schema

        if hasattr(tool, "name"):
            try:
                setattr(tool, "name", name)
            except Exception:
                pass

        self._tool_cache[name] = tool
        return tool

    # ---------------------------------------------------------------------
    # Forecasting helpers
    # ---------------------------------------------------------------------

    async def _tool_get_stock_forecast(self, ticker: str, interval: str) -> Dict[str, Any]:
        """
        Fetch OHLC / forecast data for a ticker & interval via the MCP client.
        """
        if not self._forecasting_client:
            raise RuntimeError("Forecasting client is not initialised")

        symbol = asset_registry.get_symbol(ticker.upper())
        result = await self._forecasting_client.get_stock_forecast(symbol, interval)
        return {"success": True, "ticker": ticker, "interval": interval, "forecast": result}

    async def _tool_get_action_recommendation(self, ticker: str, interval: str) -> Dict[str, Any]:
        """
        Fetch DQN action and confidence for the supplied ticker/interval.
        """
        if not self._forecasting_client:
            raise RuntimeError("Forecasting client is not initialised")

        symbol = asset_registry.get_symbol(ticker.upper())
        result = await self._forecasting_client.get_action_recommendation(symbol, interval)
        return {"success": True, "ticker": ticker, "interval": interval, "action": result}

    async def _tool_list_supported_assets(self) -> Dict[str, Any]:
        """
        List available asset metadata from the forecasting service.
        """
        if not self._forecasting_client:
            raise RuntimeError("Forecasting client is not initialised")

        assets = await self._forecasting_client.get_available_tickers()
        enabled = await self._forecasting_client.get_enabled_assets()
        await asset_registry.update_assets(assets, enabled)
        return {"success": True, "assets": asset_registry.get_assets()}

    async def _tool_get_ohlc(self, ticker: str, interval: str, limit: int = 200) -> Dict[str, Any]:
        """
        Retrieve OHLC candles for the supplied ticker/interval.
        """
        if not self._forecasting_client:
            raise RuntimeError("Forecasting client is not initialised")

        symbol = asset_registry.get_symbol(ticker.upper())
        candles = await self._forecasting_client.get_ohlc(symbol, interval, limit=limit)
        return {"success": True, "ticker": ticker, "interval": interval, "candles": candles}

    async def _tool_get_model_metrics(self, ticker: str, interval: str) -> Dict[str, Any]:
        """
        Retrieve model diagnostics (Sharpe, accuracy, etc.) for a ticker.
        """
        if not self._forecasting_client:
            raise RuntimeError("Forecasting client is not initialised")

        symbol = asset_registry.get_symbol(ticker.upper())
        metrics = await self._forecasting_client.get_model_metrics(symbol, interval)
        return {"success": True, "ticker": ticker, "interval": interval, "metrics": metrics}



# shared singleton to avoid repeated initialisation
toolkit_registry = ToolkitRegistry()


async def build_default_tools() -> List[FunctionTool]:
    """Convenience helper mirroring ToolkitRegistry.get_default_toolset."""
    return await toolkit_registry.get_default_toolset()
