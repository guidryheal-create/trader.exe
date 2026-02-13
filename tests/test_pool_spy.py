from __future__ import annotations

from core.clients.uviswap.pool_spy import PoolSpy
from core.models.uviswap import PoolModel


class _FakeRedis:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)


def test_pool_spy_persists_and_resolves_from_redis():
    fake_redis = _FakeRedis()
    pool_spy = PoolSpy(w3=object(), subgraph_url="http://unused", redis_client=fake_redis)

    pools = [
        PoolModel.model_validate(
            {
                "id": "0xpool",
                "createdAtTimestamp": 1700000000,
                "createdAtBlockNumber": 123,
                "txCount": 5,
                "volumeUSD": 1000.0,
                "totalValueLockedUSD": 2000.0,
                "token0": {"id": "0xaaa", "symbol": "ETH"},
                "token1": {"id": "0xbbb", "symbol": "USDC"},
            }
        )
    ]

    pool_spy.build_pool_index(pools)

    # Clear in-memory to ensure Redis fallback path is used
    pool_spy._pool_index = {}
    resolved = pool_spy.resolve_best_pool("ETH", "USDC")

    assert resolved is not None
    assert resolved.pool_address == "0xpool"
    assert any(k.startswith("uviswap:pools:pair:") for k in fake_redis.data)
