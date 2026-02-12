"""
Shared utility for wrapping async functions as CAMEL FunctionTools.

This module provides a pure CAMEL-compliant way to wrap async functions
so they can be used as synchronous FunctionTool instances in CAMEL workers.
"""

import asyncio
import inspect
from typing import Any, Callable, Dict, Optional

from core.logging import log

try:
    from camel.toolkits import FunctionTool
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False


def wrap_async_tool(func: Callable) -> Callable:
    """
    Wrap an async function to work with CAMEL's synchronous FunctionTool interface.
    
    This follows pure CAMEL patterns by:
    1. Respecting CAMEL's event loop (never modifying it)
    2. Running async functions in isolated threads with their own loops
    3. Properly cleaning up resources (cancelling tasks, closing loops)
    
    Args:
        func: Async function to wrap
        
    Returns:
        Synchronous wrapper function that can be used with FunctionTool
    """
    if not inspect.iscoroutinefunction(func):
        # Not an async function, return as-is
        return func
    
    def sync_wrapper(*args, **kwargs):
        """Synchronous wrapper for async function."""
        # ✅ PURE CAMEL: Run async function in isolated thread with its own loop
        # This avoids conflicts with CAMEL's event loop while allowing async execution
        import concurrent.futures
        import threading
        
        def run_async_in_thread():
            """Run async function in a new thread with its own event loop."""
            # Create a new event loop in this thread (isolated from CAMEL's loop)
            thread_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(thread_loop)
                # Run the coroutine in this thread's loop
                return thread_loop.run_until_complete(func(*args, **kwargs))
            finally:
                # ✅ CRITICAL: Properly close the loop to avoid resource leaks
                try:
                    # Cancel any pending tasks
                    pending = asyncio.all_tasks(thread_loop)
                    for task in pending:
                        task.cancel()
                    # Wait for cancellation to complete
                    if pending:
                        thread_loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                except Exception:
                    pass
                # Close the loop
                thread_loop.close()
        
        # Check if we're in CAMEL's async context
        try:
            # CAMEL's event loop is running - use executor to avoid conflicts
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                # ✅ Increased timeout to 90s to handle long-running forecasting API requests
                return future.result(timeout=90.0)  # 90 second timeout for reliability
        except RuntimeError:
            # No running loop - can run directly (shouldn't happen in CAMEL context)
            return run_async_in_thread()
    
    # Copy function metadata
    sync_wrapper.__name__ = func.__name__
    sync_wrapper.__doc__ = func.__doc__
    sync_wrapper.__module__ = func.__module__
    sync_wrapper.__qualname__ = func.__qualname__
    # Mark as not async so CAMEL treats it as sync
    sync_wrapper._is_async = False
    
    return sync_wrapper


def create_function_tool(func: Callable, tool_name: str = None, description: str = None, explicit_schema: Optional[Dict[str, Any]] = None) -> Any:
    """
    Create a CAMEL FunctionTool from a function (async or sync).
    
    This is a convenience function that:
    1. Wraps async functions properly
    2. Creates FunctionTool instances
    3. Handles schema normalization
    
    Args:
        func: Function to wrap (can be async or sync)
        tool_name: Optional tool name override
        description: Optional tool description override
        explicit_schema: Optional explicit OpenAI tool schema to use (avoids Pydantic model generation)
        
    Returns:
        FunctionTool instance ready for CAMEL use
    """
    if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
        raise ImportError("CAMEL function tools not installed")
    
    # Store original function for schema extraction (before wrapping)
    original_func = func
    
    # Wrap async functions
    if inspect.iscoroutinefunction(func):
        func = wrap_async_tool(func)
    
    # Override name/description if provided (guard when attributes are read-only)
    if tool_name:
        for target in (func, original_func):
            try:
                target.__name__ = tool_name  # type: ignore[attr-defined]
            except Exception:
                pass
    if description:
        for target in (func, original_func):
            try:
                target.__doc__ = description
            except Exception:
                pass
    
    # Create FunctionTool
    # If explicit_schema is provided, pass it directly into the constructor so that
    # CAMEL does NOT attempt to auto-generate a Pydantic model (which can trigger
    # forward-ref errors like `CreateEntities` / `List` not fully defined).
    if explicit_schema:
        tool = FunctionTool(func, openai_tool_schema=explicit_schema)  # type: ignore[call-arg]
        # Also mirror into internal caches if present
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = explicit_schema
        if hasattr(tool, '_schema'):
            tool._schema = explicit_schema
        return tool
    else:
        tool = FunctionTool(func)
    
    # Normalize schema - extract from original function signature if schema is empty
    try:
        schema = dict(tool.get_openai_tool_schema())
        # Check if schema has empty properties (indicates extraction failed)
        function_schema = schema.get("function", {})
        params = function_schema.get("parameters", {})
        properties = params.get("properties", {})
        
        # If schema is empty or only has args/kwargs (from wrapper), extract from original function
        if not properties or (len(properties) == 2 and "args" in properties and "kwargs" in properties):
            # Extract from original function signature (before wrapping)
            sig = inspect.signature(original_func)
            extracted_props = {}
            extracted_required = []
            
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                param_type = "string"  # default
                if param.annotation != inspect.Parameter.empty:
                    ann_str = str(param.annotation)
                    if "float" in ann_str or "int" in ann_str:
                        param_type = "number"
                    elif "bool" in ann_str:
                        param_type = "boolean"
                    elif "list" in ann_str or "List" in ann_str:
                        param_type = "array"
                
                extracted_props[param_name] = {
                    "type": param_type,
                    "description": f"Parameter {param_name}",
                }
                
                if param.default == inspect.Parameter.empty:
                    extracted_required.append(param_name)
            
            if extracted_props:
                params["properties"] = extracted_props
                params["required"] = extracted_required
                function_schema["parameters"] = params
                schema["function"] = function_schema
                tool.openai_tool_schema = schema
    except Exception as e:
        log.debug(f"Schema extraction failed for {func.__name__}: {e}, using default")
        # Fallback: create minimal schema
        schema = {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": func.__doc__ or func.__name__,
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
        tool.openai_tool_schema = schema
    
    # Ensure description is set
    function_schema = schema.get("function", {})
    function_schema["name"] = func.__name__
    
    # ✅ CRITICAL: Use full docstring as description (includes parameter extraction rules)
    if func.__doc__:
        function_schema["description"] = func.__doc__.strip()
    else:
        function_schema.setdefault("description", func.__name__)
    
    tool.openai_tool_schema = schema
    
    # Ensure FunctionTool name attribute is populated for test/registry checks
    try:
        tool.name = func.__name__
    except Exception:
        pass

    return tool
