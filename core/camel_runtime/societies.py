"""
Trading Workforce Society configuration.

Defines a CAMEL Workforce tailored for the trading system.  The society
instantiates the coordinator, task agent, and worker agent blueprints so
that we can reuse them both in the long running orchestrator and inside
pipeline executions.
"""

from __future__ import annotations

import os
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Deque

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.societies.workforce import Workforce
from camel.logger import get_logger
from camel.toolkits import (
    MathToolkit,
    RetrievalToolkit,
)

from core.models.camel_models import CamelModelFactory
from core.camel_runtime.registries import build_default_tools
from core.memory.ollama_embedding import OllamaEmbedding

logger = get_logger(__name__)

# ✅ Module-level configuration
# Neo4j is disabled by default to prevent segmentation faults in non-Docker environments
NEO4J_DISABLED = os.getenv('DISABLE_NEO4J', 'true').lower() in ('true', '1', 'yes')

# ✅ CRITICAL: Completely disable GoogleMapsToolkit by preventing its initialization
# CAMEL's GoogleMapsToolkit auto-adds irrelevant tools (weather, geocode, etc.) that we don't need
# Set GOOGLE_API_KEY to a disabled value BEFORE any CAMEL imports to prevent GoogleMapsToolkit from initializing
if not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") in ["", "noop", "DISABLED"]:
    os.environ["GOOGLE_API_KEY"] = "DISABLED_GOOGLE_TOOLKIT_NOT_USED"
    logger.info("✅ GoogleMapsToolkit disabled - GOOGLE_API_KEY set to disabled value")

# ✅ CRITICAL: Monkey patch CAMEL's Workforce._create_new_agent to completely remove GoogleMapsToolkit tools
# This is the most aggressive approach - filter tools immediately after agent creation
try:
    from camel.societies.workforce.workforce import Workforce
    _original_create_new_agent = Workforce._create_new_agent
    
    def _patched_create_new_agent(self, task, *args, **kwargs):
        """Patched _create_new_agent that completely removes GoogleMapsToolkit tools."""
        # Call original method
        agent = _original_create_new_agent(self, task, *args, **kwargs)
        
        # ✅ CRITICAL: Immediately filter out ALL GoogleMapsToolkit and irrelevant tools
        if hasattr(agent, 'tools') and agent.tools:
            irrelevant_patterns = ['weather', 'geocode', 'directions', 'place', 'maps', 'location', 'google', 'wikipedia']
            irrelevant_tool_names = [
                'get_weather_data', 'get_geocode', 'get_directions', 
                'get_place_details', 'search_nearby_places', 'search_google', 
                'google_search', 'search_wikipedia', 'search_duckduckgo'
            ]
            filtered_tools = []
            removed_count = 0
            
            for tool in agent.tools:
                tool_name = getattr(tool, 'name', '').lower()
                tool_str = str(tool).lower()
                
                # Check exact name match
                if tool_name in [n.lower() for n in irrelevant_tool_names]:
                    removed_count += 1
                    continue
                
                # Check pattern match
                if any(pattern in tool_name or pattern in tool_str for pattern in irrelevant_patterns):
                    removed_count += 1
                    continue
                
                filtered_tools.append(tool)
            
            if removed_count > 0:
                logger.info(f"✅ Removed {removed_count} GoogleMapsToolkit/irrelevant tools from new agent (had {len(agent.tools)}, now {len(filtered_tools)})")
                agent.tools = filtered_tools
        
        return agent
    
    # Apply monkey patch
    Workforce._create_new_agent = _patched_create_new_agent
    logger.info("✅ Applied monkey patch to Workforce._create_new_agent to remove GoogleMapsToolkit")
except (ImportError, AttributeError) as e:
    logger.warning(f"⚠️  Could not patch Workforce._create_new_agent: {e}")
# ✅ REMOVED: Worker wrapper classes - using pure CAMEL ChatAgents instead
# Workers are created directly as ChatAgents and added via add_single_agent_worker


class TradingWorkforceSociety:
    """
    Factory for CAMEL Workforces specialised for trading tasks.

    The workforce wires the coordinator, task, and worker chat agents with
    the shared toolkit registry, ensuring every worker has access to the
    FunctionTool set aligned to the official CAMEL tooling API.
    """

    def __init__(self) -> None:
        # ✅ CAMEL creates coordinator and task agents internally - no need to store them
        self._workforce: Optional[Workforce] = None
        self._workers: List[Any] = []
        self._filtered_tools: Optional[List] = None  # Cache filtered tools

    async def build(self) -> Workforce:
        """Initialise (or return) a fully configured workforce instance."""
        if self._workforce:
            return self._workforce

        try:
            logger.info("Building CAMEL workforce tools...")
            tools = await build_default_tools()
            logger.info(f"Built {len(tools)} tools for CAMEL workforce")
            
            # Validate tools
            if not tools:
                raise RuntimeError("No tools were built for the workforce")
            
            # ✅ CRITICAL: Filter tools immediately to prevent GoogleMapsToolkit from being used
            tools = self._filter_trading_tools(tools)
            self._filtered_tools = tools  # Cache for reuse
            
            tool_names = [getattr(tool, 'name', str(tool)) for tool in tools]
            logger.info(f"Tool names (filtered): {tool_names[:10]}{'...' if len(tool_names) > 10 else ''}")

            logger.info("Creating CAMEL Workforce instance...")
            try:
                # ✅ PURE CAMEL PATTERN: Following crrypto_pipeline_exemple.py and crypto_cycle_exemple.py
                # Create coordinator and task agents explicitly, then pass to Workforce
                from camel.agents import ChatAgent
                from camel.messages import BaseMessage
                from camel.models import ModelFactory
                from camel.types import ModelPlatformType, ModelType
                from camel.configs import ChatGPTConfig
                
                # ✅ CRITICAL: Ensure OPENAI_API_KEY is in os.environ before CAMEL tries to use it
                # CAMEL's ChatGPTConfig() reads OPENAI_API_KEY from os.environ automatically
                import os
                openai_key = os.getenv("OPENAI_API_KEY")
                if not openai_key:
                    # Try to get from settings
                    try:
                        from core.config import settings
                        openai_key = getattr(settings, 'openai_api_key', None)
                        if openai_key:
                            os.environ["OPENAI_API_KEY"] = openai_key
                            logger.info(f"✅ Set OPENAI_API_KEY from settings (length: {len(openai_key)})")
                    except Exception:
                        pass
                
                if not openai_key:
                    raise ValueError("OPENAI_API_KEY not found in environment or settings. Please set it in .env file")
                
                # Verify key is valid (not empty, not placeholder)
                if len(openai_key) < 20 or "dummy" in openai_key.lower() or "placeholder" in openai_key.lower():
                    raise ValueError(f"Invalid OPENAI_API_KEY detected (length: {len(openai_key)}). Please set a valid key in .env file")
                
                logger.info(f"✅ OPENAI_API_KEY verified (length: {len(openai_key)}, starts with: {openai_key[:8]}...)")
                
                # Get model for agents (following examples exactly)
                # Examples use ChatGPTConfig().as_dict() - CAMEL automatically reads OPENAI_API_KEY from os.environ
                try:
                    # ✅ Following crrypto_pipeline_exemple.py and crypto_cycle_exemple.py exactly
                    # ChatGPTConfig() reads OPENAI_API_KEY from os.environ automatically
                    config = ChatGPTConfig()
                    model = ModelFactory.create(
                        model_platform=ModelPlatformType.DEFAULT,
                        model_type=ModelType.DEFAULT,
                        model_config_dict=config.as_dict(),
                    )
                    logger.info(f"✅ Created model using ChatGPTConfig (API key from os.environ: OPENAI_API_KEY)")
                except Exception as model_error:
                    logger.error(f"❌ Model creation with ChatGPTConfig failed: {model_error}", exc_info=True)
                    raise ValueError(f"Failed to create CAMEL model: {model_error}. Check OPENAI_API_KEY is valid.")
                
                # ✅ Filter tools before passing to agents (prevent GoogleMapsToolkit)
                # Use cached filtered tools (already filtered above)
                filtered_tools_for_agents = self._filtered_tools or self._filter_trading_tools(tools)
                
                # Coordinator agent (following examples - crrypto_pipeline_exemple.py pattern)
                # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
                coordinator_agent = ChatAgent(
                    BaseMessage.make_assistant_message(
                        role_name="Trading System Coordinator",
                        content=(
                            "Coordinate fact, trend, sentiment, and DQN agents. "
                            "Ensure quality, structure, and consistency in trading decisions.\n\n"
                            "**TASK COORDINATION**\n"
                            "Decompose complex tasks into subtasks and assign to appropriate workers:\n"
                            "- Fact worker: price, volume, market data\n"
                            "- Sentiment worker: sentiment scores, news signals\n"
                            "- Trend worker: DQN actions, confidence, forecast trends\n"
                            "- Risk worker: volatility, correlation, portfolio risk\n"
                            "- Fusion worker: Synthesize all inputs into wallet distribution\n\n"
                            "Workers process tasks independently. Coordinate task flow to ensure all steps complete."
                        ),
                    ),
                    model=model,
                )
                # ✅ Filter tools after creation (monkey patch should have removed GoogleMapsToolkit, but double-check)
                if hasattr(coordinator_agent, 'tools') and coordinator_agent.tools:
                    original_tools = coordinator_agent.tools
                    filtered_coord_tools = self._filter_trading_tools(original_tools)
                    if len(filtered_coord_tools) < len(original_tools):
                        try:
                            coordinator_agent.tools = filtered_coord_tools
                            logger.info(f"✅ Filtered {len(original_tools) - len(filtered_coord_tools)} irrelevant tools from coordinator agent")
                        except (AttributeError, TypeError):
                            logger.warning("⚠️  Could not filter tools from coordinator agent (tools may be read-only)")
                
                # Task agent (following examples - crrypto_pipeline_exemple.py pattern)
                # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
                task_agent = ChatAgent(
                    BaseMessage.make_assistant_message(
                        role_name="Trading Task Planner",
                        content=(
                            "Plan and route trading analysis tasks.\n\n"
                            "**CRITICAL: Task Decomposition**\n"
                            "For complex portfolio tasks, ALWAYS decompose into subtasks:\n"
                            "1) Fact gathering (market data, price, volume)\n"
                            "2) Sentiment analysis (news, social media)\n"
                            "3) Trend analysis (forecasting + DQN signals)\n"
                            "4) Risk analysis (volatility, correlation)\n"
                            "5) Wallet distribution synthesis (combine all inputs)\n\n"
                            "Route each subtask to the appropriate worker. Workers process tasks independently."
                        ),
                    ),
                    model=model,
                )
                # ✅ Filter tools after creation (monkey patch should have removed GoogleMapsToolkit, but double-check)
                if hasattr(task_agent, 'tools') and task_agent.tools:
                    original_tools = task_agent.tools
                    filtered_task_tools = self._filter_trading_tools(original_tools)
                    if len(filtered_task_tools) < len(original_tools):
                        try:
                            task_agent.tools = filtered_task_tools
                            logger.info(f"✅ Filtered {len(original_tools) - len(filtered_task_tools)} irrelevant tools from task agent")
                        except (AttributeError, TypeError):
                            logger.warning("⚠️  Could not filter tools from task agent (tools may be read-only)")
                
                # Create Workforce (following examples exactly - crrypto_pipeline_exemple.py pattern)
                # ✅ Examples use direct coordinator_agent and task_agent arguments
                # Try direct arguments first (for CAMEL versions that support it), fallback to kwargs
                # ✅ Handle WorkforceMode import (may not exist or moved in different CAMEL versions)
                HAS_WORKFORCE_MODE = False
                WorkforceMode = None
                # Try several possible import locations to support multiple CAMEL releases
                try:
                    from camel.societies.workforce import WorkforceMode as _WorkforceMode
                    WorkforceMode = _WorkforceMode
                    HAS_WORKFORCE_MODE = True
                    logger.debug("✅ WorkforceMode imported from camel.societies.workforce")
                except Exception:
                    try:
                        from camel.societies.workforce.workforce import WorkforceMode as _WorkforceMode
                        WorkforceMode = _WorkforceMode
                        HAS_WORKFORCE_MODE = True
                        logger.debug("✅ WorkforceMode imported from camel.societies.workforce.workforce")
                    except Exception:
                        # Fallback: define a minimal local WorkforceMode enum matching expected values
                        class _LocalWorkforceMode(Enum):
                            AUTO_DECOMPOSE = "AUTO_DECOMPOSE"
                            PIPELINE = "PIPELINE"

                        WorkforceMode = _LocalWorkforceMode
                        HAS_WORKFORCE_MODE = True
                        logger.debug("⚠️  WorkforceMode not found in CAMEL; using local fallback enum")

                # Provide a minimal WorkforceSnapshot dataclass for compatibility with newer APIs
                try:
                    from camel.societies.workforce import WorkforceSnapshot as _WorkforceSnapshot
                except Exception:
                    @dataclass
                    class _WorkforceSnapshot:
                        main_task: Optional[Any] = None
                        pending_tasks: Optional[Deque[Any]] = None
                        completed_tasks: Optional[List[Any]] = None
                        task_dependencies: Optional[Dict[str, List[str]]] = None
                        assignees: Optional[Dict[str, str]] = None
                        current_task_index: int = 0
                        description: str = ''

                # Expose names into local vars for later use
                WorkforceSnapshot = locals().get('_WorkforceSnapshot')

                # ✅ Version-flexible workforce creation
                workforce = None
                # ✅ Preferred constructor: direct agents + share_memory=True + PIPELINE mode when available
                kwargs = {"share_memory": True}
                if HAS_WORKFORCE_MODE and WorkforceMode is not None:
                    kwargs["mode"] = WorkforceMode.PIPELINE
                workforce = Workforce(
                    "Trading System Workforce",
                    coordinator_agent=coordinator_agent,
                    task_agent=task_agent,
                    **kwargs,
                )
                logger.info("✅ Created Workforce with direct agent arguments and share_memory=True")

                # ✅ If mode attribute exists and wasn't set, set it after creation
                if HAS_WORKFORCE_MODE and WorkforceMode is not None and hasattr(workforce, "mode"):
                    try:
                        workforce.mode = WorkforceMode.PIPELINE
                        logger.info("✅ Set Workforce mode to PIPELINE")
                    except Exception:
                        logger.debug("Workforce mode attribute not settable; continuing without mode")
                
                # System messages may be read-only in newer CAMEL versions; skip setting to avoid errors
                logger.info("✅ Created Workforce instance")
                
                logger.info("✅ CAMEL Workforce instance created successfully")
                # ✅ Ensure a minimal pipeline is configured when Workforce is in PIPELINE mode
                try:
                    # Some CAMEL versions expose pipeline builder via `pipeline_add`
                    if hasattr(workforce, "pipeline_add"):
                        try:
                            # Build a tiny no-op pipeline so `process_task` works in pipeline mode
                            pipeline_builder = workforce.pipeline_add("Initialization")
                            pipeline_builder = pipeline_builder.pipeline_add("No-op")
                            pipeline_builder.pipeline_build()
                            logger.info("✅ Default minimal pipeline configured for PIPELINE mode")
                        except Exception as pb_err:
                            logger.debug(f"Could not build default pipeline: {pb_err}")
                except Exception:
                    # Non-fatal: continue if pipeline API not available
                    pass
            except Exception as e:
                logger.error(f"Failed to create Workforce instance: {type(e).__name__}: {e}", exc_info=True)
                raise RuntimeError(f"Workforce instance creation failed: {e}") from e
        except Exception as e:
            logger.error(f"Error during workforce build: {type(e).__name__}: {e}", exc_info=True)
            raise

        # ✅ System messages are now set during ChatAgent creation (see above)
        # No need to set them after workforce creation since system_message is read-only

        # ✅ Build agent-specific tool sets (minimal, focused tools per agent for token efficiency)
        # All agents get conversation logging, only Fusion gets signal logging
        conversation_logging_tools = await self._get_conversation_logging_tools()
        signal_logging_tools = await self._get_signal_logging_tools()
        
        # Fact agent tools: youtube, search, research, asknews
        fact_tools_list = await self._get_fact_agent_tools()
        fact_tools = [
            *fact_tools_list,
            *conversation_logging_tools,
        ]
        
        # Sentiment agent tools: CoinMarketCap (via market_data), search, asknews
        sentiment_tools_list = await self._get_sentiment_agent_tools()
        sentiment_tools = [
            *sentiment_tools_list,
            *conversation_logging_tools,
        ]
        
        # Trend agent tools: forecasting API (get_stock_forecast, get_action_recommendation)
        trend_tools_list = await self._get_trend_agent_tools()
        trend_tools = [
            *trend_tools_list,
            *conversation_logging_tools,
        ]
        
        # Risk agent tools: market data, forecasting (for volatility/risk metrics)
        risk_tools_list = await self._get_risk_agent_tools()
        risk_tools = [
            *risk_tools_list,
            *conversation_logging_tools,
        ]
        
        # Fusion agent tools: signal logging (wallet registration moved to API service)
        fusion_tools = [*signal_logging_tools]
        
        # Add Neo4j Memory Toolkit to Fusion agent (trader agent)
        # DISABLED: Neo4j causes segmentation faults in some environments
        if not NEO4J_DISABLED:
            try:
                from core.camel_tools.neo4j_memory_toolkit import Neo4jMemoryToolkit
                neo4j_toolkit = Neo4jMemoryToolkit()
                await neo4j_toolkit.initialize()
                fusion_tools.extend([
                    *neo4j_toolkit.get_tools(),
                ])
                logger.info("✅ Added Neo4j Memory Toolkit to Fusion agent")
            except Exception as e:
                logger.debug(f"Neo4j Memory Toolkit not available for fusion agent: {e}")
        else:
            logger.info("⚠️  Neo4j Memory Toolkit DISABLED (DISABLE_NEO4J=true or not set)")
        
        # Add Report Toolkit to Fusion agent (trader agent)
        try:
            from core.camel_tools.report_toolkit import ReportToolkit
            report_toolkit = ReportToolkit()
            fusion_tools.extend([
                *report_toolkit.get_tools(),
            ])
            logger.info("✅ Added Report Toolkit to Fusion agent")
        except Exception as e:
            logger.debug(f"Report Toolkit not available for fusion agent: {e}")
        
        # Add ROI Analyzer toolkit (get_latest_advice only) to Fusion agent
        try:
            from core.camel_tools.roi_analyzer_toolkit import ROIAnalyzerToolkit
            roi_toolkit_fusion = ROIAnalyzerToolkit()
            await roi_toolkit_fusion.initialize()
            # Only add get_latest_advice tool (read-only)
            roi_tools = roi_toolkit_fusion.get_tools()
            for tool in roi_tools:
                # Get tool name from schema
                try:
                    schema = tool.get_openai_tool_schema() if hasattr(tool, 'get_openai_tool_schema') else tool.openai_tool_schema
                    if isinstance(schema, dict):
                        tool_name = schema.get('function', {}).get('name', '')
                        if tool_name == 'get_latest_advice':
                            fusion_tools.append(tool)
                            break
                except Exception:
                    continue
            logger.info("✅ Added ROI Analyzer (get_latest_advice) to Fusion agent")
        except Exception as e:
            logger.debug(f"ROI Analyzer toolkit not available for fusion agent: {e}")
        
        # Strategy Worker tools: signal logging only (wallet registration handled by API endpoints)
        strategy_tools = [*signal_logging_tools]
        
        # Memory workers: minimal tools (no conversation logging toolkit in Polymarket-only mode)
        memory_tools = []
        
        # Pruning agent tools: Neo4j memory (delete operations) + reports
        pruning_tools = []
        # Add Neo4j Memory Toolkit (delete operations for pruning)
        # DISABLED: Neo4j causes segmentation faults in some environments
        if not NEO4J_DISABLED:
            try:
                from core.camel_tools.neo4j_memory_toolkit import Neo4jMemoryToolkit
                neo4j_pruning_toolkit = Neo4jMemoryToolkit()
                await neo4j_pruning_toolkit.initialize()
                # Only add delete/search tools for pruning
                all_tools = neo4j_pruning_toolkit.get_tools()
                delete_tools = []
                allowed_tools = ['delete_entities', 'delete_observations', 'search_memories', 'read_graph']
                for t in all_tools:
                    try:
                        # Get schema - try method first, then attribute
                        if hasattr(t, 'get_openai_tool_schema'):
                            schema = t.get_openai_tool_schema()
                        elif hasattr(t, 'openai_tool_schema'):
                            schema = t.openai_tool_schema
                        else:
                            continue
                        
                        if isinstance(schema, dict):
                            tool_name = schema.get('function', {}).get('name', '')
                            if tool_name in allowed_tools:
                                delete_tools.append(t)
                    except Exception:
                        continue
                pruning_tools.extend(delete_tools)
                logger.info(f"✅ Added Neo4j Memory Toolkit (delete operations, {len(delete_tools)} tools) to Memory Pruning agent")
            except Exception as e:
                logger.debug(f"Neo4j Memory Toolkit not available for pruning agent: {e}")
        
        # Add Report Toolkit (read reports to understand what to prune)
        try:
            from core.camel_tools.report_toolkit import ReportToolkit
            report_pruning_toolkit = ReportToolkit()
            pruning_tools.extend(report_pruning_toolkit.get_tools())
            logger.info("✅ Added Report Toolkit to Memory Pruning agent")
        except Exception as e:
            logger.debug(f"Report Toolkit not available for pruning agent: {e}")
        
        # Fact Agent - Fetches crypto news and market data daily
        # Tools: youtube, search, research, asknews, market_data, retrieval
        # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
        fact_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Fact Extractor",
                content=(
                    "Extract market facts: price, volume, market cap, volatility, on-chain metrics. "
                    "Fetch crypto news using search_market_info, YouTube transcripts, AskNews, and NewsAPI. "
                    "Use log_conversation to log important facts with clear, user-friendly explanations. "
                    "Work independently - tasks are coordinated by the coordinator agent."
                ),
            ),
            model=model,
            tools=fact_tools,
        )
        # ✅ Add memory system with Ollama embeddings to Fact agent
        try:
            fact_memory = self._create_agent_memory("Fact_Extractor", model)
            fact_agent.memory = fact_memory
            logger.info("✅ Added memory system to Fact Extractor agent")
        except Exception as e:
            logger.warning(f"⚠️  Could not add memory to Fact agent: {e}")
        
        # Trend Agent - Analyzes trends and DQN
        # Tools: forecasting API (get_stock_forecast, get_action_recommendation), math + logging
        # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
        trend_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Trend Analyzer",
                content=(
                    "Analyze trends using DQN (get_action_recommendation) and forecasting (get_stock_forecast) data. "
                    "Use log_conversation to log important findings. "
                    "Work independently - tasks are coordinated by the coordinator agent."
                ),
            ),
            model=model,
            tools=trend_tools,
        )
        # ✅ Add memory system with Ollama embeddings to Trend agent
        try:
            trend_memory = self._create_agent_memory("Trend_Analyzer", model)
            trend_agent.memory = trend_memory
            logger.info("✅ Added memory system to Trend Analyzer agent")
        except Exception as e:
            logger.warning(f"⚠️  Could not add memory to Trend agent: {e}")
        
        # Sentiment Agent - Checks sentiment
        # Tools: CoinMarketCap (via market_data), search, asknews, retrieval + logging
        # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
        sentiment_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Sentiment Analyst",
                content=(
                    "Analyze sentiment from news, social media, and CoinMarketCap-style indicators (market cap, volume, dominance). "
                    "Use Polymarket tools (get_market_details, get_order_book, search_markets, get_markets_by_tag) to access human price estimations from prediction markets. "
                    "Polymarket prices represent human sentiment and expectations - use them as a sentiment signal alongside other data sources. "
                    "Use search_market_info, AskNews, and Yahoo Finance tools to find relevant news. "
                    "Use market data tools for CoinMarketCap-like metrics. "
                    "If sentiment data is missing, fall back to neutral sentiment with fear/greed=50 and log the fallback. "
                    "Use log_conversation to log sentiment analysis with clear, user-friendly explanations. "
                    "Work independently - tasks are coordinated by the coordinator agent."
                ),
            ),
            model=model,
            tools=sentiment_tools,
        )
        # ✅ Add memory system with Ollama embeddings to Sentiment agent
        try:
            sentiment_memory = self._create_agent_memory("Sentiment_Analyst", model)
            sentiment_agent.memory = sentiment_memory
            logger.info("✅ Added memory system to Sentiment Analyst agent")
        except Exception as e:
            logger.warning(f"⚠️  Could not add memory to Sentiment agent: {e}")
        
        # Risk Analyzer - Analyzes risk
        # Tools: market data, forecasting (for volatility/risk metrics) + logging
        # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
        risk_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Risk Analyzer",
                content=(
                    "Analyze risk factors for INDIVIDUAL TICKERS (e.g., BTC, ETH, SOL): volatility, correlation, concentration, market conditions. "
                    "**CRITICAL**: Query individual ticker symbols (BTC, ETH, etc.) - NOT 'PORTFOLIO' or 'portfolio' as a ticker. "
                    "Use market data and forecasting tools (get_stock_forecast, get_action_recommendation) for individual tickers. "
                    "For portfolio-level risk, aggregate individual ticker risks. "
                    "Use log_conversation to log risk assessments. "
                    "Work independently - tasks are coordinated by the coordinator agent."
                ),
            ),
            model=model,
            tools=risk_tools,
        )
        
        # Fusion/Synthesizer Agent - Generates wallet distribution (Trader Agent)
        # Tools: signal logging + wallet distribution registration + conversation logging + Neo4j memory + reports
        # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
        fusion_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Fusion Synthesizer",
                content=(
                    "Generate wallet distribution combining trend, sentiment, and risk analysis. "
                    "Use log_trading_signal to log BUY/SELL signals when relevant. "
                    "Use register_wallet_distribution to store the final wallet distribution for each strategy. "
                    "The register_wallet_distribution tool requires: strategy (e.g., 'wallet_balancing', 'trend_follower'), "
                    "wallet_distribution (dict of ticker->allocation), reserve_pct (0.1-0.15), buy_signals (list), "
                    "sell_signals (list), ai_explanation (string).\n\n"
                    "**REVIEW ADVICE:** At the start of each cycle, use get_latest_advice to retrieve advice from the "
                    "review agent about what worked well and what needs improvement in previous cycles. "
                    "Incorporate this advice into your decision-making.\n\n"
                    "**NEO4J MEMORY:** Use Neo4j memory tools (read_graph, search_memories, create_entities, create_relations) "
                    "to store and retrieve trading knowledge, market patterns, and decision context.\n\n"
                    "**REPORTS:** Use get_all_reports to read reports from other agents (Fact Extractor, Trend Analyzer, etc.) "
                    "to understand their analysis and market insights before making wallet distribution decisions.\n\n"
                    "Work independently - tasks are coordinated by the coordinator agent."
                ),
            ),
            model=model,
            tools=fusion_tools,
        )
        
        # Memory Review Agent - Updates credit points for agent decisions
        # Tools: conversation logging + wallet review (to read wallet distributions and logs)
        # ✅ Enhanced: Note AI agent decisions in prompt header
        review_agent_tools = await self._get_review_agent_tools()
        review_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Memory Reviewer",
                content=(
                    "You are the Memory Reviewer agent. Your role is to analyze ROI from wallet distributions "
                    "and update agent weights based on performance.\n\n"
                    "**AVAILABLE AGENTS TO REVIEW:**\n"
                    "- Fact Extractor: Market facts, news, on-chain metrics\n"
                    "- Trend Analyzer: DQN signals, forecast trends\n"
                    "- Sentiment Analyst: News sentiment, social media signals\n"
                    "- Risk Analyzer: Volatility, correlation, portfolio risk\n"
                    "- Fusion Synthesizer: Final wallet distribution decisions\n\n"
                    "**YOUR TASK:**\n"
                    "1. Use analyze_wallet_roi to analyze ROI from previous wallet distributions. "
                    "If it returns 'waiting for more evaluation', log that status and skip to step 4.\n"
                    "2. If ROI data is available, use get_stock_forecast to get current prices and calculate actual ROI.\n"
                    "3. Use update_agent_weight to adjust agent weights based on performance:\n"
                    "   - Agents that contributed to good decisions → increase weight (0.7-1.0)\n"
                    "   - Agents that contributed to poor decisions → decrease weight (0.3-0.6)\n"
                    "   - Always provide a reason for weight changes\n"
                    "4. Use generate_advice to create advice for the next cycle based on your analysis.\n"
                    "5. Use log_conversation to log your review findings.\n\n"
                    "**WEIGHT UPDATE GUIDELINES:**\n"
                    "- Default weight: 0.5 (neutral)\n"
                    "- High performance: 0.7-1.0\n"
                    "- Low performance: 0.3-0.6\n"
                    "- Very poor performance: 0.1-0.3\n"
                    "- Always update weights with clear reasoning"
                ),
            ),
            model=model,
            tools=review_agent_tools,
        )
        
        # Memory Pruning Agent - Dumps irrelevant data daily
        # Tools: conversation logging + Neo4j memory (delete operations) + reports
        # ✅ Enhanced: Note AI agent decisions in prompt header
        pruning_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Memory Pruner",
                content=(
                    "You are the Memory Pruner agent. Your role is to clean up irrelevant data.\n\n"
                    "**CONTEXT FROM OTHER AGENTS:**\n"
                    "You have access to data from:\n"
                    "- Fact Extractor: News articles, market data\n"
                    "- Trend Analyzer: Forecast data, DQN signals\n"
                    "- Sentiment Analyst: Sentiment analysis results\n"
                    "- Risk Analyzer: Risk assessments\n"
                    "- Fusion Synthesizer: Wallet distribution decisions\n\n"
                    "**YOUR TASK:**\n"
                    "Prune memory daily: dump all irrelevant data and search results. "
                    "Keep recent decisions, important facts, and relevant analysis. "
                    "Remove outdated news, old search results, and stale data.\n\n"
                    "**NEO4J MEMORY:** Use Neo4j memory tools (search_memories, read_graph) to find outdated entities, "
                    "then use delete_entities and delete_observations to remove them. Focus on removing old market data, "
                    "outdated news, and stale analysis.\n\n"
                    "**REPORTS:** Use get_all_reports to read reports from other agents to understand what data is relevant "
                    "and what can be pruned. Reports older than the current cycle can be safely ignored.\n\n"
                    "Your agent memory system provides context via get_context() - use this to review stored memories without shape errors. "
                    "Update shared memory to remove pruned entries. "
                    "Use log_conversation to log pruning actions with user_explanation of what was pruned and why."
                ),
            ),
            model=model,
            tools=pruning_tools,
        )
        # ✅ Add memory system to pruning agent (provides get_context() for memory access without shape errors)
        try:
            pruning_memory = self._create_agent_memory("Memory_Pruner", model)
            pruning_agent.memory = pruning_memory
            logger.info("✅ Added memory system to Memory Pruner agent")
        except Exception as e:
            logger.warning(f"⚠️  Could not add memory to Pruning agent: {e}")
        
        # Strategy Worker - Generates wallet distributions for different strategies
        # Tools: wallet distribution + signal logging + conversation logging
        # ✅ NO SHARED MEMORY: Workers process tasks independently to avoid data overflow bias
        strategy_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Strategy Worker",
                content=(
                    "You are the Strategy Worker responsible for generating wallet distributions for different trading strategies. "
                    "For each strategy (wallet_balancing, trading, trend_follower, risk_adjusted_portfolio), generate an appropriate wallet distribution. "
                    "Use register_wallet_distribution tool to store distributions for each strategy. "
                    "Use log_trading_signal to log buy/sell signals. "
                    "Use log_conversation to log your decision-making process. "
                    "Work independently - tasks are coordinated by the coordinator agent."
                ),
            ),
            model=model,
            tools=strategy_tools,
        )
        
        # Polymarket Bet Expert - Places bets on Polymarket prediction markets
        # Tools: Polymarket toolkit (search, analyze, place bets) + signal logging
        polymarket_bet_tools = await self._get_polymarket_bet_agent_tools()
        polymarket_bet_agent = ChatAgent(
            BaseMessage.make_assistant_message(
                role_name="Polymarket Bet Expert",
                content=(
                    "You are the Polymarket Bet Expert responsible for analyzing prediction markets and making informed betting decisions.\n\n"
                    "**YOUR ROLE:**\n"
                    "Analyze Polymarket prediction markets for opportunities to place profitable bets. Use market data, "
                    "trends, and sentiment analysis from other agents to make decisions.\n\n"
                    "**DECISION WORKFLOW:**\n"
                    "1. Search and identify relevant markets using search_markets (by category, tags, keywords)\n"
                    "2. Get trending markets to spot momentum: get_trending_markets()\n"
                    "3. Analyze market details: get_market_details(market_id) for order book, volume, liquidity\n"
                    "4. Evaluate market conditions:\n"
                    "   - Order book depth and spreads indicate liquidity\n"
                    "   - Volume and trading activity show interest\n"
                    "   - Yes/No prices reveal market consensus\n"
                    "5. Compare to external analysis:\n"
                    "   - Check trend analysis from Trend Analyzer\n"
                    "   - Check sentiment analysis from Sentiment Analyst\n"
                    "   - Integrate risk assessment from Risk Analyzer\n"
                    "6. Make betting decision:\n"
                    "   - If YES is underpriced → BET YES (log_trading_signal)\n"
                    "   - If NO is underpriced → BET NO (log_trading_signal)\n"
                    "   - If mispriced and confidence > 0.65 → EXECUTE BET\n"
                    "   - If uncertain → SKIP (confidence < 0.5)\n"
                    "7. Log decision with clear reasoning\n\n"
                    "**BET CRITERIA:**\n"
                    "- Confidence threshold: 0.65 minimum\n"
                    "- Edge requirement: Expected value > 0.05 (5% edge)\n"
                    "- Risk management: Size inversely with volatility\n"
                    "- Market quality: High liquidity and volume preferred\n\n"
                    "**IMPORTANT:**\n"
                    "- Use get_orderbook to check actual bid-ask spreads\n"
                    "- Monitor order book depth for slippage risk\n"
                    "- Log all decisions with user_explanation via log_trading_signal\n"
                    "- Work independently - tasks are coordinated by the coordinator agent"
                ),
            ),
            model=model,
            tools=polymarket_bet_tools,
        )
        
        # ✅ Add workers - CAMEL handles everything
        # Trading workers
        workforce.add_single_agent_worker("Fact Extractor", fact_agent)
        workforce.add_single_agent_worker("Trend Analyzer", trend_agent)
        workforce.add_single_agent_worker("Sentiment Analyst", sentiment_agent)
        workforce.add_single_agent_worker("Risk Analyzer", risk_agent)
        workforce.add_single_agent_worker("Fusion Synthesizer", fusion_agent)
        # Strategy worker (for strategy-specific wallet distributions)
        workforce.add_single_agent_worker("Strategy Worker", strategy_agent)
        # Polymarket Bet Expert (for prediction market betting)
        workforce.add_single_agent_worker("Polymarket Bet Expert", polymarket_bet_agent)
        # Memory workers
        workforce.add_single_agent_worker("Memory Reviewer", review_agent)
        workforce.add_single_agent_worker("Memory Pruner", pruning_agent)
        
        workers_added = 9
        logger.info(f"✅ Added {workers_added} workers to workforce (5 trading + 1 strategy + 1 polymarket + 2 memory)")

        # ✅ PIPELINE CONFIGURATION REMOVED
        # Pipeline tasks are now managed by daily_process.py, hourly_process.py, minute_process.py
        # These modules use WorkforceTaskSystem to create tasks and process them individually.
        # The society only creates the workforce and workers - it does NOT configure pipelines.
        # This prevents duplicate execution and allows the scheduler service to properly manage triggers.
        logger.info("✅ Pipeline configuration delegated to daily_process.py, hourly_process.py, minute_process.py")

        # ✅ DISABLED: Workflow memory loading - we use direct task processing, not saved workflows
        # CAMEL's workflow_memory_manager tries to load workflow files for all worker roles,
        # which generates INFO messages for missing files. Since we don't use workflow files,
        # we skip this to avoid noise and unnecessary file system lookups.
        # If you need workflow persistence in the future, re-enable this block.
        # try:
        #     loaded = getattr(workforce, "load_workflow_memories", None)
        #     if callable(loaded):
        #         summary = loaded()
        #         logger.debug(
        #             "Loaded workforce workflow memories: %s",
        #             summary,
        #         )
        # except Exception as exc:
        #     logger.debug("Unable to load workflow memories: %s", exc)

        self._workforce = workforce
        logger.info(f"✅ Trading workforce ready with {workers_added} workers")
        return workforce
    
    async def _get_conversation_logging_tools(self) -> List:
        """Get conversation logging tools (available to all agents)."""
        # Conversation logging toolkit is deprecated for the Polymarket-only bot.
        # Use signal logging and API-backed audit trails instead.
        logger.info("Conversation logging toolkit disabled for Polymarket-only deployment")
        return []
    
    async def _get_signal_logging_tools(self) -> List:
        """Get signal logging tools (for Fusion agent only)."""
        try:
            from core.camel_tools.signal_logging_toolkit import SignalLoggingToolkit
            toolkit = SignalLoggingToolkit()
            await toolkit.initialize()
            # Use get_tools() which is the standard CAMEL method
            return toolkit.get_tools()
        except Exception as e:
            logger.debug(f"Signal logging tools not available: {e}")
            return []
    
    async def _get_fact_agent_tools(self) -> List:
        """Get tools for Fact agent: youtube, search, research, asknews, retrieval."""
        fact_tools = []
        
        # RetrievalToolkit for fact/news agent
        try:
            retrieval_toolkit = RetrievalToolkit()
            await retrieval_toolkit.initialize()
            fact_tools.extend(retrieval_toolkit.get_tools())
            logger.info("✅ Added RetrievalToolkit to Fact agent")
        except Exception as e:
            logger.debug(f"RetrievalToolkit not available for fact agent: {e}")
        
        # Search toolkit
        try:
            from core.camel_tools.search_toolkit import SearchToolkit
            search_toolkit = SearchToolkit()
            await search_toolkit.initialize()
            if hasattr(search_toolkit, 'get_tools'):
                fact_tools.extend(search_toolkit.get_tools())
            elif hasattr(search_toolkit, 'get_all_tools'):
                fact_tools.extend(search_toolkit.get_all_tools())
        except Exception as e:
            logger.debug(f"Search toolkit not available for fact agent: {e}")
        
        # YouTube transcript toolkit
        try:
            from core.camel_tools.youtube_transcript_toolkit import get_youtube_transcript_toolkit
            if get_youtube_transcript_toolkit:
                youtube_toolkit = get_youtube_transcript_toolkit()
                await youtube_toolkit.initialize()
                get_tools_method = getattr(youtube_toolkit, 'get_tools', None) or getattr(youtube_toolkit, 'get_all_tools', None)
                if get_tools_method:
                    fact_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"YouTube toolkit not available for fact agent: {e}")
        
        # AskNews toolkit
        try:
            from core.camel_runtime.registries import toolkit_registry
            await toolkit_registry.ensure_clients()
            if toolkit_registry._asknews_toolkit:
                get_tools_method = getattr(toolkit_registry._asknews_toolkit, 'get_tools', None) or getattr(toolkit_registry._asknews_toolkit, 'get_all_tools', None)
                if get_tools_method:
                    fact_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"AskNews toolkit not available for fact agent: {e}")
        
        # NewsAPI toolkit
        try:
            from core.camel_tools.newsapi_toolkit import NewsAPIToolkit
            from core.config import settings
            newsapi_toolkit = NewsAPIToolkit(api_key=getattr(settings, 'news_api_key', None))
            await newsapi_toolkit.initialize()
            get_tools_method = getattr(newsapi_toolkit, 'get_tools', None) or getattr(newsapi_toolkit, 'get_all_tools', None)
            if get_tools_method:
                fact_tools.extend([*get_tools_method()])
                logger.info("✅ Added NewsAPI toolkit to Fact agent")
        except Exception as e:
            logger.debug(f"NewsAPI toolkit not available for fact agent: {e}")
        
        # Native CAMEL toolkits: ThinkingToolkit and TaskPlanningToolkit (only for Fact agent)
        try:
            from camel.toolkits import ThinkingToolkit, TaskPlanningToolkit
            thinking_toolkit = ThinkingToolkit()
            task_planning_toolkit = TaskPlanningToolkit()
            fact_tools.extend(thinking_toolkit.get_tools())
            fact_tools.extend(task_planning_toolkit.get_tools())
            logger.info("✅ Added ThinkingToolkit and TaskPlanningToolkit to Fact agent")
        except Exception as e:
            logger.debug(f"ThinkingToolkit/TaskPlanningToolkit not available for fact agent: {e}")
        
        # Yahoo Finance toolkit (for financial news and quotes)
        try:
            from core.camel_tools.yahoo_finance_toolkit import YahooFinanceMCPToolkit
            yahoo_toolkit = YahooFinanceMCPToolkit()
            await yahoo_toolkit.initialize()
            get_tools_method = getattr(yahoo_toolkit, 'get_tools', None) or getattr(yahoo_toolkit, 'get_all_tools', None)
            if get_tools_method:
                fact_tools.extend([*get_tools_method()])
                logger.info("✅ Added Yahoo Finance toolkit to Fact agent")
        except Exception as e:
            logger.debug(f"Yahoo Finance toolkit not available for fact agent: {e}")
        
        # Market data (basic info)
        try:
            from core.camel_tools.market_data_toolkit import MarketDataToolkit
            market_toolkit = MarketDataToolkit()
            await market_toolkit.initialize()
            get_tools_method = getattr(market_toolkit, 'get_tools', None) or getattr(market_toolkit, 'get_all_tools', None)
            if get_tools_method:
                fact_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"Market data toolkit not available for fact agent: {e}")
        
        return fact_tools
    
    async def _get_sentiment_agent_tools(self) -> List:
        """Get tools for Sentiment agent: search, asknews, market data, Yahoo Finance, retrieval."""
        sentiment_tools = []
        
        # RetrievalToolkit for sentiment agent
        try:
            retrieval_toolkit = RetrievalToolkit()
            await retrieval_toolkit.initialize()
            sentiment_tools.extend(retrieval_toolkit.get_tools())
            logger.info("✅ Added RetrievalToolkit to Sentiment agent")
        except Exception as e:
            logger.debug(f"RetrievalToolkit not available for sentiment agent: {e}")
        
        # Search toolkit
        try:
            from core.camel_tools.search_toolkit import SearchToolkit
            search_toolkit = SearchToolkit()
            await search_toolkit.initialize()
            get_tools_method = getattr(search_toolkit, 'get_tools', None) or getattr(search_toolkit, 'get_all_tools', None)
            if get_tools_method:
                sentiment_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"Search toolkit not available for sentiment agent: {e}")
        
        # AskNews toolkit
        try:
            from core.camel_runtime.registries import toolkit_registry
            await toolkit_registry.ensure_clients()
            if toolkit_registry._asknews_toolkit:
                get_tools_method = getattr(toolkit_registry._asknews_toolkit, 'get_tools', None) or getattr(toolkit_registry._asknews_toolkit, 'get_all_tools', None)
                if get_tools_method:
                    sentiment_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"AskNews toolkit not available for sentiment agent: {e}")
        
        # Market data (for CoinMarketCap-like data)
        try:
            from core.camel_tools.market_data_toolkit import MarketDataToolkit
            market_toolkit = MarketDataToolkit()
            await market_toolkit.initialize()
            get_tools_method = getattr(market_toolkit, 'get_tools', None) or getattr(market_toolkit, 'get_all_tools', None)
            if get_tools_method:
                sentiment_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"Market data toolkit not available for sentiment agent: {e}")

        # Polymarket toolkit (human price estimations for sentiment analysis)
        try:
            from core.camel_tools.polymarket_toolkit import PolymarketToolkit
            polymarket_toolkit = PolymarketToolkit()
            await polymarket_toolkit.initialize()
            sentiment_tools.extend(polymarket_toolkit.get_tools())
            logger.info("✅ Added Polymarket Toolkit to Sentiment agent")
        except Exception as e:
            logger.debug(f"Polymarket Toolkit not available for sentiment agent: {e}")
        
        # Yahoo Finance (MCP) toolkit for news/sentiment proxy
        try:
            from core.camel_runtime.registries import toolkit_registry
            await toolkit_registry.ensure_clients()
            if getattr(toolkit_registry, "_yahoo_finance_toolkit", None):
                get_tools_method = getattr(toolkit_registry._yahoo_finance_toolkit, 'get_tools', None) or getattr(toolkit_registry._yahoo_finance_toolkit, 'get_all_tools', None)
                if get_tools_method:
                    sentiment_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"Yahoo Finance toolkit not available for sentiment agent: {e}")
        
        # Santiment API toolkit for sentiment analysis - DISABLED due to rate limits
        # try:
        #     from core.camel_tools.santiment_toolkit import SantimentToolkit
        #     santiment_toolkit = SantimentToolkit()
        #     await santiment_toolkit.initialize()
        #     get_tools_method = getattr(santiment_toolkit, 'get_tools', None) or getattr(santiment_toolkit, 'get_all_tools', None)
        #     if get_tools_method:
        #         tools_list = get_tools_method()
        #         if tools_list:  # Only add if tools are available (API key is set)
        #             sentiment_tools.extend(tools_list)
        #             logger.info("✅ Added Santiment toolkit to Sentiment agent")
        # except Exception as e:
        #     logger.debug(f"Santiment toolkit not available for sentiment agent: {e}")
        logger.debug("Santiment toolkit disabled - rate limits reached")
        
        return sentiment_tools
    
    async def _get_review_agent_tools(self) -> List:
        """Get tools for Review agent: wallet review, conversation logging, Neo4j memory (read-only), reports."""
        review_tools_list = []
        
        # Conversation logging toolkit removed for Polymarket-only deployment
        logger.debug("Conversation logging toolkit disabled; skipping for Review agent")
        
        # Wallet review toolkit (to read wallet distributions and logs)
        try:
            from core.camel_tools.wallet_review_toolkit import WalletReviewToolkit
            wallet_review_toolkit = WalletReviewToolkit()
            await wallet_review_toolkit.initialize()
            review_tools_list.extend(wallet_review_toolkit.get_tools())
            logger.info("✅ Added wallet review toolkit to Review agent")
        except Exception as e:
            logger.debug(f"Wallet review toolkit not available for review agent: {e}")
        
        # ROI Analyzer toolkit (for analyzing ROI and updating agent weights)
        try:
            from core.camel_tools.roi_analyzer_toolkit import ROIAnalyzerToolkit
            roi_toolkit = ROIAnalyzerToolkit()
            await roi_toolkit.initialize()
            review_tools_list.extend(roi_toolkit.get_tools())
            logger.info("✅ Added ROI Analyzer toolkit to Review agent")
        except Exception as e:
            logger.debug(f"ROI Analyzer toolkit not available for review agent: {e}")
        
        # Forecasting API (for getting current prices to calculate P&L)
        try:
            from core.camel_runtime.registries import toolkit_registry
            await toolkit_registry.ensure_clients()
            if toolkit_registry._api_toolkit:
                api_tools = toolkit_registry._api_toolkit.get_tools()
                # Add forecast tools for price lookup
                review_tools_list.extend(api_tools)
                logger.info("✅ Added forecasting API toolkit to Review agent (for price lookups)")
        except Exception as e:
            logger.debug(f"Forecasting API toolkit not available for review agent: {e}")
        
        # Neo4j Memory Toolkit (read-only operations for review)
        # DISABLED: Neo4j causes segmentation faults in some environments
        if not NEO4J_DISABLED:
            try:
                from core.camel_tools.neo4j_memory_toolkit import Neo4jMemoryToolkit
                neo4j_toolkit = Neo4jMemoryToolkit()
                await neo4j_toolkit.initialize()
                # Only add read/search tools (not delete operations)
                all_tools = neo4j_toolkit.get_tools()
                read_tools = []
                allowed_tools = ['read_graph', 'search_memories', 'find_memories_by_name']
                for t in all_tools:
                    try:
                        # Get schema - try method first, then attribute
                        if hasattr(t, 'get_openai_tool_schema'):
                            schema = t.get_openai_tool_schema()
                        elif hasattr(t, 'openai_tool_schema'):
                            schema = t.openai_tool_schema
                        else:
                            continue
                        
                        if isinstance(schema, dict):
                            tool_name = schema.get('function', {}).get('name', '')
                            if tool_name in allowed_tools:
                                read_tools.append(t)
                    except Exception:
                        continue
                review_tools_list.extend(read_tools)
                logger.info(f"✅ Added Neo4j Memory Toolkit (read-only, {len(read_tools)} tools) to Review agent")
            except Exception as e:
                logger.debug(f"Neo4j Memory Toolkit not available for review agent: {e}")
        else:
            logger.info("⚠️  Neo4j Memory Toolkit DISABLED for Review agent (DISABLE_NEO4J=true or not set)")
        
        # Report Toolkit (read reports, make reports)
        try:
            from core.camel_tools.report_toolkit import ReportToolkit
            report_toolkit = ReportToolkit()
            review_tools_list.extend(report_toolkit.get_tools())
            logger.info("✅ Added Report Toolkit to Review agent")
        except Exception as e:
            logger.debug(f"Report Toolkit not available for review agent: {e}")
        
        return review_tools_list
    
    async def _get_trend_agent_tools(self) -> List:
        """Get tools for Trend agent: forecasting API (get_stock_forecast, get_action_recommendation), math."""
        trend_tools = []
        
        # MathToolkit for trend agent
        try:
            math_toolkit = MathToolkit()
            await math_toolkit.initialize()
            trend_tools.extend(math_toolkit.get_tools())
            logger.info("✅ Added MathToolkit to Trend agent")
        except Exception as e:
            logger.debug(f"MathToolkit not available for trend agent: {e}")
        
        # Forecasting API toolkit (main tools)
        try:
            from core.camel_runtime.registries import toolkit_registry
            await toolkit_registry.ensure_clients()
            if toolkit_registry._api_toolkit:
                # Get all tools from API toolkit (get_stock_forecast, get_action_recommendation, get_metrics)
                # Use get_tools() which is the standard CAMEL method
                api_tools = toolkit_registry._api_toolkit.get_tools()
                # Add all tools (they are already filtered to forecasting/DQN tools)
                trend_tools.extend(api_tools)
                logger.info(f"✅ Added {len(api_tools)} forecasting tools to Trend Analyzer")
        except Exception as e:
            logger.warning(f"⚠️ Forecasting API toolkit not available for trend agent: {e}", exc_info=True)
        
        # If no tools found, try direct initialization
        if not trend_tools:
            try:
                from core.camel_tools.api_forecasting_toolkit import APIForecastingToolkit
                from core.clients.forecasting_client import ForecastingClient
                from core.config import settings
                
                client = ForecastingClient({
                    "base_url": settings.mcp_api_url,
                    "api_key": settings.mcp_api_key,
                    "mock_mode": settings.use_mock_services,
                })
                await client.connect()
                
                api_toolkit = APIForecastingToolkit(client)
                await api_toolkit.initialize()
                direct_tools = api_toolkit.get_tools()
                trend_tools.extend(direct_tools)
                logger.info(f"✅ Added {len(direct_tools)} forecasting tools to Trend Analyzer (direct init)")
            except Exception as e:
                logger.error(f"❌ Failed to initialize forecasting tools for Trend Analyzer: {e}", exc_info=True)
        
        if not trend_tools:
            logger.error("❌ Trend Analyzer has NO forecasting tools! This will cause task failures.")
        
        return trend_tools
    
    async def _get_risk_agent_tools(self) -> List:
        """Get tools for Risk agent: market data, forecasting (for volatility/risk metrics)."""
        risk_tools = []
        
        # Market data toolkit
        try:
            from core.camel_tools.market_data_toolkit import MarketDataToolkit
            market_toolkit = MarketDataToolkit()
            await market_toolkit.initialize()
            get_tools_method = getattr(market_toolkit, 'get_tools', None) or getattr(market_toolkit, 'get_all_tools', None)
            if get_tools_method:
                risk_tools.extend([*get_tools_method()])
        except Exception as e:
            logger.debug(f"Market data toolkit not available for risk agent: {e}")
        
        # Forecasting API (for volatility metrics)
        try:
            from core.camel_runtime.registries import toolkit_registry
            await toolkit_registry.ensure_clients()
            if toolkit_registry._api_toolkit:
                api_tools = toolkit_registry._api_toolkit.get_tools()
                # Get metrics and forecast tools
                filtered_api_tools = [
                    tool for tool in api_tools
                    if 'metric' in getattr(tool, 'name', '').lower() or 'forecast' in getattr(tool, 'name', '').lower()
                ]
                risk_tools.extend(filtered_api_tools)
        except Exception as e:
            logger.debug(f"Forecasting API toolkit not available for risk agent: {e}")
        
        return risk_tools
    
    async def _get_polymarket_bet_agent_tools(self) -> List:
        """Get tools for Polymarket Bet Expert agent: Polymarket toolkit for market analysis and betting."""
        polymarket_tools = []
        
        # Polymarket Toolkit - Main tools for market discovery, analysis, and betting
        try:
            from core.camel_tools.polymarket_toolkit import EnhancedPolymarketToolkit
            polymarket_toolkit = EnhancedPolymarketToolkit()
            polymarket_toolkit.initialize()
            
            # Get all Polymarket tools
            pm_tools = polymarket_toolkit.get_tools()
            if pm_tools:
                polymarket_tools.extend(pm_tools)
                tool_names = [getattr(t, 'name', str(t)) for t in pm_tools]
                logger.info(f"✅ Added {len(pm_tools)} Polymarket tools to Bet Expert: {tool_names[:5]}{'...' if len(tool_names) > 5 else ''}")
            else:
                logger.warning("⚠️ Polymarket toolkit returned no tools")
        except Exception as e:
            logger.warning(f"⚠️ Polymarket toolkit not available for Bet Expert: {e}", exc_info=True)
        
        # Signal logging (for logging BUY/SELL decisions)
        try:
            signal_logging_tools = await self._get_signal_logging_tools()
            polymarket_tools.extend(signal_logging_tools)
            logger.info("✅ Added signal logging to Polymarket Bet Expert")
        except Exception as e:
            logger.debug(f"Signal logging not available for Polymarket agent: {e}")
        
        return polymarket_tools
    
    def _create_agent_memory(self, agent_id: str, model) -> Any:
        """
        Create long-term memory system for an agent using Ollama embeddings.
        
        Args:
            agent_id: Unique identifier for the agent
            model: Model instance for token counting
            
        Returns:
            LongtermAgentMemory instance
        """
        try:
            from camel.memories import (
                LongtermAgentMemory,
                ChatHistoryBlock,
                VectorDBBlock,
                ScoreBasedContextCreator,
            )
            from camel.types import ModelType
            from camel.utils import OpenAITokenCounter
            from camel.storages import InMemoryKeyValueStorage, QdrantStorage
            from core.config import settings
            from core.memory.qdrant_storage import QdrantStorageFactory
            
            # Create Ollama embedding
            # Uses improved timeout handling (180s default, 3 retries with exponential backoff)
            # Follows CAMEL-AI BaseEmbedding interface pattern
            try:
                embedding = OllamaEmbedding()
                vector_dim = embedding.get_output_dim()
            except (ConnectionError, ConnectionRefusedError, OSError) as e:
                # Ollama service is not reachable - skip memory for this agent
                logger.debug(f"⚠️  Ollama embedding service unreachable for {agent_id}: {type(e).__name__}, skipping memory")
                return None
            
            # Ensure Qdrant collection exists
            collection_name = f"{settings.qdrant_collection_name}_{agent_id.lower()}"
            QdrantStorageFactory.ensure_collection_exists(
                collection_name=collection_name,
                vector_dim=vector_dim
            )
            
            # Create Qdrant storage
            qdrant_storage = QdrantStorageFactory.create_storage(
                collection_name=collection_name,
                vector_dim=vector_dim
            )
            
            # Create vector DB block with Ollama embedding
            vector_db_block = VectorDBBlock(
                embedding=embedding,
                storage=qdrant_storage,
            )
            
            # Create chat history block
            chat_history_block = ChatHistoryBlock(
                storage=InMemoryKeyValueStorage(),
                keep_rate=0.9
            )
            
            # Create context creator with token limit
            # Use GPT_4O_MINI for token counting (standard CAMEL model)
            context_creator = ScoreBasedContextCreator(
                token_counter=OpenAITokenCounter(ModelType.GPT_4O_MINI),
                token_limit=1024,
            )
            
            # Create long-term memory
            memory = LongtermAgentMemory(
                context_creator=context_creator,
                chat_history_block=chat_history_block,
                vector_db_block=vector_db_block,
            )
            
            logger.info(f"✅ Created memory system for agent: {agent_id} with Ollama embeddings")
            return memory
            
        except ImportError as e:
            logger.warning(f"⚠️  CAMEL memory modules not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️  Failed to create memory for agent {agent_id}: {e}")
            return None
    
    def _filter_trading_tools(self, tools: List) -> List:
        """
        Filter out irrelevant tools (weather, maps, Google tools, etc.) that are not relevant for trading.
        
        CAMEL's Workforce automatically adds GoogleMapsToolkit tools when creating new agents,
        which includes weather tools that are not relevant for trading analysis.
        """
        from camel.toolkits import FunctionTool
        
        irrelevant_tool_names = [
            'get_weather_data', 'get_geocode', 'get_directions', 
            'get_place_details', 'search_nearby_places',
            'search_duckduckgo',  # Known broken
            # Google search tools (disabled - not useful for trading)
            'search_google', 'google_search', 'search_wikipedia',
        ]
        irrelevant_patterns = [
            'weather', 'geocode', 'directions', 'place', 'maps', 'location',
            'google', 'wikipedia',  # Google toolkit patterns
        ]
        
        filtered = []
        for tool in tools:
            # Handle both FunctionTool instances and other tool types
            if not isinstance(tool, FunctionTool):
                # If it's not a FunctionTool, try to get name from schema or string representation
                tool_name = getattr(tool, 'name', str(tool)).lower()
                tool_str = str(tool).lower()
            else:
                tool_name = getattr(tool, 'name', '').lower()
                tool_str = str(tool).lower()
            
            # Check exact name match
            if tool_name in [n.lower() for n in irrelevant_tool_names]:
                logger.debug(f"Filtered out irrelevant tool: {getattr(tool, 'name', 'unknown')}")
                continue
            
            # Check pattern match
            if any(pattern in tool_name or pattern in tool_str for pattern in irrelevant_patterns):
                logger.debug(f"Filtered out tool matching irrelevant pattern: {getattr(tool, 'name', 'unknown')}")
                continue

            filtered.append(tool)
        
        if len(filtered) < len(tools):
            logger.info(f"✅ Filtered {len(tools) - len(filtered)} irrelevant tools. {len(filtered)} trading-relevant tools remaining.")
        
        return filtered
    
    def get_shared_memory_context(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest shared memory context from the workforce.
        
        This collects all shared memory from coordinator, task agent, and workers,
        making it available for pipelines (like fusion) to use as context.
        
        Returns:
            Dict with keys: coordinator, task_agent, workers, or None if unavailable
        """
        if not self._workforce:
            logger.warning("Cannot get shared memory context: workforce not initialized")
            return None
        
        try:
            # ✅ CAMEL pattern: Collect shared memory if available
            if hasattr(self._workforce, '_collect_shared_memory'):
                try:
                    shared_memory = self._workforce._collect_shared_memory()
                    
                    # ✅ Validate and filter empty messages to prevent embedding shape errors
                    if shared_memory:
                        # Filter out empty messages from each agent type
                        for key in ['coordinator', 'task_agent', 'workers']:
                            if key in shared_memory and isinstance(shared_memory[key], list):
                                # Filter out messages with empty or invalid content
                                original_count = len(shared_memory[key])
                                valid_msgs = []
                                for msg in shared_memory[key]:
                                    if not msg:
                                        continue
                                    # Check for content
                                    has_content = False
                                    if isinstance(msg, dict):
                                        content = msg.get('content', '')
                                        has_content = str(content).strip() if content else False
                                    elif hasattr(msg, 'content'):
                                        content = getattr(msg, 'content', '')
                                        has_content = str(content).strip() if content else False
                                    elif isinstance(msg, str):
                                        has_content = msg.strip()
                                    
                                    if has_content:
                                        valid_msgs.append(msg)
                                    else:
                                        # Log empty message details for debugging
                                        msg_type = type(msg).__name__
                                        logger.debug(f"Skipping empty {msg_type} message in {key}")
                                
                                shared_memory[key] = valid_msgs
                                filtered_count = len(shared_memory[key])
                                if original_count != filtered_count:
                                    logger.debug(f"Filtered {original_count - filtered_count} empty messages from {key} "
                                              f"(kept {filtered_count})")
                    
                    coordinator_msgs = len(shared_memory.get('coordinator', [])) if isinstance(shared_memory.get('coordinator'), list) else 0
                    task_agent_msgs = len(shared_memory.get('task_agent', [])) if isinstance(shared_memory.get('task_agent'), list) else 0
                    worker_msgs = len(shared_memory.get('workers', [])) if isinstance(shared_memory.get('workers'), list) else 0
                    logger.info(f"✅ Collected shared memory: {coordinator_msgs} coordinator, "
                               f"{task_agent_msgs} task_agent, {worker_msgs} worker records")
                    return shared_memory
                except ValueError as ve:
                    # Handle vector shape/dimension errors gracefully
                    error_str = str(ve).lower()
                    if "shape" in error_str or "dimension" in error_str or "broadcast" in error_str or "aligned" in error_str:
                        logger.warning(f"🔴 Vector shape error when collecting shared memory: {ve}\n"
                                     f"   This indicates embedding dimension mismatch (likely empty text input).\n"
                                     f"   Returning empty memory as fallback.")
                        return {'coordinator': [], 'task_agent': [], 'workers': []}
                    else:
                        raise
            else:
                logger.debug("Shared memory collection not available (may not be enabled)")
                return None
        except Exception as e:
            # ✅ Catch and handle embedding shape errors gracefully with detailed logging
            error_str = str(e).lower()
            if "shape" in error_str or "dimension" in error_str or "broadcast" in error_str or "aligned" in error_str or "invalid text input" in error_str:
                logger.warning(f"🔴 Shared memory collection embedding error: {e}\n"
                             f"   Error type: {type(e).__name__}\n"
                             f"   This typically means empty or whitespace-only messages were passed to embedding.\n"
                             f"   Returning empty memory as safe fallback.")
                return {'coordinator': [], 'task_agent': [], 'workers': []}
            logger.debug(f"Shared memory collection not available: {type(e).__name__}: {e}")
            return None
    
    def sync_shared_memory(self) -> bool:
        """
        Synchronize shared memory across all workforce agents.
        
        This should be called after workers have conversations to ensure
        all agents have access to shared context.
        
        Returns:
            True if synchronization succeeded, False otherwise
        """
        if not self._workforce:
            logger.debug("Cannot sync shared memory: workforce not initialized")
            return False
        
        try:
            # ✅ CAMEL pattern: Sync shared memory if available
            if hasattr(self._workforce, '_sync_shared_memory'):
                self._workforce._sync_shared_memory()
                logger.debug("✅ Shared memory synchronized across all workforce agents")
                return True
            else:
                logger.debug("Shared memory sync not available (may be handled automatically by CAMEL)")
                return False
        except Exception as e:
            logger.debug(f"Shared memory sync not available: {e}")
            return False


society_factory = TradingWorkforceSociety()

