import asyncio
import pytest

from api.services.polymarket.config_service import process_config_service
from api.services.polymarket.logging_service import logging_service
from api.routers.polymarket import config as config_router
from api.routers.polymarket import logs as logs_router
from api.routers.polymarket import trades as trades_router
from api.models.polymarket import (
    ConfigUpdateRequest,
    LogEvent,
    TradeProposalRequest,
    TradeExecuteRequest,
)


def test_config_get_and_update():
    data = asyncio.run(config_router.get_config())
    assert "active_flux" in data

    update_payload = {
        "process": {
            "active_flux": "polymarket_rss_flux",
            "trade_frequency_hours": 6,
            "max_ai_weighted_daily": 0.8,
            "max_ai_weighted_per_trade": 0.5,
        }
    }
    updated = asyncio.run(config_router.update_config(ConfigUpdateRequest(**update_payload)))
    assert updated["active_flux"] == "polymarket_rss_flux"
    assert updated["trade_frequency_hours"] == 6
    assert updated["max_ai_weighted_daily"] == 0.8
    assert updated["max_ai_weighted_per_trade"] == 0.5


def test_logs_post_get_delete():
    logging_service.clear()
    asyncio.run(
        logs_router.add_log(
            LogEvent(timestamp="", level="info", message="test", context={"a": 1})
        )
    )
    data = asyncio.run(logs_router.list_logs(limit=100))
    assert data["count"] >= 1
    cleared = asyncio.run(logs_router.clear_logs())
    assert cleared["cleared"] is True


def test_trade_propose_and_execute_flow(monkeypatch):
    monkeypatch.setattr(
        trades_router.data_toolkit,
        "get_market_data",
        lambda market_id: {"status": "success", "mid_price": 0.5},
    )

    # Patch trade service to avoid external calls
    async def _noop_init():
        return None

    async def _buy_market(market_id, asset, quantity, price, outcome="YES", bet_id=None):
        return {
            "trade_id": "t1",
            "market_id": market_id,
            "bet_id": bet_id or market_id,
            "asset": asset,
            "type": "BUY",
            "outcome": outcome,
            "quantity": quantity,
            "price": price,
            "total_value": quantity * price,
            "status": "filled",
            "timestamp": "2024-01-01T00:00:00Z",
        }

    monkeypatch.setattr(trades_router.trade_service, "initialize", _noop_init)
    monkeypatch.setattr(trades_router.trade_service, "buy_market", _buy_market)
    monkeypatch.setattr(trades_router.trade_service, "list_trades", lambda limit=500, status=None, asset=None: [])

    # Propose
    proposal = asyncio.run(
        trades_router.propose_trade(
            TradeProposalRequest(
                market_id="m1",
                outcome="yes",
                confidence=0.7,
                reasoning="test",
                wallet_balance=1000.0,
            )
        )
    )
    assert proposal["proposal_id"]
    assert proposal["recommended_quantity"] > 0

    # Execute via proposal
    exec_data = asyncio.run(
        trades_router.execute_trade(TradeExecuteRequest(proposal_id=proposal["proposal_id"]))
    )
    assert exec_data["status"] == "filled"


def test_trade_execute_direct(monkeypatch):
    monkeypatch.setattr(
        trades_router.data_toolkit,
        "get_market_data",
        lambda market_id: {"status": "success", "mid_price": 0.5},
    )

    async def _noop_init():
        return None

    async def _sell_market(market_id, asset, quantity, price, bet_id=None):
        return {
            "trade_id": "t2",
            "market_id": market_id,
            "bet_id": bet_id or market_id,
            "asset": asset,
            "type": "SELL",
            "outcome": "NO",
            "quantity": quantity,
            "price": price,
            "total_value": quantity * price,
            "status": "filled",
            "timestamp": "2024-01-01T00:00:00Z",
        }

    monkeypatch.setattr(trades_router.trade_service, "initialize", _noop_init)
    monkeypatch.setattr(trades_router.trade_service, "sell_market", _sell_market)
    monkeypatch.setattr(trades_router.trade_service, "list_trades", lambda limit=500, status=None, asset=None: [])

    data = asyncio.run(
        trades_router.execute_trade(
            TradeExecuteRequest(market_id="m2", outcome="no", quantity=10, price=0.4)
        )
    )
    assert data["status"] == "filled"
