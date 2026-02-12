"""
Compatibility wrapper for the canonical Santiment client.

The real implementation is at `core.clients.santiment_client`.
This module re-exports it for backward compatibility.
"""

from core.clients.santiment_client import *  # noqa: F401,F403
from core.clients.santiment_client import SantimentAPIClient, SantimentAPIError

__all__ = ["SantimentAPIClient", "SantimentAPIError"]
