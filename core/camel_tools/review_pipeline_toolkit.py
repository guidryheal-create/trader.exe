"""
CAMEL toolkit exposing the weight review pipeline as a callable tool.

✅ REMOVED: review_pipeline module was deleted - using pure CAMEL workforce tasks instead.
This toolkit is now a stub to prevent import errors.
"""

from __future__ import annotations

from typing import Any, Dict

# ✅ REMOVED: review_pipeline import (module deleted - using CAMEL workforce tasks instead)
# from core.pipelines.review_pipeline import WeightReviewPipeline, REDIS_REVIEW_KEY
from core.clients.redis_client import redis_client

try:  # pragma: no cover - optional dependency
    from camel.toolkits import FunctionTool
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False


class ReviewPipelineToolkit:
    """Expose the weight review pipeline via CAMEL function tools."""

    def __init__(self, redis_client_override=None):
        self.redis = redis_client_override or redis_client

    async def initialize(self) -> None:
        """Placeholder to mirror other toolkit interfaces."""

    def get_run_review_tool(self):
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools not installed")

        async def run_weight_review(trigger: str = "camel_tool") -> Dict[str, Any]:
            """
            Execute the weight review pipeline and return the latest snapshot.

            ✅ STUB: review_pipeline module was deleted - using CAMEL workforce tasks instead.
            This tool is disabled to prevent errors.

            Args:
                trigger: Label describing the caller (defaults to 'camel_tool').

            Returns:
                Dictionary indicating the tool is disabled.
            """
            return {
                "success": False,
                "error": "Weight review pipeline removed - use CAMEL workforce tasks instead",
                "message": "This tool is disabled. Weight review should be handled via CAMEL workforce tasks.",
            }

        run_weight_review.__name__ = "run_weight_review"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(run_weight_review)

        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # trigger has a default value ("camel_tool"), so it's optional and should NOT be in required
        schema = {
            "type": "function",
            "function": {
                "name": "run_weight_review",
                "description": run_weight_review.__doc__ or "Execute the weight review pipeline and return the latest snapshot",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "trigger": {
                            "type": "string",
                            "description": "Label describing the caller or reason for review. Defaults to 'camel_tool' if not specified."
                        }
                    },
                    "required": [],  # trigger has a default, so it's optional
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

    def get_all_tools(self):
        """Return the tool collection provided by this toolkit."""
        return [self.get_run_review_tool()]


__all__ = ["ReviewPipelineToolkit"]


