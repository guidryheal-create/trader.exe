"""
AskNews-powered toolkit for CAMEL agents.

Wraps the official `asknews` client and exposes simple search functions as
FunctionTools so that CAMEL workforces can fetch recent news snippets without
launching a browser.  Requires `pip install asknews`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.logging import log

try:  # pragma: no cover - optional dependency
    from camel.toolkits import FunctionTool
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False

try:  # pragma: no cover - optional dependency
    from asknews import AskNewsClient
    ASKNEWS_AVAILABLE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    # Catch both ImportError and ModuleNotFoundError (asknews might depend on asknews_sdk)
    AskNewsClient = None  # type: ignore
    ASKNEWS_AVAILABLE = False


class AskNewsToolkit:
    """Expose AskNews search helpers to CAMEL agents."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._client: Optional["AskNewsClient"] = None  # String annotation for forward reference
        self._api_key = api_key

    async def initialize(self) -> None:
        if not ASKNEWS_AVAILABLE:
            raise ImportError("asknews package is not installed. Install with `pip install asknews`.")
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL function tools are required for AskNews toolkit.")

        if not self._client:
            self._client = AskNewsClient(api_key=self._api_key)
            log.info("AskNews client initialised.")

    async def _ensure_client(self) -> "AskNewsClient":
        await self.initialize()
        if not self._client:
            raise RuntimeError("AskNews client failed to initialise.")
        return self._client

    async def search_latest(
        self,
        query: str,
        max_results: int = 5,
        language: str = "en",
    ) -> Dict[str, Any]:
        client = await self._ensure_client()
        response = await client.search_latest(query=query, max_results=max_results, language=language)
        return {"success": True, "query": query, "items": response}

    def get_search_tool(self):
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit = self

        async def asknews_search(
            query: str,
            max_results: int = 5,
            language: str = "en",
        ) -> Dict[str, Any]:
            """
            Search the AskNews API for recent headlines matching the query.

            Args:
                query: Search phrase.
                max_results: Maximum number of articles to return.
                language: Desired language (default English).
            """

            return await toolkit.search_latest(
                query=query,
                max_results=max(1, min(max_results, 20)),
                language=language,
            )

        asknews_search.__name__ = "asknews_search"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(asknews_search)

        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # query is required (no default), max_results and language are optional (have defaults)
        schema = {
            "type": "function",
            "function": {
                "name": asknews_search.__name__,
                "description": asknews_search.__doc__ or "Search news articles using AskNews",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return. Defaults to 5 if not specified.",
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code (e.g., 'en', 'es', 'fr'). Defaults to 'en' if not specified."
                        }
                    },
                    "required": ["query"],  # Only query is required, others have defaults
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
        return [self.get_search_tool()]


__all__ = ["AskNewsToolkit"]


