"""
Report Toolkit for CAMEL Agents.

Provides report storage for inter-agent communication.
Reports are stored in-memory per-cycle AND persisted to Redis for frontend display.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
import asyncio
import concurrent.futures

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
from core.clients.redis_client import RedisClient

logger = get_logger(__name__)


class ReportToolkit(BaseToolkit):
    r"""A toolkit for creating and retrieving reports for inter-agent communication.
    
    Reports are messages that agents want to give to the trader agent.
    Each toolkit instance maintains its own in-memory report storage (per-cycle).
    Reports are ALSO persisted to Redis for frontend display (converted to conversation format).
    """

    def __init__(self, redis_client_override=None, timeout: Optional[float] = None):
        r"""Initializes the ReportToolkit with in-memory and Redis storage.
        
        Args:
            redis_client_override: Optional RedisClient instance for testing
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        # Per-cycle in-memory storage
        self._reports: List[Dict[str, Any]] = []
        self._cycle_id: str = str(uuid.uuid4())
        # Redis client for persistence
        if redis_client_override:
            self.redis = redis_client_override
        else:
            self.redis = RedisClient()

    def make_report(
        self,
        title: str,
        description: str,
        main_focused_tickers: List[str],
        market_feeling: str,
        explanations: str,
        agent_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create and store a report for inter-agent communication.
        
        Reports follow a minimal template designed for the trader agent to read
        and make decisions. Each report includes essential information about
        the process, focused tickers, and market sentiment.
        Reports are stored in-memory AND persisted to Redis for frontend display.
        
        Args:
            title: Report title (brief summary)
            description: Description of the process that generated this report
            main_focused_tickers: List of main ticker symbols this report focuses on
            market_feeling: Market sentiment/feeling (e.g., "bullish", "bearish", "neutral")
            explanations: Detailed explanations supporting the market feeling
            agent_name: Optional name of the agent creating the report (auto-detected if not provided)
        
        Returns:
            Dictionary with success status and report details
        """
        try:
            timestamp = datetime.now(timezone.utc)
            safe_agent = agent_name or "unknown_agent"
            
            # Generate report ID
            report_id = f"report:{safe_agent}:{int(timestamp.timestamp())}:{uuid.uuid4().hex[:8]}"
            
            # Determine tags based on market feeling and content
            tags = ["report", "market_analysis"]
            if market_feeling.lower() in ["bullish", "bearish"]:
                tags.append(market_feeling.lower())
            if main_focused_tickers:
                tags.extend([f"ticker:{ticker}" for ticker in main_focused_tickers[:3]])  # Limit to 3 tickers
            
            report = {
                "report_id": report_id,
                "title": title,
                "description": description,
                "main_focused_tickers": main_focused_tickers,
                "market_feeling": market_feeling,
                "explanations": explanations,
                "agent_name": safe_agent,
                "timestamp": timestamp.isoformat(),
                "cycle_id": self._cycle_id,
                "tags": tags
            }
            
            # Store in-memory
            self._reports.append(report)
            
            # Persist to Redis (async, non-blocking)
            self._persist_report_to_redis(report, timestamp, safe_agent, report_id)
            
            logger.info(f"Report created: {title} by {safe_agent} (ID: {report_id})")
            
            return {
                "success": True,
                "report": report,
                "total_reports": len(self._reports)
            }
        except Exception as e:
            logger.error(f"Error creating report: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _persist_report_to_redis(
        self,
        report: Dict[str, Any],
        timestamp: datetime,
        agent_name: str,
        report_id: str
    ) -> None:
        """Persist report to Redis as conversation format for frontend display."""
        async def _async_persist():
            try:
                await self.redis.connect()
                
                # Convert report to conversation format
                # Combine description and explanations for user_explanation
                user_explanation = f"{report.get('description', '')}\n\n{report.get('explanations', '')}".strip()
                
                # Create conversation data (similar to conversation_logging_toolkit)
                conversation_data = {
                    "agent_name": agent_name,
                    "user_explanation": user_explanation,
                    "message": f"Market Feeling: {report.get('market_feeling', 'unknown')}\n\nFocused Tickers: {', '.join(report.get('main_focused_tickers', []))}",
                    "timestamp": timestamp.isoformat(),
                    "conversation_id": report_id,
                    "agentic": True,
                    "source": "report_toolkit",
                    "title": report.get("title", "Agent Report"),
                    "citations": [],
                    "tools_used": ["make_report"],
                    "agents_involved": [agent_name],
                    "decision_metadata": {
                        "report_id": report_id,
                        "market_feeling": report.get("market_feeling"),
                        "main_focused_tickers": report.get("main_focused_tickers", []),
                        "cycle_id": report.get("cycle_id"),
                        "tags": report.get("tags", [])
                    },
                    "tags": report.get("tags", []),
                    "report_data": {
                        "description": report.get("description"),
                        "explanations": report.get("explanations"),
                        "market_feeling": report.get("market_feeling")
                    }
                }
                
                # Store as agentic decision (for frontend display)
                decision_key = f"agentic:decision:{report_id}"
                decision_data = {
                    "decision_id": report_id,
                    "title": report.get("title", "Agent Report"),
                    "agent_name": agent_name,
                    "user_explanation": user_explanation,
                    "message": conversation_data["message"],
                    "citations": [],
                    "tools_used": ["make_report"],
                    "agents_involved": [agent_name],
                    "decision_metadata": conversation_data["decision_metadata"],
                    "timestamp": timestamp.isoformat(),
                    "agentic": True,
                    "source": "report_toolkit",
                    "tags": report.get("tags", []),
                    "report_data": conversation_data["report_data"],
                    # Add ticker and interval for filtering
                    "ticker": report.get("main_focused_tickers", [""])[0] if report.get("main_focused_tickers") else None,
                    "interval": "days"  # Default interval for reports
                }
                
                await self.redis.set_json(decision_key, decision_data, expire=86400 * 7)
                log.debug(f"Report persisted to Redis: {decision_key}")
                
            except Exception as e:
                log.warning(f"Failed to persist report to Redis: {e}", exc_info=True)
        
        # Run async persist in background (non-blocking)
        def _run_async():
            """Run async persist in a new event loop."""
            try:
                asyncio.run(_async_persist())
            except Exception as e:
                log.warning(f"Failed to run async persist: {e}", exc_info=True)
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, use executor to run in separate thread
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(_run_async)
                    # Don't wait for completion
            else:
                asyncio.run(_async_persist())
        except RuntimeError:
            # No event loop, create one in thread
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(_run_async)

    def get_all_reports(self) -> Dict[str, Any]:
        """Retrieve all reports from the current cycle.
        
        Returns:
            Dictionary with success status and list of all reports
        """
        try:
            return {
                "success": True,
                "reports": self._reports.copy(),  # Return copy to prevent external modification
                "count": len(self._reports),
                "cycle_id": self._cycle_id
            }
        except Exception as e:
            logger.error(f"Error retrieving reports: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_tools(self) -> List[FunctionTool]:
        """Returns a list of FunctionTool objects for report operations."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            logger.warning("CAMEL tools not available, returning empty list")
            return []
        
        toolkit_instance = self
        
        # Make report tool
        # Note: agent_name is removed from signature to avoid OpenAI strict mode issues
        # It will default to None in the actual method call
        def make_report(
            title: str,
            description: str,
            main_focused_tickers: str,
            market_feeling: str,
            explanations: str
        ) -> Dict[str, Any]:
            """Create and store a report for inter-agent communication.
            
            Reports are messages that agents want to give to the trader agent.
            They follow a minimal template with essential information for decision making.
            
            Args:
                title: Report title (brief summary, e.g., "Market Analysis for BTC/ETH")
                description: Description of the process that generated this report
                            (e.g., "Analyzed sentiment and trend data for major cryptocurrencies")
                main_focused_tickers: Comma-separated list of ticker symbols (e.g., "BTC,ETH,SOL" or "BTC, ETH, SOL")
                market_feeling: Market sentiment/feeling - one of: "bullish", "bearish", "neutral", "uncertain"
                explanations: Detailed explanations supporting the market feeling
                            (e.g., "Strong buy signals detected for BTC with 85% confidence...")
            
            Returns:
                Dictionary with success status and report details
            """
            # Parse comma-separated tickers string into list
            ticker_list = [t.strip().upper() for t in main_focused_tickers.split(",") if t.strip()] if main_focused_tickers else []
            
            return toolkit_instance.make_report(
                title=title,
                description=description,
                main_focused_tickers=ticker_list,
                market_feeling=market_feeling,
                explanations=explanations,
                agent_name=None  # Always None since it's not in the schema
            )
        
        make_report.__name__ = "make_report"
        from core.camel_tools.async_wrapper import create_function_tool
        
        # Provide explicit schema following OpenAI format - use strings only (no objects/arrays)
        # AI will construct objects from strings, which is clearer
        # Note: agent_name is optional with default "", so it's not included in the schema
        # (OpenAI strict mode requires all properties to be in required array)
        explicit_schema = {
            "type": "function",
            "function": {
                "name": "make_report",
                "description": "Create and store a report for inter-agent communication. Reports are messages that agents want to give to the trader agent. They follow a minimal template with essential information for decision making. Optional agent_name parameter can be provided but is not required.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Report title (brief summary, e.g., 'Market Analysis for BTC/ETH')"
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of the process that generated this report (e.g., 'Analyzed sentiment and trend data for major cryptocurrencies')"
                        },
                        "main_focused_tickers": {
                            "type": "string",
                            "description": "Comma-separated list of main ticker symbols this report focuses on (e.g., 'BTC,ETH,SOL' or 'BTC, ETH, SOL'). The system will parse this into a list automatically."
                        },
                        "market_feeling": {
                            "type": "string",
                            "enum": ["bullish", "bearish", "neutral", "uncertain"],
                            "description": "Market sentiment/feeling - one of: 'bullish', 'bearish', 'neutral', or 'uncertain'"
                        },
                        "explanations": {
                            "type": "string",
                            "description": "Detailed explanations supporting the market feeling (e.g., 'Strong buy signals detected for BTC with 85% confidence based on DQN analysis and trend forecasting')"
                        }
                    },
                    "required": ["title", "description", "main_focused_tickers", "market_feeling", "explanations"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        make_report_tool = create_function_tool(make_report, explicit_schema=explicit_schema)
        # Schema is already set via explicit_schema parameter in create_function_tool
        
        # Get all reports tool
        def get_all_reports() -> Dict[str, Any]:
            """Retrieve all reports from the current cycle.
            
            Returns all reports created during this execution cycle.
            Reports are cleared when the toolkit instance is destroyed (end of cycle).
            
            Returns:
                Dictionary with success status and list of all reports
            """
            return toolkit_instance.get_all_reports()
        
        get_all_reports.__name__ = "get_all_reports"
        get_all_reports_tool = create_function_tool(get_all_reports)
        
        # Override schema for get_all_reports - following OpenAI format
        schema_get = {
            "type": "function",
            "function": {
                "name": "get_all_reports",
                "description": "Retrieve all reports from the current cycle. Returns all reports created during this execution cycle. Reports are cleared when the toolkit instance is destroyed (end of cycle).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        get_all_reports_tool.openai_tool_schema = schema_get
        if hasattr(get_all_reports_tool, '_openai_tool_schema'):
            get_all_reports_tool._openai_tool_schema = schema_get
        if hasattr(get_all_reports_tool, '_schema'):
            get_all_reports_tool._schema = schema_get
        
        return [
            make_report_tool,
            get_all_reports_tool,
        ]

