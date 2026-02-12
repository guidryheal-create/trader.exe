from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.clients.uviswap.client import UviSwapClient


class _DummyRPC:
    def __init__(self, _url: str):
        self.chain_id = 1

        class _Eth:
            chain_id = 1

            @staticmethod
            def contract(*args, **kwargs):
                return SimpleNamespace(address=kwargs.get("address"))

        self.w3 = SimpleNamespace(eth=_Eth())

    def nonce(self, _address: str) -> int:
        return 1


class _DummyRouter:
    def __init__(self, contract):
        self.contract = contract


class _DummyPermit2:
    def __init__(self, w3, addr):
        self.w3 = w3
        self.addr = addr

    def needs_erc20_approval(self, owner: str, token: str, min_allowance: int | None = None) -> bool:
        return False


class _DummyGas:
    def __init__(self, w3):
        self.w3 = w3


class _DummyPool:
    def __init__(self, w3, pool_manager_address=None, subgraph_url=None, redis_client=None, timeout_seconds=15.0):
        self.w3 = w3
        self.pool_manager_address = pool_manager_address
        self.subgraph_url = subgraph_url
        self.redis_client = redis_client

    def discover_and_index_pools(self, symbols, limit=100):
        return {
            "pool_count": 1,
            "pools": [
                {
                    "id": "0xpool",
                    "token0": {"symbol": symbols[0], "id": "0xaaa"},
                    "token1": {"symbol": symbols[1], "id": "0xbbb"},
                }
            ],
            "formatted": "Pool Address: 0xpool",
        }

    def resolve_best_pool(self, token_in_symbol: str, token_out_symbol: str):
        return SimpleNamespace(
            model_dump=lambda: {
                "pair": f"{token_in_symbol}/{token_out_symbol}",
                "pool_address": "0xpool",
                "token0_symbol": token_in_symbol,
                "token1_symbol": token_out_symbol,
            }
        )


@pytest.fixture
def patched_client_deps(monkeypatch):
    monkeypatch.setattr("core.clients.uviswap.client.RPC", _DummyRPC)
    monkeypatch.setattr("core.clients.uviswap.client.Router", _DummyRouter)
    monkeypatch.setattr("core.clients.uviswap.client.Permit2Client", _DummyPermit2)
    monkeypatch.setattr("core.clients.uviswap.client.GasManager", _DummyGas)
    monkeypatch.setattr("core.clients.uviswap.client.PoolSpy", _DummyPool)
    monkeypatch.setattr("core.clients.uviswap.client.UviSwapClient._init_redis", lambda self: None)


def test_client_discovers_and_resolves_trade_pool(patched_client_deps):
    private_key = "0x59c6995e998f97a5a004497e5f6f3f0f4f8eb59eac220d8d9f87f84d888fff44"
    client = UviSwapClient(private_key=private_key, rpc_url="http://dummy")

    discovered = client.discover_trade_pools(symbols=["ETH", "USDC"], limit=10)
    assert discovered["pool_count"] == 1

    resolved = client.resolve_trade_pool("ETH", "USDC")
    assert resolved["success"] is True
    assert resolved["pool"]["pool_address"] == "0xpool"


def test_client_trade_pool_context_uses_market_context(patched_client_deps, monkeypatch):
    private_key = "0x59c6995e998f97a5a004497e5f6f3f0f4f8eb59eac220d8d9f87f84d888fff44"
    client = UviSwapClient(private_key=private_key, rpc_url="http://dummy")

    monkeypatch.setattr(client, "get_market_context", lambda token_symbol: {"symbol": token_symbol, "context": "ok"})
    context = client.get_trade_pool_context("ETH", "USDC")

    assert context["success"] is True
    assert context["token_in_context"]["symbol"] == "ETH"
    assert context["token_out_context"]["symbol"] == "USDC"
