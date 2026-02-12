"""
Compatibility wrapper for the canonical Forecasting client.

The canonical implementation lives under `core.clients.forecasting_client`.
This module re-exports it and provides the legacy module path for imports
that reference `core.forecasting_client`.
"""

from core.clients.forecasting_client import *  # noqa: F401,F403
from core.clients.forecasting_client import ForecastingClient, ForecastingAPIError, forecasting_client

__all__ = ["ForecastingClient", "ForecastingAPIError", "forecasting_client"]
