"""Simple in-memory logging for Polymarket API."""
from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, timezone


class LoggingService:
    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []

    def log_event(self, level: str, message: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "message": message,
            "context": context or {},
        }
        self._events.append(event)
        return event

    def list_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(reversed(self._events))[:limit]

    def clear(self) -> None:
        self._events.clear()


logging_service = LoggingService()
