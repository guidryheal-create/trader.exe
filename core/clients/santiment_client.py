"""
Santiment API Client for sentiment and social metrics.

Provides access to Santiment GraphQL API for cryptocurrency sentiment analysis,
social volume, social dominance, and trending words.
Reference: https://santiment.net/
"""
import asyncio
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from core.logging import log
from core.settings.config import settings


class SantimentAPIError(Exception):
    """Base exception for Santiment API operations."""
    pass


class SantimentAPIClient:
    """
    Client for interacting with Santiment GraphQL API.
    
    Supports querying:
    - Sentiment balance
    - Social volume
    - Social dominance
    - Trending words
    - Social volume shifts/alerts
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Santiment API client.
        
        Args:
            config: Optional configuration dict with:
                - api_key: Santiment API key (default: from SENTIMENT_API env var)
                - base_url: API base URL (default: "https://api.santiment.net/graphql")
                - timeout: Request timeout in seconds (default: 30)
                - retry_attempts: Number of retry attempts (default: 3)
        """
        config = config or {}
        self.api_key = config.get(
            "api_key",
            getattr(settings, 'sentiment_api_key', None)
        )
        if not self.api_key:
            raise ValueError("SENTIMENT_API environment variable is required. Please set it in .env file.")
        
        self.base_url = config.get(
            "base_url",
            "https://api.santiment.net/graphql"
        )
        self.timeout = config.get("timeout", 30.0)
        self.retry_attempts = config.get("retry_attempts", 3)
        self.retry_delay = config.get("retry_delay", 1.0)
        
        self.headers = {
            "Authorization": f"Apikey {self.api_key}",
            "Content-Type": "application/json"
        }
        
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.headers
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _execute_query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a GraphQL query against Santiment API.
        
        Args:
            query: GraphQL query string
            variables: Optional query variables
            
        Returns:
            API response as dictionary
        """
        client = await self._ensure_client()
        
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        for attempt in range(self.retry_attempts):
            try:
                response = await client.post(
                    self.base_url,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("errors"):
                    error_msg = result.get("errors", [{}])[0].get("message", "Unknown API error")
                    raise SantimentAPIError(f"API error: {error_msg}")
                
                return result
                
            except httpx.HTTPStatusError as e:
                if attempt < self.retry_attempts - 1:
                    log.warning(f"Santiment API HTTP error (attempt {attempt + 1}/{self.retry_attempts}): {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise SantimentAPIError(f"HTTP error: {e}")
            except httpx.TimeoutException as e:
                if attempt < self.retry_attempts - 1:
                    log.warning(f"Santiment API timeout (attempt {attempt + 1}/{self.retry_attempts})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise SantimentAPIError(f"Request timeout: {e}")
            except Exception as e:
                if attempt < self.retry_attempts - 1:
                    log.warning(f"Santiment API error (attempt {attempt + 1}/{self.retry_attempts}): {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise SantimentAPIError(f"Request failed: {e}")
        
        raise SantimentAPIError(f"Failed after {self.retry_attempts} attempts")
    
    async def get_sentiment_balance(
        self,
        asset: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get sentiment balance for an asset.
        
        Args:
            asset: Cryptocurrency slug (e.g., "bitcoin", "ethereum")
            days: Number of days to calculate average (default: 7)
            
        Returns:
            Dict with average sentiment balance and timeseries data
        """
        now = datetime.now(timezone.utc)
        to_date = now
        from_date = to_date - timedelta(days=days)
        
        query = f"""
        {{
          getMetric(metric: "sentiment_balance_total") {{
            timeseriesData(
              slug: "{asset}"
              from: "{from_date.isoformat()}"
              to: "{to_date.isoformat()}"
              interval: "1d"
            ) {{
              datetime
              value
            }}
          }}
        }}
        """
        
        result = await self._execute_query(query)
        timeseries = result.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
        
        if not timeseries:
            return {
                "success": False,
                "error": f"Unable to fetch sentiment data for {asset}",
                "asset": asset,
                "average_balance": None,
                "timeseries": []
            }
        
        values = [float(d["value"]) for d in timeseries if d.get("value") is not None]
        avg_balance = sum(values) / len(values) if values else 0.0
        
        return {
            "success": True,
            "asset": asset,
            "average_balance": avg_balance,
            "timeseries": timeseries,
            "days": days
        }
    
    async def get_social_volume(
        self,
        asset: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get social volume for an asset.
        
        Args:
            asset: Cryptocurrency slug (e.g., "bitcoin", "ethereum")
            days: Number of days to sum (default: 7)
            
        Returns:
            Dict with total social volume and timeseries data
        """
        now = datetime.now(timezone.utc)
        to_date = now
        from_date = to_date - timedelta(days=days)
        
        query = f"""
        {{
          getMetric(metric: "social_volume_total") {{
            timeseriesData(
              slug: "{asset}"
              from: "{from_date.isoformat()}"
              to: "{to_date.isoformat()}"
              interval: "1d"
            ) {{
              datetime
              value
            }}
          }}
        }}
        """
        
        result = await self._execute_query(query)
        timeseries = result.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
        
        if not timeseries:
            return {
                "success": False,
                "error": f"Unable to fetch social volume for {asset}",
                "asset": asset,
                "total_volume": 0,
                "timeseries": []
            }
        
        values = [int(d["value"]) for d in timeseries if d.get("value") is not None]
        total_volume = sum(values)
        
        return {
            "success": True,
            "asset": asset,
            "total_volume": total_volume,
            "timeseries": timeseries,
            "days": days
        }
    
    async def get_social_dominance(
        self,
        asset: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get social dominance for an asset.
        
        Args:
            asset: Cryptocurrency slug (e.g., "bitcoin", "ethereum")
            days: Number of days to calculate average (default: 7)
            
        Returns:
            Dict with average social dominance and timeseries data
        """
        now = datetime.now(timezone.utc)
        to_date = now
        from_date = to_date - timedelta(days=days)
        
        query = f"""
        {{
          getMetric(metric: "social_dominance_total") {{
            timeseriesData(
              slug: "{asset}"
              from: "{from_date.isoformat()}"
              to: "{to_date.isoformat()}"
              interval: "1d"
            ) {{
              datetime
              value
            }}
          }}
        }}
        """
        
        result = await self._execute_query(query)
        timeseries = result.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
        
        if not timeseries:
            return {
                "success": False,
                "error": f"Unable to fetch social dominance for {asset}",
                "asset": asset,
                "average_dominance": None,
                "timeseries": []
            }
        
        values = [float(d["value"]) for d in timeseries if d.get("value") is not None]
        avg_dominance = sum(values) / len(values) if values else 0.0
        
        return {
            "success": True,
            "asset": asset,
            "average_dominance": avg_dominance,
            "timeseries": timeseries,
            "days": days
        }
    
    async def alert_social_shift(
        self,
        asset: str,
        threshold: float = 50.0,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Detect significant shifts in social volume.
        
        Args:
            asset: Cryptocurrency slug (e.g., "bitcoin", "ethereum")
            threshold: Minimum percentage change to trigger alert (default: 50.0)
            days: Number of days to analyze (default: 7)
            
        Returns:
            Dict with shift detection results
        """
        volume_data = await self.get_social_volume(asset, days)
        
        if not volume_data.get("success") or not volume_data.get("timeseries"):
            return {
                "success": False,
                "error": f"Unable to detect social volume shift for {asset}, insufficient data.",
                "asset": asset,
                "shift_detected": False
            }
        
        timeseries = volume_data["timeseries"]
        if len(timeseries) < 2:
            return {
                "success": False,
                "error": f"Unable to detect social volume shift for {asset}, insufficient data.",
                "asset": asset,
                "shift_detected": False
            }
        
        latest_volume = int(timeseries[-1]["value"]) if timeseries[-1].get("value") else 0
        prev_values = [int(d["value"]) for d in timeseries[:-1] if d.get("value") is not None]
        prev_avg_volume = sum(prev_values) / len(prev_values) if prev_values else 0
        
        if prev_avg_volume == 0:
            return {
                "success": False,
                "error": "Cannot calculate shift: previous average volume is zero",
                "asset": asset,
                "shift_detected": False
            }
        
        change_percent = ((latest_volume - prev_avg_volume) / prev_avg_volume) * 100
        abs_change = abs(change_percent)
        shift_detected = abs_change >= threshold
        
        return {
            "success": True,
            "asset": asset,
            "shift_detected": shift_detected,
            "change_percent": change_percent,
            "abs_change_percent": abs_change,
            "latest_volume": latest_volume,
            "previous_avg_volume": prev_avg_volume,
            "direction": "spike" if change_percent > 0 else "drop",
            "threshold": threshold
        }
    
    async def get_trending_words(
        self,
        days: int = 7,
        top_n: int = 5
    ) -> Dict[str, Any]:
        """
        Get trending words in crypto space.
        
        Args:
            days: Number of days to analyze (default: 7)
            top_n: Number of top words to return (default: 5)
            
        Returns:
            Dict with top trending words and scores
        """
        now = datetime.now(timezone.utc)
        to_date = now
        from_date = to_date - timedelta(days=days)
        
        query = f"""
        {{
          getTrendingWords(size: 10, from: "{from_date.isoformat()}", to: "{to_date.isoformat()}", interval: "1d") {{
            datetime
            topWords {{
              word
              score
            }}
          }}
        }}
        """
        
        result = await self._execute_query(query)
        trends = result.get("data", {}).get("getTrendingWords", [])
        
        if not trends:
            return {
                "success": False,
                "error": "Unable to fetch trending words",
                "top_words": []
            }
        
        word_scores = {}
        for day in trends:
            top_words = day.get("topWords", [])
            for word_data in top_words:
                word = word_data.get("word")
                score = word_data.get("score", 0)
                if word:
                    if word in word_scores:
                        word_scores[word] += score
                    else:
                        word_scores[word] = score
        
        if not word_scores:
            return {
                "success": False,
                "error": "No trending words data available",
                "top_words": []
            }
        
        top_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
        
        return {
            "success": True,
            "top_words": [{"word": word, "score": score} for word, score in top_words],
            "days": days,
            "top_n": top_n
        }

