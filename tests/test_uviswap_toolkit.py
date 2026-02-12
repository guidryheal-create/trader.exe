from __future__ import annotations

import pytest

from core.camel_tools.uviswap_toolkit import UviSwapToolkit
from core.camel_tools.async_wrapper import CAMEL_TOOLS_AVAILABLE


class _FakeClient:
    def quote_exact_in(self, token_in, token_out, amount_in, fee=3000):
        return int(amount_in * 2)

    def inspect_pool(self, pool_address):
        return {"pool": pool_address, "fee": 3000}

    def discover_trade_pools(self, symbols, limit=100):
        return {"pool_count": 1, "symbols": symbols, "limit": limit}

    def resolve_trade_pool(self, token_in_symbol, token_out_symbol):
        return {"success": True, "pool": {"pair": f"{token_in_symbol}/{token_out_symbol}"}}

    def get_market_context(self, token_symbol):
        return {"symbol": token_symbol, "trend": "neutral"}

    def get_trade_pool_context(self, token_in_symbol, token_out_symbol):
        return {"success": True, "pool": {"pair": f"{token_in_symbol}/{token_out_symbol}"}}

    def approve_permit2_if_needed(self, token, min_allowance=None):
        return None

    def build_swap_plan(self, request, commands, inputs, deadline_seconds=300, simulate=True):
        return type(
            "Plan",
            (),
            {
                "simulation_ok": True,
                "simulation_result": "ok",
                "expected_out": 123,
                "min_out": 100,
                "nonce": 1,
                "tx": {"to": "0xrouter"},
                "calldata": "0x1234",
            },
        )()

    def execute_plan(self, plan, require_simulation_success=True):
        return "0xtx"


class _FakeWatchlist:
    def __init__(self):
        self.positions = {}

    def add_position(self, **kwargs):
        position = {"position_id": "pos1", **kwargs, "status": "open"}
        self.positions["pos1"] = position
        return {"success": True, "position": position}

    def get_position(self, position_id: str):
        if position_id not in self.positions:
            return {"success": False, "error": "not found"}
        return {"success": True, "position": self.positions[position_id]}

    def close_position(self, position_id: str, close_reason: str):
        if position_id not in self.positions:
            return {"success": False, "error": "not found"}
        self.positions[position_id]["status"] = "closed"
        self.positions[position_id]["close_reason"] = close_reason
        return {"success": True, "position": self.positions[position_id]}


def test_uviswap_toolkit_basic_operations():
    toolkit = UviSwapToolkit(client=_FakeClient())

    q = toolkit.quote_exact_in("0xA", "0xB", 10)
    assert q["amount_out"] == 20

    pool = toolkit.resolve_trade_pool("ETH", "USDC")
    assert pool["success"] is True

    ctx = toolkit.get_trade_pool_context("ETH", "USDC")
    assert ctx["success"] is True


def test_uviswap_toolkit_plan_and_execute():
    toolkit = UviSwapToolkit(client=_FakeClient())

    plan = toolkit.build_swap_plan(
        token_in="0xA",
        token_out="0xB",
        amount_in=100,
        commands_hex="0x00",
        inputs_hex=["0x01"],
    )
    assert plan["success"] is True
    assert plan["simulation_ok"] is True

    execution = toolkit.execute_swap(
        token_in="0xA",
        token_out="0xB",
        amount_in=100,
        commands_hex="0x00",
        inputs_hex=["0x01"],
    )
    assert execution["success"] is True
    assert execution["tx_hash"] == "0xtx"


def test_uviswap_toolkit_register_and_execute_watchlist_exit():
    watchlist = _FakeWatchlist()
    toolkit = UviSwapToolkit(client=_FakeClient(), watchlist_toolkit=watchlist)

    registered = toolkit.register_stop_loss_take_profit(
        token_symbol="ETH",
        token_address="0xaaa",
        quantity=1.0,
        entry_price=2000.0,
        stop_loss_pct=-0.05,
        take_profit_pct=0.1,
        exit_plan={
            "token_in": "0xaaa",
            "token_out": "0xbbb",
            "amount_in": 100,
            "commands_hex": "0x00",
            "inputs_hex": ["0x01"],
        },
    )
    assert registered["success"] is True

    exit_res = toolkit.execute_watchlist_exit(position_id="pos1", trigger_type="stop_loss")
    assert exit_res["success"] is True
    assert exit_res["tx_hash"] == "0xtx"


@pytest.mark.skipif(not CAMEL_TOOLS_AVAILABLE, reason="CAMEL tools not installed in test env")
def test_uviswap_toolkit_explicit_schemas():
    toolkit = UviSwapToolkit(client=_FakeClient())
    tools = toolkit.get_tools()
    names = []
    for tool in tools:
        schema = tool.get_openai_tool_schema()
        names.append(schema.get("function", {}).get("name"))

    assert "discover_trade_pools" in names
    assert "get_trade_pool_context" in names
