"""Simple in-memory chat service for CAMEL chat endpoints."""
from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, timezone


class ChatService:
    def __init__(self) -> None:
        self._history: List[Dict[str, Any]] = []

    def add_message(self, role: str, content: str) -> Dict[str, Any]:
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(msg)
        return msg

    def list_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self._history))[:limit]

    def clear(self) -> None:
        self._history.clear()


chat_service = ChatService()
