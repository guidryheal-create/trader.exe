"""In-memory decision and proposal tracking for Polymarket API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4


class DecisionService:
    def __init__(self) -> None:
        self._proposals: Dict[str, Dict[str, Any]] = {}
        self._decisions: List[Dict[str, Any]] = []

    def create_proposal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        proposal_id = str(uuid4())
        proposal = {
            "proposal_id": proposal_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        self._proposals[proposal_id] = proposal
        return proposal

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        return self._proposals.get(proposal_id)

    def list_proposals(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._proposals.values())[-limit:]

    def record_decision(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        decision = {
            "decision_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        self._decisions.append(decision)
        return decision

    def list_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self._decisions))[:limit]

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        for d in self._decisions:
            if d.get("decision_id") == decision_id:
                return d
        return None


decision_service = DecisionService()
