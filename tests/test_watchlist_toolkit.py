from __future__ import annotations

from core.camel_tools.watchlist_toolkit import WatchlistToolkit


class _FakeRedis:
    def __init__(self):
        self._hashes: dict[str, dict[str, str]] = {}
        self._lists: dict[str, list[str]] = {}
        self._kv: dict[str, str] = {}

    def hset(self, key: str, field: str, value: str):
        self._hashes.setdefault(key, {})[field] = value
        return 1

    def hget(self, key: str, field: str):
        return self._hashes.get(key, {}).get(field)

    def hgetall(self, key: str):
        return dict(self._hashes.get(key, {}))

    def lpush(self, key: str, value: str):
        self._lists.setdefault(key, []).insert(0, value)
        return len(self._lists[key])

    def ltrim(self, key: str, start: int, end: int):
        values = self._lists.get(key, [])
        if end < 0:
            self._lists[key] = values[start:]
        else:
            self._lists[key] = values[start : end + 1]

    def set(self, key: str, value: str):
        self._kv[key] = value
        return True

    def get(self, key: str):
        return self._kv.get(key)


def test_watchlist_global_roi_trigger_emits_notification():
    redis_client = _FakeRedis()
    toolkit = WatchlistToolkit(redis_client=redis_client)

    toolkit.add_position(
        token_symbol="ETH",
        token_address="0xeth",
        quantity=1.0,
        entry_price=100.0,
        wallet_address="0xwallet",
    )
    toolkit.update_price("ETH", 100.0)

    first = toolkit.evaluate_global_roi_trigger(threshold_pct=0.05, fast_threshold_pct=0.1, enabled=True)
    assert first["success"] is True
    assert first["triggered"] is False

    toolkit.update_price("ETH", 115.0)
    second = toolkit.evaluate_global_roi_trigger(threshold_pct=0.05, fast_threshold_pct=0.1, enabled=True)
    assert second["triggered"] is True
    assert second["notification"] is not None
    assert second["notification"]["trigger_type"] == "global_roi"
    assert second["notification"]["mode"] == "fast_decision"
