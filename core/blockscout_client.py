"""
Compatibility wrapper for the canonical Blockscout client.

The real implementation is at `core.clients.blockscout_client`.
This module re-exports it for backward compatibility.
"""

from core.clients.blockscout_client import *  # noqa: F401,F403
from core.clients.blockscout_client import BlockscoutMCPClient, BlockscoutMCPError

__all__ = ["BlockscoutMCPClient", "BlockscoutMCPError"]
