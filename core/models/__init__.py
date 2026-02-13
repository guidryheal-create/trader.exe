"""
Model configuration modules.
"""
from core.models import base
from core.models.camel_models import CamelModelFactory
# Import from core.models (the models.py file) for backward compatibility
# Use importlib to avoid circular import issues
import importlib.util
from pathlib import Path

__all__ = [
    "CamelModelFactory",
    "AgentType",
    "AgentMessage",
    "MessageType",
    "TradeAction",
    "SignalType",
    "MarketData",
    "DQNPrediction",
    "AgentSignal",
    "TechnicalSignal",
    "RiskMetrics",
    "TradeDecision",
]