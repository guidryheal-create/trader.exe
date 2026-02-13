"""
CAMEL toolkit exposing Guidry Cloud forecasting API telemetry statistics.

Agents can call the provided FunctionTool to understand latency, success
rates, and disabled asset history for the forecasting service, allowing
them to reason about degraded conditions before attempting expensive tool
calls.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.clients.guidry_stats_client import guidry_cloud_stats

try:  # pragma: no cover - optional dependency
    from camel.toolkits import FunctionTool
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False


class GuidryStatsToolkit:
    """Expose telemetry snapshots from the guidry-cloud forecasting API."""

    async def initialize(self) -> None:
        """Provided for interface parity; nothing to initialise."""

    async def get_guidry_cloud_api_stats_async(self) -> Dict[str, Any]:
        """
        Return aggregated telemetry for guidry-cloud forecasting requests (async implementation).

        Includes success rate, latency percentiles, rate limit counts,
        and tracked disabled assets.  Call this before intensive
        forecasting operations to understand the current reliability
        of the external service.
        """
        return guidry_cloud_stats.summary()

    def get_guidry_cloud_api_stats(self) -> Dict[str, Any]:
        """
        Return aggregated telemetry for guidry-cloud forecasting requests.
        
        This is a synchronous wrapper for the async implementation.
        Uses asyncio.run() to execute async operations in a separate thread.

        Returns:
            Dictionary with telemetry statistics including:
            - success_rate: Success rate percentage
            - latency_percentiles: Latency statistics
            - rate_limit_counts: Rate limit information
            - disabled_assets: List of disabled assets
        """
        import asyncio
        return asyncio.run(self.get_guidry_cloud_api_stats_async())

    def get_stats_tool(self):
        """Get tool for retrieving Guidry Cloud API statistics."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools not installed")
        
        # Create FunctionTool with synchronous method
        tool = FunctionTool(self.get_guidry_cloud_api_stats)
        
        # Ensure schema is correct
        try:
            schema = dict(tool.get_openai_tool_schema())
            function_schema = schema.get("function", {})
            params = function_schema.get("parameters", {})
            
            # No parameters, so required should be empty
            params["required"] = []
            function_schema["parameters"] = params
            schema["function"] = function_schema
            tool.openai_tool_schema = schema
        except Exception as e:
            from core.logging import log
            log.debug(f"Could not fix schema for get_guidry_cloud_api_stats: {e}")
        
        return tool

    def get_all_tools(self):
        """Return the complete tool collection provided by this toolkit."""
        return [self.get_stats_tool()]


__all__ = ["GuidryStatsToolkit"]

