from __future__ import annotations

import json

from core.camel_tools.wallet_analysis_toolkit import WalletAnalysisToolkit


class _FakeRedis:
    def __init__(self):
        self._hashes: dict[str, dict[str, str]] = {}
        self._lists: dict[str, list[str]] = {}

    def hset(self, key: str, field: str, value: str):
        self._hashes.setdefault(key, {})[field] = value
        return 1

    def hgetall(self, key: str):
        return dict(self._hashes.get(key, {}))

    def lrange(self, key: str, start: int, end: int):
        values = self._lists.get(key, [])
        if end < 0:
            return values[start:]
        return values[start : end + 1]


def test_get_global_wallet_state_returns_roi_and_per_token_breakdown():
    redis_client = _FakeRedis()
    toolkit = WalletAnalysisToolkit(redis_client=redis_client)

    redis_client.hset(
        "watchlist:positions",
        "p1",
        json.dumps(
            {
                "position_id": "p1",
                "token_symbol": "ETH",
                "quantity": 2.0,
                "entry_price": 100.0,
                "wallet_address": "0xwallet",
                "status": "open",
            }
        ),
    )
    redis_client.hset("watchlist:prices", "ETH", "120.0")

    state = toolkit.get_global_wallet_state(wallet_address="0xwallet")
    assert state["success"] is True
    assert state["global_invested"] == 200.0
    assert state["global_current_value"] == 240.0
    assert state["global_pnl"] == 40.0
    assert round(state["global_roi"], 6) == 0.2
    assert "ETH" in state["per_token_investment"]
    assert state["per_token_investment"]["ETH"]["invested"] == 200.0
