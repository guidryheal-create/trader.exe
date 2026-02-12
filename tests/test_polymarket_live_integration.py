"""Live Polymarket integration tests (guarded by env flag).

These tests run only when POLYMARKET_LIVE_TESTS=1.
They use .env credentials and perform read-only calls.
"""

import os
import pytest

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from core.clients.polymarket_client import PolymarketClient
from core.camel_tools.polymarket_toolkit import EnhancedPolymarketToolkit


def _should_run() -> bool:
    return os.getenv("POLYMARKET_LIVE_TESTS") == "1"


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def run_async(coro, timeout: float = 30.0):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _get_sample_market(client: PolymarketClient) -> dict:
    markets = []
    try:
        markets = run_async(client.search_markets(query="bitcoin", limit=5))
    except Exception:
        markets = []
    if not markets:
        pytest.skip("No markets returned from Polymarket API")
    return markets[0]


@pytest.mark.skipif(not _should_run(), reason="POLYMARKET_LIVE_TESTS is not enabled")
def test_open_positions_readonly():
    """Ensure we can fetch open positions with env-configured credentials."""
    _load_env()

    client = PolymarketClient()
    positions = client.get_open_positions()
    assert isinstance(positions, dict)


@pytest.mark.skipif(not _should_run(), reason="POLYMARKET_LIVE_TESTS is not enabled")
def test_authenticated_flag():
    """Check authenticated flag is a boolean (does not trade)."""
    _load_env()

    client = PolymarketClient()
    assert isinstance(client.is_authenticated, bool)


@pytest.mark.skipif(not _should_run(), reason="POLYMARKET_LIVE_TESTS is not enabled")
def test_public_market_search():
    """Search markets via Polymarket client (public API)."""
    _load_env()
    client = PolymarketClient()
    markets = run_async(client.search_markets(query="bitcoin", limit=5))
    assert isinstance(markets, list)


@pytest.mark.skipif(not _should_run(), reason="POLYMARKET_LIVE_TESTS is not enabled")
def test_public_market_details_and_orderbook():
    """Fetch market details and orderbook for a sample market."""
    _load_env()
    client = PolymarketClient()
    market = _get_sample_market(client)
    market_id = market.get("id") or market.get("market_id")
    assert market_id
    details = run_async(client.get_market_details(market_id=market_id))
    assert isinstance(details, dict)
    tokens = run_async(client.get_outcome_token_ids(market_id))
    if tokens:
        token_id = tokens.get("YES") or next(iter(tokens.values()))
        book = run_async(client.get_orderbook(token_id=token_id, depth=5))
        assert isinstance(book, dict)


@pytest.mark.skipif(not _should_run(), reason="POLYMARKET_LIVE_TESTS is not enabled")
def test_toolkit_search_and_trending():
    """Use EnhancedPolymarketToolkit for search and trending (read-only)."""
    _load_env()
    toolkit = EnhancedPolymarketToolkit()
    toolkit.initialize()
    search = toolkit.search_markets(query="bitcoin", limit=5)
    assert isinstance(search, dict)
    trending = toolkit.get_trending_markets(timeframe="24h", limit=5)
    assert isinstance(trending, dict)
