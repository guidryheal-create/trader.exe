"""
Simplified utilities for CAMEL runtime configuration and management.

Provides helper functions for:
- Tool validation and registration
- Client initialization
- Toolkit factory methods
- Logging and error handling
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Callable, Awaitable

from core.logging import log

AsyncFn = Callable[..., Awaitable[Any]]


class ToolValidation:
    """Utilities for validating CAMEL tools and schemas."""
    
    # Tools that are known to be irrelevant or broken for trading
    IRRELEVANT_TOOL_NAMES = {
        'search_duckduckgo',       # Known broken
        'get_weather_data',        # Weather - not relevant
        'get_geocode',             # Geocoding - not relevant
        'get_directions',          # Directions - not relevant
        'get_place_details',       # Place details - not relevant
        'search_nearby_places',    # Nearby places - not relevant
        'query_wolfram_alpha',     # Wolfram Alpha - not relevant
    }
    
    # Patterns for filtering out irrelevant tools
    IRRELEVANT_PATTERNS = {
        'weather', 'geocode', 'directions', 'place', 'maps', 
        'location', 'google', 'wikipedia', 'wolfram'
    }
    
    @staticmethod
    def is_function_tool(tool: Any) -> bool:
        """Check if tool is a valid CAMEL FunctionTool."""
        try:
            from camel.toolkits import FunctionTool
            return isinstance(tool, FunctionTool)
        except Exception:
            return False
    
    @staticmethod
    def has_valid_schema(tool: Any) -> bool:
        """Check if tool has a valid openai schema."""
        try:
            schema = tool.get_openai_tool_schema()
            return schema is not None and 'function' in schema
        except Exception:
            return False
    
    @staticmethod
    def is_irrelevant(tool: Any) -> bool:
        """Check if tool is irrelevant for trading."""
        tool_name = getattr(tool, 'name', '').lower()
        tool_str = str(tool).lower()
        
        # Check exact name match
        if tool_name in ToolValidation.IRRELEVANT_TOOL_NAMES:
            return True
        
        # Check pattern match
        return any(
            pattern in tool_name or pattern in tool_str 
            for pattern in ToolValidation.IRRELEVANT_PATTERNS
        )
    
    @staticmethod
    def validate_and_filter_tools(
        tools: List[Any],
        require_function_tool: bool = True
    ) -> tuple[List[Any], int]:
        """
        Validate and filter tools for CAMEL workforce use.
        
        Returns:
            Tuple of (filtered_tools, removed_count)
        """
        if not tools:
            return [], 0
        
        valid_tools = []
        removed_count = 0
        
        for tool in tools:
            # Must be FunctionTool if required
            if require_function_tool and not ToolValidation.is_function_tool(tool):
                log.debug(f"Skipping non-FunctionTool: {type(tool).__name__}")
                removed_count += 1
                continue
            
            # Must have valid schema
            if not ToolValidation.has_valid_schema(tool):
                tool_name = getattr(tool, 'name', 'unknown')
                log.debug(f"Skipping tool with invalid schema: {tool_name}")
                removed_count += 1
                continue
            
            # Skip irrelevant tools
            if ToolValidation.is_irrelevant(tool):
                tool_name = getattr(tool, 'name', 'unknown')
                log.debug(f"Skipping irrelevant tool: {tool_name}")
                removed_count += 1
                continue
            
            valid_tools.append(tool)
        
        return valid_tools, removed_count


class ClientInitialization:
    """Utilities for safely initializing service clients."""
    
    @staticmethod
    def is_forecasting_enabled(default_mode: str = "api") -> bool:
        """
        Check if forecasting should be enabled.
        
        Returns False if FORECASTING_MODE is "disabled" or "mock".
        """
        from core.settings.config import settings
        mode = getattr(settings, "forecasting_mode", default_mode)
        return mode not in ("disabled", "mock")
    
    @staticmethod
    def is_dex_enabled() -> bool:
        """Check if DEX simulator should be enabled."""
        return os.getenv("ENABLE_DEX_TOOLS", "false").lower() in ("1", "true", "yes", "on")
    
    @staticmethod
    def get_api_key(key_name: str, default: Optional[str] = None) -> Optional[str]:
        """Safely retrieve API key from settings or environment."""
        try:
            from core.settings.config import settings
            value = getattr(settings, key_name, default)
            if value:
                return value
        except Exception:
            pass
        return os.getenv(key_name.upper(), default)


class LoggingMarkers:
    """Standardized logging markers for CAMEL runtime operations."""
    
    TOOLKIT_REGISTRY = "[TOOLKIT REGISTRY]"
    POLYMARKET = "[POLYMARKET]"
    FORECASTING = "[FORECASTING]"
    DEX = "[DEX]"
    WORKFORCE = "[WORKFORCE]"
    RUNTIME = "[RUNTIME]"
    
    @staticmethod
    def info(marker: str, message: str, *args) -> None:
        """Log info with marker."""
        log.info(f"{marker} {message}", *args)
    
    @staticmethod
    def debug(marker: str, message: str, *args) -> None:
        """Log debug with marker."""
        log.debug(f"{marker} {message}", *args)
    
    @staticmethod
    def warning(marker: str, message: str, *args) -> None:
        """Log warning with marker."""
        log.warning(f"{marker} {message}", *args)
    
    @staticmethod
    def error(marker: str, message: str, *args) -> None:
        """Log error with marker."""
        log.error(f"{marker} {message}", *args)


class ToolkitInitialization:
    """Utilities for initializing toolkits safely."""
    
    @staticmethod
    async def init_toolkit(
        toolkit_class: type,
        name: str,
        *args,
        **kwargs
    ) -> Optional[Any]:
        """
        Safely initialize a toolkit instance.
        
        Args:
            toolkit_class: The toolkit class to instantiate
            name: Human-readable name for logging
            *args: Positional args for toolkit constructor
            **kwargs: Keyword args for toolkit constructor
        
        Returns:
            Initialized toolkit instance or None if initialization failed
        """
        try:
            toolkit = toolkit_class(*args, **kwargs)
            
            # Try async initialization if available
            if hasattr(toolkit, 'initialize') and callable(getattr(toolkit, 'initialize')):
                try:
                    await toolkit.initialize()
                except TypeError:
                    # Might be sync method, try without await
                    toolkit.initialize()
            
            LoggingMarkers.info("TOOLKIT_REGISTRY", f"Initialized {name} toolkit")
            return toolkit
        except Exception as exc:
            LoggingMarkers.debug("TOOLKIT_REGISTRY", f"Failed to initialize {name} toolkit: {exc}")
            return None
    
    @staticmethod
    def extract_tools(
        toolkit: Any,
        method_name: str = "get_tools"
    ) -> List[Any]:
        """
        Extract tools from a toolkit instance.
        
        Args:
            toolkit: The toolkit instance
            method_name: Name of the method to call (default "get_tools")
        
        Returns:
            List of tools or empty list if extraction failed
        """
        try:
            if hasattr(toolkit, method_name) and callable(getattr(toolkit, method_name)):
                method = getattr(toolkit, method_name)
                tools = method()
                return tools if isinstance(tools, list) else []
            return []
        except Exception as exc:
            LoggingMarkers.debug("TOOLKIT_REGISTRY", f"Failed to extract tools: {exc}")
            return []


__all__ = [
    "ToolValidation",
    "ClientInitialization",
    "LoggingMarkers",
    "ToolkitInitialization",
]
