"""
Compatibility wrapper for the canonical Yahoo Finance client.

The implementation is maintained at `core.clients.yahoo_finance_client`.
This module re-exports to preserve backward compatibility.
"""

from core.clients.yahoo_finance_client import *  # noqa: F401,F403
from core.clients.yahoo_finance_client import YahooFinanceMCPClient, YahooFinanceMCPError

__all__ = ["YahooFinanceMCPClient", "YahooFinanceMCPError"]
