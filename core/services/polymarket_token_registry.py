"""Internal registry for mapping LLM-safe identifiers to token IDs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class TokenRegistry:
    """Maintain internal mappings for Polymarket token IDs.

    LLM-visible identifiers are simple strings (bet_id, token_label).
    Token IDs remain internal and are resolved at execution time.
    """

    market_token_map: Dict[str, Dict[str, str]] = field(default_factory=dict)
    trade_map: Dict[str, Dict[str, str]] = field(default_factory=dict)
    alias_map: Dict[str, str] = field(default_factory=dict)

    def register_market(
        self,
        market_id: str,
        bet_id: str,
        yes_token_id: Optional[str],
        no_token_id: Optional[str],
    ) -> None:
        """Register token IDs for a market with a LLM-safe bet_id."""
        if not bet_id:
            bet_id = market_id
        if market_id and bet_id:
            self.alias_map[bet_id] = market_id
        entry: Dict[str, str] = {}
        if yes_token_id:
            entry["YES"] = str(yes_token_id)
        if no_token_id:
            entry["NO"] = str(no_token_id)
        if entry:
            self.market_token_map[bet_id] = entry

    def register_trade(self, trade_id: str, bet_id: str, outcome: str) -> None:
        """Register a trade to resolve later."""
        if trade_id and bet_id:
            self.trade_map[trade_id] = {
                "bet_id": bet_id,
                "outcome": outcome.upper(),
            }

    def resolve_market_id(self, bet_id: str) -> Optional[str]:
        """Resolve bet_id to canonical market_id if known."""
        return self.alias_map.get(bet_id)

    def resolve_token_id(self, bet_id: str, outcome: str) -> Optional[str]:
        """Resolve token ID for a bet_id/outcome pair."""
        outcome_key = outcome.upper()
        return self.market_token_map.get(bet_id, {}).get(outcome_key)

    def resolve_trade(self, trade_id: str) -> Optional[Dict[str, str]]:
        """Resolve trade_id to bet_id/outcome pair."""
        return self.trade_map.get(trade_id)
