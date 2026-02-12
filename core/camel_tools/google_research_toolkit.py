"""
Toolkit wrapping CAMEL's SearchToolkit helpers (Google/Wikipedia) and exposing
them as FunctionTool instances for the trading workforce.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.logging import log

try:  # pragma: no cover - optional dependency
    from camel.toolkits import FunctionTool
    from camel.toolkits.search_toolkit import SearchToolkit
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover
    FunctionTool = None  # type: ignore
    SearchToolkit = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False


class GoogleResearchToolkit:
    """Expose search helpers (Google/Wikipedia) as FunctionTool objects."""

    def __init__(self) -> None:
        self._search_toolkit: SearchToolkit | None = None

    async def initialize(self) -> None:
        if not CAMEL_TOOLS_AVAILABLE or SearchToolkit is None:
            raise ImportError("camel.toolkits.search_toolkit.SearchToolkit is not available.")
        if self._search_toolkit is None:
            # ✅ Check for Google API key before initializing (optional - don't fail if missing)
            import os
            google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not google_api_key or google_api_key.strip() == "":
                # ✅ Make Google API key optional - don't raise error, just skip initialization
                log.debug(
                    "GOOGLE_API_KEY not found. Google Research Toolkit is optional - "
                    "system will work without it using OpenAI only."
                )
                return  # Skip initialization, toolkit will be None
            try:
                # ✅ Catch GOOGLE_API_KEY errors from CAMEL's SearchToolkit
                # SearchToolkit may raise an error if GOOGLE_API_KEY is not set
                self._search_toolkit = SearchToolkit()
                log.info("SearchToolkit initialised for GoogleResearchToolkit.")
            except (ValueError, KeyError, RuntimeError) as e:
                # CAMEL's SearchToolkit raises ValueError/KeyError when GOOGLE_API_KEY is missing
                error_msg = str(e).lower()
                if "google_api_key" in error_msg or "api key" in error_msg or "not found" in error_msg:
                    log.debug(f"GOOGLE_API_KEY not configured. Google Research Toolkit is optional - continuing without it.")
                else:
                    log.warning(f"Failed to initialize Google Research Toolkit: {e}. Continuing without it.")
                self._search_toolkit = None
            except Exception as e:
                # Catch any other initialization errors
                log.warning(f"Failed to initialize Google Research Toolkit: {e}. Continuing without it.")
                self._search_toolkit = None

    def _wrap(self, fn_name: str, tool_name: str, description: str) -> FunctionTool:
        """Wrap a SearchToolkit method as a FunctionTool."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None or SearchToolkit is None:
            raise ImportError("CAMEL toolkits are not available.")
        if self._search_toolkit is None:
            # ✅ Make Google Research Toolkit optional - return a no-op tool if not initialized
            log.debug("SearchToolkit not initialised (GOOGLE_API_KEY not set). Returning no-op tool.")
            # Return a no-op function tool that returns empty results
            def noop_search(*args, **kwargs):
                return {"results": [], "message": "Google Research Toolkit not available (GOOGLE_API_KEY not set)"}
            from core.camel_tools.async_wrapper import create_function_tool
            return create_function_tool(noop_search, tool_name, description)

        try:
            # Get the bound method from the SearchToolkit instance
            bound_method = getattr(self._search_toolkit, fn_name)
            
            # Create a wrapper function that preserves the instance binding
            def wrapped_search(query: str) -> Any:
                """Wrapper function that calls the bound method."""
                try:
                    result = bound_method(query)
                    # Check if result indicates failure
                    if isinstance(result, dict) and result.get("result"):
                        result_str = str(result.get("result", ""))
                        if "error" in result_str.lower() or "failed" in result_str.lower():
                            log.warning(f"Google search failed for query '{query}': {result_str}")
                    return result
                except Exception as exc:
                    log.warning(f"Google search error for query '{query}': {exc}")
                    # Return a structured error response that won't break the workflow
                    return {"result": f"[Google search unavailable: {str(exc)}]"}
            
            # Set the wrapper's metadata to match the original method
            wrapped_search.__name__ = tool_name
            wrapped_search.__doc__ = description
            
            # Create FunctionTool from the wrapper function (not the bound method)
            tool = FunctionTool(wrapped_search)
            
            # Set the OpenAI tool schema
            schema = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query string.",
                            }
                        },
                        "required": ["query"],
                    },
                },
            }
            tool.openai_tool_schema = schema
            
            # Verify the tool is a FunctionTool instance
            if not isinstance(tool, FunctionTool):
                raise TypeError(f"Created tool is not a FunctionTool instance: {type(tool)}")
            
            return tool
        except Exception as exc:
            log.warning("Failed to wrap search tool %s: %s", fn_name, exc)
            raise

    def get_tools(self) -> List[FunctionTool]:
        """Return the bundled search tools (Google/Wikipedia/DuckDuckGo)."""
        tools = []
        
        # Wrap Google search
        try:
            if hasattr(self._search_toolkit, "search_google"):
                tools.append(self._wrap(
                    fn_name="search_google",
                    tool_name="search_google",
                    description="Search Google and return the top results.",
                ))
        except Exception as exc:
            log.warning("Failed to wrap search_google: %s", exc)
        
        # Wrap Wikipedia search
        try:
            if hasattr(self._search_toolkit, "search_wiki"):
                tools.append(self._wrap(
                    fn_name="search_wiki",
                    tool_name="search_wikipedia",
                    description="Search Wikipedia and return summary snippets.",
                ))
        except Exception as exc:
            log.warning("Failed to wrap search_wiki: %s", exc)
        
        # Wrap DuckDuckGo search if available
        try:
            if hasattr(self._search_toolkit, "search_duckduckgo"):
                tools.append(self._wrap(
                    fn_name="search_duckduckgo",
                    tool_name="search_duckduckgo",
                    description="Search DuckDuckGo and return the top results.",
                ))
        except Exception as exc:
            log.warning("Failed to wrap search_duckduckgo: %s", exc)
        
        return tools

    def get_all_tools(self) -> List[Any]:
        return self.get_tools()


__all__ = ["GoogleResearchToolkit"]


