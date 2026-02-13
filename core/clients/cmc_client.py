"""Utility client for CoinMarketCap market sentiment indicators."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from core.settings.config import settings
from core.logging import log

# move to client 
class CMCIndicatorClient:
    """Fetches sentiment indicators from the CoinMarketCap public API."""

    _BASE_URL = "https://pro-api.coinmarketcap.com"

    def __init__(self, api_key: Optional[str]) -> None:
        self._api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        if not self._api_key:
            raise RuntimeError("CMC API key not configured")
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._BASE_URL,
                headers={
                    "X-CMC_PRO_API_KEY": self._api_key,
                    "Accept": "application/json",
                },
                timeout=20.0,
            )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_snapshot(self) -> Optional[Dict[str, Any]]:
        """Return aggregated sentiment snapshot if the API key is present.
        
        Uses CoinMarketCap API v3 endpoints:
        - /v3/fear-and-greed/historical (with limit=1 for latest)
        - /v3/altcoin-season/historical (with limit=1 for latest)
        - /v3/market-cycle/historical (with limit=1 for latest)
        - /v3/bitcoin-dominance/historical (with limit=1 for latest)
        - /v3/cmc20/historical (with limit=1 for latest)
        - /v3/cmc100/historical (with limit=1 for latest)
        """

        if not self._api_key:
            log.warning("CMC API key not configured, skipping market indicators")
            return None

        await self.connect()
        assert self._client is not None

        try:
            # ✅ Use historical endpoints with limit=1 to get latest value
            # According to CMC API docs: https://coinmarketcap.com/api/documentation/v3/#/Fear%20and%20Greed%20Index
            fear_greed = await self._get_latest_value("/v3/fear-and-greed/historical", params={"limit": 1})
            altcoin_season = await self._get_latest_value("/v3/altcoin-season/historical", params={"limit": 1})
            market_cycle = await self._get_latest_value("/v3/market-cycle/historical", params={"limit": 1})
            dominance = await self._get_latest_value("/v3/bitcoin-dominance/historical", params={"limit": 1})
            cmc20 = await self._get_latest_value("/v3/cmc20/historical", params={"limit": 1})
            cmc100 = await self._get_latest_value("/v3/cmc100/historical", params={"limit": 1})
            
            log.info(f"✅ CMC indicators fetched - Fear & Greed: {fear_greed.get('value') if fear_greed else 'N/A'}, "
                    f"Altcoin Season: {altcoin_season.get('value') if altcoin_season else 'N/A'}, "
                    f"Market Cycle: {market_cycle.get('value') if market_cycle else 'N/A'}")
        except Exception as exc:  # pragma: no cover - network
            log.warning(f"⚠️  Failed to fetch CMC indicators: {exc}", exc_info=True)
            return None

        snapshot = {
            "fear_greed_index": fear_greed,
            "altcoin_season_index": altcoin_season,
            "market_cycle_indicator": market_cycle,
            "bitcoin_dominance": dominance,
            "cmc20_index": cmc20,
            "cmc100_index": cmc100,
        }
        return snapshot

    async def _get_latest_value(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Get latest value from CMC API endpoint.
        
        Args:
            endpoint: API endpoint path (e.g., "/v3/fear-and-greed/historical")
            params: Optional query parameters (e.g., {"limit": 1})
        
        Returns:
            Latest data point from the API response, or None if unavailable
        """
        if not self._client:
            return None
        
        try:
            response = await self._client.get(endpoint, params=params or {})
            response.raise_for_status()
            payload = response.json()
            
            # CMC API v3 returns data in "data" field
            data = payload.get("data")
            
            # Handle list response (historical endpoints return arrays)
            if isinstance(data, list) and data:
                # Return the first (latest) entry
                latest = data[0]
                log.debug(f"✅ CMC {endpoint}: Retrieved latest value: {latest.get('value') if isinstance(latest, dict) else 'N/A'}")
                return latest
            
            # Handle dict response (some endpoints return single object)
            if isinstance(data, dict):
                log.debug(f"✅ CMC {endpoint}: Retrieved value: {data.get('value') if 'value' in data else 'N/A'}")
                return data
            
            log.warning(f"⚠️  CMC {endpoint}: Unexpected response format: {type(data)}")
            return None
        except httpx.HTTPStatusError as e:
            # ✅ Reduce log noise for expected 404s (some endpoints don't exist)
            if e.response.status_code == 404:
                log.debug(f"⚠️  CMC API endpoint not found (404): {endpoint} - This is expected for some endpoints")
            else:
                log.warning(f"⚠️  CMC API error for {endpoint}: HTTP {e.response.status_code} - {e.response.text[:200]}")
            return None
        except Exception as e:
            log.warning(f"⚠️  CMC API error for {endpoint}: {e}")
            return None


async def get_indicator_snapshot() -> Optional[Dict[str, Any]]:
    """Convenience wrapper used by pipelines."""

    if not settings.cmc_api_key:
        return None

    client = CMCIndicatorClient(settings.cmc_api_key)
    try:
        return await client.get_snapshot()
    finally:
        await client.close()
