"""
Core package for the Agentic Trading System.

This module uses lazy imports to avoid circular dependencies between
config, logging, and redis_client modules.
"""

__all__ = [
    "settings",
    "log",
    "redis_client",
]

# ✅ REMOVED: Workforce wrappers - use pure CAMEL Workforce directly
# Import from core.camel_runtime.societies import TradingWorkforceSociety

