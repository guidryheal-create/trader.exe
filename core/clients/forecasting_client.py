"""
Forecasting API client for guidry-cloud.com integration.
"""
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta, timezone
from time import perf_counter
import httpx
from httpx import TimeoutException, RemoteProtocolError, ConnectError, NetworkError
from core.logging import log
from core.mocks.mock_forecasting_service import get_mock_forecasting_service
from core.clients.guidry_stats_client import guidry_cloud_stats
from core.models.asset_registry import get_assets, get_symbol


class ForecastingAPIError(Exception):
    """Base exception for forecasting API operations."""
    pass


class AssetNotEnabledError(ForecastingAPIError):
    """Raised when the forecasting API reports that an asset is not enabled."""

    def __init__(self, ticker: str, message: str):
        self.ticker = ticker
        super().__init__(message)


class ForecastingClient:
    """Client for interacting with the forecasting API at guidry-cloud.com."""
    
    def __init__(self, config: Dict[str, Any]):
        # ✅ Ensure base_url is set from config, fallback to settings, then default
        self.base_url = config.get("base_url")
        if not self.base_url:
            from core.settings.config import settings
            # Prefer Hygdra / forecasting API URL when available, then legacy MCP URL
            self.base_url = (
                getattr(settings, "forecasting_api_url", None)
                or getattr(settings, "hygdra_forecasting_api_url", None)
                or getattr(settings, "mcp_api_url", None)
                or "https://forecasting.guidry-cloud.com/mcp"
            )
        # Ensure base_url doesn't end with trailing slash (httpx handles paths correctly)
        self.base_url = self.base_url.rstrip("/")
        self.api_key = config.get("api_key")
        # ✅ Increased timeout for better reliability (was 30.0, now 60.0)
        self.timeout = config.get("timeout", 60.0)
        self.retry_attempts = config.get("retry_attempts", 3)
        self.retry_delay = config.get("retry_delay", 2.0)  # Increased from 1.0 to 2.0
        
        # HTTP client
        self.client: Optional[httpx.AsyncClient] = None
        # ✅ Track which event loop the client was created in
        # This is critical because httpx.AsyncClient binds to the event loop at creation time
        # and cannot be used in a different event loop
        self._client_loop_id: Optional[int] = None
        
        # Cache for frequently accessed data
        self.cache: Dict[str, Any] = {}
        self.cache_ttl: Dict[str, datetime] = {}
        self.default_cache_ttl = timedelta(minutes=5)
        
        # Mock mode (explicit flag preferred, falls back to legacy config flag)
        mock_mode = config.get("mock_mode")
        if mock_mode is None:
            mock_mode = bool(config.get("use_mock_services", False))
        self.is_mock = bool(mock_mode)
        self.mock_data: Dict[str, Any] = {}
        self.mock_service = None
    
    async def connect(self) -> None:
        """Initialize the HTTP client."""
        try:
            # ✅ CRITICAL: Always reload base_url from settings to ensure we use the latest .env value
            from core.settings.config import settings
            # Prefer explicit Hygdra/forecasting API settings if present
            current_url = (
                getattr(settings, "forecasting_api_url", None)
                or getattr(settings, "hygdra_forecasting_api_url", None)
                or getattr(settings, "mcp_api_url", None)
                or "https://forecasting.guidry-cloud.com/mcp"
            )
            # If Docker internal or non-HTTPS URL detected in CI/dev, fall back to public endpoint
            if not current_url.startswith("https://") or "localhost" in current_url:
                public_url = "https://forecasting.guidry-cloud.com/mcp"
                log.warning(f"Non-HTTPS or local forecasting URL detected, using public URL: {public_url}")
                current_url = public_url

            # Normalize MCP endpoint (accept /mcp/tools and append /mcp if missing)
            if current_url.endswith("/mcp/tools"):
                current_url = current_url[:-6]
            if current_url.endswith("/mcp/"):
                current_url = current_url[:-1]
            if current_url.endswith("/mcp") or "/mcp" in current_url:
                normalized_url = current_url
            else:
                normalized_url = f"{current_url.rstrip('/')}/mcp"

            # Reload base_url from settings to ensure latest env value
            if not self.base_url or self.base_url != normalized_url:
                self.base_url = normalized_url.rstrip("/")
                log.info(f"✅ Reloaded base_url from settings: {self.base_url}")
            
            # ✅ Ensure API key is loaded from settings if not provided in config
            if not self.api_key:
                self.api_key = settings.mcp_api_key
            
            if not self.is_mock and not self.api_key:
                log.warning("Forecasting API key not found. Some requests may fail with 401 Unauthorized.")
                # Don't raise error, allow connection but log warning

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "AgenticTradingSystem/1.0.0"
            }
            
            # ✅ Always set X-API-Key header if available (required by MCP API)
            if self.api_key:
                headers["X-API-Key"] = self.api_key
                log.debug(f"Forecasting API client configured with API key (length: {len(self.api_key)})")
            else:
                log.warning("Forecasting API client initialized without API key - requests may fail")
            
            # ✅ Log base URL for debugging
            log.info(f"Forecasting API client initializing with base_url: {self.base_url}")
            
            # ✅ DEBUG: Check event loop state before creating httpx client
            # httpx.AsyncClient binds to the current event loop, so we need a valid loop
            try:
                current_loop = asyncio.get_running_loop()
                loop_running = current_loop.is_running()
                loop_closed = current_loop.is_closed()
                log.debug(
                    f"[ForecastingClient] Creating httpx.AsyncClient:\n"
                    f"  Loop running: {loop_running}\n"
                    f"  Loop closed: {loop_closed}\n"
                    f"  Loop ID: {id(current_loop)}"
                )
                if loop_closed:
                    log.error(
                        f"[ForecastingClient] ⚠️ WARNING: Creating httpx.AsyncClient with a CLOSED event loop!\n"
                        f"  This will cause RuntimeError: Event loop is closed when making requests.\n"
                        f"  The client should be created in a valid, running event loop."
                    )
            except RuntimeError as loop_check_error:
                log.error(
                    f"[ForecastingClient] ⚠️ WARNING: No running event loop when creating httpx.AsyncClient:\n"
                    f"  Error: {loop_check_error}\n"
                    f"  httpx.AsyncClient requires a running event loop."
                )
            
            # Configure HTTP/2 settings to handle connection termination gracefully
            # ✅ Increased timeouts: connect=20.0, read=self.timeout (60.0), write=20.0
            # Note: httpx.AsyncClient binds to the current event loop at creation time
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=20.0, read=self.timeout, write=20.0),
                limits=httpx.Limits(
                    max_keepalive_connections=10,  # Reduced to prevent connection pool exhaustion
                    max_connections=50,  # Reduced to prevent connection pool exhaustion
                    keepalive_expiry=60.0  # Close idle connections after 60s (increased from 30s)
                ),
                http2=True,  # Enable HTTP/2 but handle connection errors gracefully
                verify=False  # Disable SSL verification for development/testing
            )
            
            if self.is_mock:
                self.mock_service = await get_mock_forecasting_service()
                await self._setup_mock_data()
            
            # ✅ Track the event loop ID where the client was created
            try:
                current_loop = asyncio.get_running_loop()
                self._client_loop_id = id(current_loop)
                log.debug(f"[ForecastingClient] Client bound to event loop ID: {self._client_loop_id}")
            except RuntimeError:
                # No running loop - this shouldn't happen during connect, but handle gracefully
                self._client_loop_id = None
                log.warning("[ForecastingClient] No running loop when creating client - client may not work correctly")
            
            log.info(f"✅ Forecasting API client connected to {self.base_url} (client base_url: {self.client.base_url})")     
              
        except Exception as e:
            log.error(f"Failed to connect to forecasting API: {e}")
            raise ForecastingAPIError(f"Connection failed: {e}")
    
    async def initialize(self) -> None:
        """Initialize the forecasting client (alias for connect)."""
        try:
            await self.connect()        
        except Exception as e:
            log.error(f"Failed to connect to forecasting API: {e}")
            raise ForecastingAPIError(f"Connection failed: {e}")
    
    async def disconnect(self, silent: bool = False) -> None:
        """
        Close the HTTP client.
        
        Args:
            silent: If True, suppress warnings about event loop closure.
                   Useful when disconnecting before recreating client in a new loop.
        """
        if self.client:
            try:
                # Check if event loop is available before closing
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_closed():
                        if not silent:
                            log.warning("[ForecastingClient] Event loop is closed, skipping client close")
                        self.client = None
                        self._client_loop_id = None
                        return
                except RuntimeError:
                    if not silent:
                        log.warning("[ForecastingClient] No running event loop, skipping client close")
                    self.client = None
                    self._client_loop_id = None
                    return
                
                await self.client.aclose()
                self.client = None
                self._client_loop_id = None  # Reset loop ID when disconnecting
                if not silent:
                    log.info("Forecasting API client disconnected")
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    if not silent:
                        log.warning(f"[ForecastingClient] Event loop closed during disconnect: {e}")
                    self.client = None
                    self._client_loop_id = None
                else:
                    raise
            except Exception as e:
                if not silent:
                    log.warning(f"[ForecastingClient] Error during disconnect: {e}")
                self.client = None
                self._client_loop_id = None
    
    async def _setup_mock_data(self) -> None:
        """Setup mock data for testing."""
        self.mock_data = {
            "tickers": [
                {"symbol": "BTC-USD", "name": "Bitcoin", "type": "crypto", "intervals": ["minutes", "hours", "days", "thirty"], "has_dqn": True},
                {"symbol": "ETH-USD", "name": "Ethereum", "type": "crypto", "intervals": ["minutes", "hours", "days", "thirty"], "has_dqn": True},
                {"symbol": "SOL-USD", "name": "Solana", "type": "crypto", "intervals": ["minutes", "hours", "days", "thirty"], "has_dqn": True},
            ],
            "actions": {
                "BTC-USD": {"hours": {"action": 2, "action_confidence": 0.85, "forecast_price": 47000.0}, "days": {"action": 2, "action_confidence": 0.78, "forecast_price": 50000.0}},
                "ETH-USD": {"hours": {"action": 1, "action_confidence": 0.72, "forecast_price": 2100.0}, "days": {"action": 2, "action_confidence": 0.81, "forecast_price": 2300.0}},
                "SOL-USD": {"hours": {"action": 0, "action_confidence": 0.68, "forecast_price": 95.0}, "days": {"action": 1, "action_confidence": 0.75, "forecast_price": 100.0}},
            },
            "metrics": {
                "BTC-USD": {"hours": {"accuracy": 0.82, "sharpe_ratio": 1.45, "max_drawdown": 0.12}, "days": {"accuracy": 0.78, "sharpe_ratio": 1.32, "max_drawdown": 0.15}},
                "ETH-USD": {"hours": {"accuracy": 0.79, "sharpe_ratio": 1.28, "max_drawdown": 0.14}, "days": {"accuracy": 0.81, "sharpe_ratio": 1.41, "max_drawdown": 0.13}},
                "SOL-USD": {"hours": {"accuracy": 0.75, "sharpe_ratio": 1.15, "max_drawdown": 0.18}, "days": {"accuracy": 0.77, "sharpe_ratio": 1.22, "max_drawdown": 0.16}},
            }
        }
    
    def _normalise_ohlc_entry(self, entry: Any) -> Optional[Dict[str, Any]]:
        """Normalise a single OHLC candle from external API responses."""
        if not isinstance(entry, dict):
            return None

        lowered = {str(key).lower(): value for key, value in entry.items()}

        timestamp = None
        for key, value in entry.items():
            if str(key).lower() in {"timestamp", "time", "date"}:
                timestamp = value
                break
        if not timestamp:
            return None

        def to_float(value: Any) -> Optional[float]:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        normalised = {
            "timestamp": timestamp,
            "open": to_float(lowered.get("open")),
            "high": to_float(lowered.get("high")),
            "low": to_float(lowered.get("low")),
            "close": to_float(lowered.get("close")),
            "volume": to_float(lowered.get("volume")) or 0.0,
        }

        if any(normalised.get(field) is None for field in ("open", "high", "low", "close")):
            return None

        return normalised

    def _normalise_forecast_entry(self, ticker: str, interval: str, entry: Any) -> Optional[Dict[str, Any]]:
        """Normalise forecast entries returned by the forecasting API."""
        if not isinstance(entry, dict):
            return None

        lowered = {str(key).lower(): value for key, value in entry.items()}

        timestamp = None
        for key, value in entry.items():
            if str(key).lower() in {"timestamp", "time", "date"}:
                timestamp = value
                break
        prediction_time = entry.get("pred_date") or entry.get("prediction_time")

        def to_float(value: Any) -> Optional[float]:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        forecast_value = to_float(
            lowered.get("forecasting")
            or lowered.get("forecast")
            or lowered.get("prediction")
        )
        close_value = to_float(lowered.get("close"))

        if not timestamp and not prediction_time:
            return None

        normalised = {
            "ticker": ticker,
            "interval": interval,
            "timestamp": timestamp,
            "prediction_time": prediction_time,
            "forecast": forecast_value,
            "price": forecast_value,
            "close": close_value,
        }

        # Preserve any additional attributes for transparency/debugging.
        for key, value in entry.items():
            if key not in normalised:
                normalised[key] = value

        return normalised

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic.
        
        ✅ Event Loop Handling:
        - This method runs in an isolated thread with its own event loop (via async_wrapper)
        - Each tool call gets a fresh event loop created by async_wrapper
        - httpx.AsyncClient is bound to the event loop at creation time (in connect())
        - If the event loop closes during request execution, we catch RuntimeError and fail fast
        - We don't retry on event loop closure because retrying in a closed loop won't work
        - The async_wrapper will create a new loop for the next tool call
        
        ✅ Error Handling:
        - RuntimeError about event loop closure: Fail fast, don't retry
        - Connection errors (RemoteProtocolError, ConnectError, NetworkError): Retry with backoff
        - HTTP errors (429, 502, 503, 504): Retry with backoff
        - Timeout errors: Retry with backoff
        - Other errors: Retry with backoff, but check loop state before sleep
        
        ✅ Diagnostics:
        - Logs event loop state before requests and on errors
        - Logs detailed error context including loop state and client state
        """
        # ✅ CRITICAL: Ensure client is bound to the current event loop
        # httpx.AsyncClient is bound to the event loop at creation time and cannot be used
        # across different event loops. Since async_wrapper creates a NEW event loop for each
        # tool call, we must recreate the client for each new loop to ensure isolation.
        current_loop_id = None
        try:
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)
        except RuntimeError:
            pass
        
        # ✅ ISOLATION: Recreate client if:
        # 1. Client doesn't exist, OR
        # 2. Client exists but is bound to a different event loop (different tool call)
        # This ensures each tool call gets its own isolated client bound to its own event loop
        if not self.client or (current_loop_id is not None and self._client_loop_id != current_loop_id):
            if not self.client:
                log.debug("[ForecastingClient] Client not connected, attempting to reconnect...")
            else:
                log.debug(
                    f"[ForecastingClient] Client bound to different event loop "
                    f"(client_loop_id={self._client_loop_id}, current_loop_id={current_loop_id}), recreating..."
                )
                # Close the old client before creating a new one
                # Use silent disconnect since we're about to recreate anyway
                try:
                    await self.disconnect(silent=True)
                except Exception:
                    # Ignore all errors when closing old client - we're recreating anyway
                    self.client = None
                    self._client_loop_id = None
            
            try:
                # ✅ DEBUG: Check loop state before connecting
                try:
                    loop = asyncio.get_running_loop()
                    log.debug(f"[ForecastingClient] Reconnecting: loop_running={loop.is_running()}, loop_closed={loop.is_closed()}, loop_id={id(loop)}")
                except RuntimeError as loop_check:
                    log.debug(f"[ForecastingClient] Cannot check loop state before reconnect: {loop_check}")
                
                await self.connect()
                log.debug(f"[ForecastingClient] Reconnected successfully (bound to loop_id={self._client_loop_id})")
            except Exception as connect_error:
                error_type = type(connect_error).__name__
                error_msg = str(connect_error)
                log.error(
                    f"[ForecastingClient] ❌ Reconnect failed:\n"
                    f"  Error type: {error_type}\n"
                    f"  Error message: {error_msg}\n"
                    f"  Endpoint: {endpoint}"
                )
                raise ForecastingAPIError(f"Not connected to forecasting API and reconnect failed: {error_msg}")
        
        # ✅ Log full URL for debugging (httpx will prepend base_url to endpoint)
        full_url = f"{self.base_url}{endpoint}" if endpoint.startswith("/") else f"{self.base_url}/{endpoint}"
        log.debug(f"[ForecastingClient] Making {method} request to: {full_url} (timeout={self.timeout}s, retry_attempts={self.retry_attempts})")
        
        for attempt in range(self.retry_attempts):
            start = perf_counter()
            
            # ✅ DEBUG: Check event loop state before request (for diagnostics)
            try:
                current_loop = asyncio.get_running_loop()
                loop_running = current_loop.is_running()
                loop_closed = current_loop.is_closed()
                log.debug(f"[ForecastingClient] Pre-request check (attempt {attempt + 1}): loop_running={loop_running}, loop_closed={loop_closed}")
            except RuntimeError as loop_check_error:
                log.debug(f"[ForecastingClient] Pre-request loop check failed: {loop_check_error}")
            
            try:
                # ✅ Simple HTTP request - event loop isolation is handled by async_wrapper
                log.debug(f"[ForecastingClient] Executing {method} request (attempt {attempt + 1}/{self.retry_attempts})")
                if method == "GET":
                    response = await self.client.get(endpoint, params=params)
                elif method == "POST":
                    response = await self.client.post(endpoint, params=params, json=data)
                else:
                    raise ForecastingAPIError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                duration = perf_counter() - start
                guidry_cloud_stats.record_success(endpoint, response.status_code, duration)
                return response.json()
                
            except httpx.HTTPStatusError as e:
                duration = perf_counter() - start
                status_code = e.response.status_code
                detail = self._extract_error_detail(e)
                ticker = self._extract_ticker_from_endpoint(endpoint, params, data)
                guidry_cloud_stats.record_failure(
                    endpoint=endpoint,
                    status=status_code,
                    duration_secs=duration,
                    error=detail,
                    rate_limited=status_code == 429,
                    disabled_asset=ticker if detail and "not enabled" in detail.lower() else None,
                )
                if e.response.status_code == 400:
                    if detail and "not enabled" in detail.lower():
                        raise AssetNotEnabledError(ticker or "UNKNOWN", detail)
                if status_code in [429, 502, 503, 504] and attempt < self.retry_attempts - 1:
                    # Retry on rate limit or server errors
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise ForecastingAPIError(f"HTTP error {status_code}: {e.response.text}")
            except (RemoteProtocolError, ConnectError, NetworkError) as e:
                # Handle connection errors (connection terminated, network issues, etc.)
                duration = perf_counter() - start
                error_type = type(e).__name__
                log.warning(f"[ForecastingClient] Connection error on attempt {attempt + 1}/{self.retry_attempts}: {error_type}: {e}")
                guidry_cloud_stats.record_failure(
                    endpoint=endpoint,
                    status=0,
                    duration_secs=duration,
                    error=f"{error_type}: {str(e)}",
                    connection_error=True,
                )
                # Retry connection errors with exponential backoff
                if attempt < self.retry_attempts - 1:
                    # For connection errors, wait longer before retry
                    retry_delay = self.retry_delay * (2 ** attempt) * 2  # Double the delay for connection errors
                    log.info(f"[ForecastingClient] Retrying in {retry_delay:.1f}s...")
                    await asyncio.sleep(retry_delay)
                    # Reconnect client if connection was terminated
                    if isinstance(e, RemoteProtocolError):
                        try:
                            await self.disconnect()
                            await self.connect()
                            log.info("[ForecastingClient] Reconnected after connection termination")
                        except Exception as reconnect_error:
                            log.warning(f"[ForecastingClient] Failed to reconnect: {reconnect_error}")
                    continue
                raise ForecastingAPIError(f"Connection error after {self.retry_attempts} attempts: {error_type}: {e}")
            except TimeoutException as e:
                duration = perf_counter() - start
                log.warning(f"[ForecastingClient] Timeout on attempt {attempt + 1}/{self.retry_attempts}: {e}")
                guidry_cloud_stats.record_failure(
                    endpoint=endpoint,
                    status=0,
                    duration_secs=duration,
                    error=f"Timeout: {str(e)}",
                    timeout=True,
                )
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise ForecastingAPIError(f"Request timeout after {self.timeout}s: {e}")
            except RuntimeError as e:
                # ✅ Handle event loop closure specifically - don't retry, just fail fast
                # The async_wrapper will create a new loop for the next tool call
                error_msg = str(e)
                duration = perf_counter() - start
                
                # ✅ DEBUG: Enhanced diagnostics for RuntimeError
                is_event_loop_error = "event loop" in error_msg.lower() or "Event loop is closed" in error_msg
                
                # Check current loop state for diagnostics
                loop_state_info = {}
                try:
                    current_loop = asyncio.get_running_loop()
                    loop_state_info = {
                        "loop_running": current_loop.is_running(),
                        "loop_closed": current_loop.is_closed(),
                        "has_loop": True
                    }
                except RuntimeError as loop_check_error:
                    loop_state_info = {
                        "has_loop": False,
                        "loop_check_error": str(loop_check_error)
                    }
                
                # Check client state
                client_state_info = {
                    "client_exists": self.client is not None,
                    "client_type": type(self.client).__name__ if self.client else None
                }
                
                if is_event_loop_error:
                    log.error(
                        f"[ForecastingClient] ❌ Event loop closed during request (attempt {attempt + 1}/{self.retry_attempts}):\n"
                        f"  Error: {error_msg}\n"
                        f"  Endpoint: {full_url}\n"
                        f"  Loop state: {loop_state_info}\n"
                        f"  Client state: {client_state_info}\n"
                        f"  Duration before error: {duration:.3f}s\n"
                        f"  Context: This error occurs when httpx.AsyncClient tries to use a closed event loop.\n"
                        f"  Root cause: The event loop was closed (likely by async_wrapper cleanup) while the request was in progress.\n"
                        f"  Solution: async_wrapper will create a new loop for the next tool call, so failing fast is correct."
                    )
                    guidry_cloud_stats.record_failure(
                        endpoint=endpoint,
                        status=0,
                        duration_secs=duration,
                        error=f"Event loop closed: {error_msg}",
                        connection_error=True,
                    )
                    # Don't retry - event loop is closed, retrying won't help
                    # The async_wrapper will handle creating a new loop for the next tool call
                    raise ForecastingAPIError(f"Event loop closed during request: {error_msg}")
                else:
                    # Other RuntimeError - log diagnostics but re-raise as-is
                    log.warning(
                        f"[ForecastingClient] RuntimeError (not event loop closure) on attempt {attempt + 1}:\n"
                        f"  Error: {error_msg}\n"
                        f"  Endpoint: {full_url}\n"
                        f"  Loop state: {loop_state_info}\n"
                        f"  Client state: {client_state_info}"
                    )
                    raise
            except Exception as e:
                duration = perf_counter() - start
                error_type = type(e).__name__
                error_msg = str(e)
                
                # ✅ DEBUG: Check if this is a RuntimeError that wasn't caught by RuntimeError handler
                # (shouldn't happen, but useful for diagnostics)
                is_runtime_error = isinstance(e, RuntimeError)
                if is_runtime_error and ("event loop" in error_msg.lower() or "Event loop is closed" in error_msg):
                    # This should have been caught by RuntimeError handler above, but log it anyway
                    log.error(
                        f"[ForecastingClient] ⚠️ RuntimeError about event loop caught in generic Exception handler "
                        f"(should have been caught earlier): {error_msg}"
                    )
                    # Re-raise as ForecastingAPIError to avoid retry loop
                    raise ForecastingAPIError(f"Event loop closed: {error_msg}")
                
                log.error(
                    f"[ForecastingClient] Error on attempt {attempt + 1}/{self.retry_attempts}:\n"
                    f"  Error type: {error_type}\n"
                    f"  Error message: {error_msg}\n"
                    f"  Endpoint: {full_url}\n"
                    f"  Duration: {duration:.3f}s"
                )
                
                guidry_cloud_stats.record_failure(
                    endpoint=endpoint,
                    status=0,
                    duration_secs=duration,
                    error=f"{error_type}: {error_msg}",
                    timeout=isinstance(e, TimeoutException),
                    connection_error=isinstance(e, (ConnectError, NetworkError, RemoteProtocolError)),
                )
                if attempt < self.retry_attempts - 1:
                    retry_delay = self.retry_delay * (2 ** attempt)
                    log.info(f"[ForecastingClient] Retrying in {retry_delay:.1f}s...")
                    try:
                        # ✅ DEBUG: Check loop state before sleep
                        try:
                            loop = asyncio.get_running_loop()
                            if loop.is_closed():
                                log.error(f"[ForecastingClient] ❌ Event loop is closed, cannot retry (sleep would fail)")
                                raise ForecastingAPIError(f"Event loop closed, cannot retry: {error_msg}")
                        except RuntimeError as loop_check:
                            log.error(f"[ForecastingClient] ❌ Cannot check loop state for retry: {loop_check}")
                            raise ForecastingAPIError(f"Cannot retry due to loop state: {error_msg}")
                        
                        await asyncio.sleep(retry_delay)
                    except RuntimeError as sleep_error:
                        # Event loop closed during sleep - can't retry
                        sleep_error_msg = str(sleep_error)
                        if "event loop" in sleep_error_msg.lower() or "Event loop is closed" in sleep_error_msg:
                            log.error(
                                f"[ForecastingClient] ❌ Event loop closed during retry delay sleep:\n"
                                f"  Original error: {error_type}: {error_msg}\n"
                                f"  Sleep error: {sleep_error_msg}\n"
                                f"  Endpoint: {full_url}"
                            )
                            raise ForecastingAPIError(f"Event loop closed during retry delay: {error_msg}")
                        raise
                    continue
                raise ForecastingAPIError(f"Request failed after {self.retry_attempts} attempts: {error_type}: {error_msg}")
        
        raise ForecastingAPIError("Max retry attempts exceeded")

    @staticmethod
    def _extract_error_detail(error: httpx.HTTPStatusError) -> Optional[str]:
        try:
            payload = error.response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            for key in ("detail", "message", "error"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    nested_detail = value.get("detail") or value.get("message")
                    if isinstance(nested_detail, str):
                        return nested_detail
        elif isinstance(payload, str):
            return payload

        text = error.response.text
        return text if text else None

    @staticmethod
    def _extract_ticker_from_endpoint(
        endpoint: str,
        params: Optional[Dict[str, Any]],
        data: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Best-effort attempt to recover the ticker from the request context."""

        # Direct parameter overrides
        for source in (params, data):
            if isinstance(source, dict):
                ticker = source.get("ticker") or source.get("symbol")
                if isinstance(ticker, str):
                    return ticker

        # Endpoints of the form /api/json/action/<symbol>/<interval>
        parts = endpoint.strip("/").split("/")
        if len(parts) >= 4 and parts[-3] == "action":
            return parts[-2]
        if len(parts) >= 3 and parts[-2] in {"info", "metrics", "ohlc"}:
            return parts[-1]

        return None

    def get_stats_snapshot(self) -> Dict[str, Any]:
        """Return current aggregated statistics for Guidry Cloud API usage."""
        return guidry_cloud_stats.summary()
    
    # ------------------------------------------------------------------
    # DQN aggregation helpers
    # ------------------------------------------------------------------
    async def get_dqn_signals_for_universe(
        self,
        base_tickers: Optional[List[str]] = None,
        interval: str = "days",
    ) -> List[Dict[str, Any]]:
        """
        Fetch DQN action recommendations for a universe of base tickers.
        
        Args:
            base_tickers: List of base symbols like \"BTC\", \"ETH\". If None,
                uses asset_registry.get_assets() as the default universe.
            interval: Forecasting interval (\"minutes\", \"thirty\", \"hours\", \"days\").
        
        Returns:
            List of normalized records:
              {
                \"base_ticker\": \"BTC\",
                \"symbol\": \"BTC-USD\",
                \"interval\": \"days\",
                \"action\": int,
                \"action_confidence\": float,
                \"q_values\": list[float],
                \"forecast_price\": float | None,
                \"current_price\": float | None,
              }
        """
        # Normalise interval
        interval_norm = (interval or "").strip().lower()
        if interval_norm not in ["minutes", "thirty", "hours", "days"]:
            interval_norm = "days"

        # Default universe from asset registry
        if not base_tickers:
            base_tickers = get_assets()

        results: List[Dict[str, Any]] = []
        if not base_tickers:
            return results

        for base in base_tickers:
            base_symbol = str(base).upper()
            symbol = get_symbol(base_symbol)
            try:
                action_payload = await self.get_action_recommendation(symbol, interval_norm)
            except AssetNotEnabledError:
                # Skip disabled assets silently
                continue
            except ForecastingAPIError as e:
                log.debug(f"Skipping {symbol} for DQN aggregation due to API error: {e}")
                continue
            except Exception as e:
                log.debug(f"Unexpected error while fetching DQN action for {symbol}: {e}")
                continue

            if not isinstance(action_payload, dict):
                continue

            # Normalise minimal fields for ranking helpers
            record: Dict[str, Any] = {
                "base_ticker": base_symbol,
                "symbol": symbol,
                "interval": interval_norm,
                "action": action_payload.get("action"),
                "action_confidence": action_payload.get("action_confidence")
                or action_payload.get("confidence"),
                "q_values": action_payload.get("q_values") or [],
                "forecast_price": action_payload.get("forecast_price")
                or action_payload.get("forecast"),
                "current_price": action_payload.get("current_price"),
            }
            results.append(record)

        return results
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached data if not expired."""
        if key in self.cache and key in self.cache_ttl:
            from datetime import timezone
            if datetime.now(timezone.utc) < self.cache_ttl[key]:
                return self.cache[key]
            else:
                # Remove expired cache
                del self.cache[key]
                del self.cache_ttl[key]
        return None
    
    def _set_cache(self, key: str, value: Any, ttl: Optional[timedelta] = None) -> None:
        """Set cached data with TTL."""
        self.cache[key] = value
        from datetime import timezone
        self.cache_ttl[key] = datetime.now(timezone.utc) + (ttl or self.default_cache_ttl)

    def _use_mcp_tools(self) -> bool:
        """Return True if the client should call MCP /tools endpoints."""
        return "/mcp" in (self.base_url or "")
    
    async def get_available_tickers(self) -> List[Dict[str, Any]]:
        """Get list of available tickers."""
        cache_key = "available_tickers"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if self.is_mock:
            if self.mock_service:
                # Use comprehensive mock service
                tickers = await self.mock_service.get_available_tickers()
                result = [{"symbol": ticker, "name": ticker.replace("-", " "), "active": True} for ticker in tickers]
            else:
                result = self.mock_data["tickers"]
        else:
            try:
                if self._use_mcp_tools():
                    response = await self._make_request("GET", "/tools/list_available_tickers")
                else:
                    response = await self._make_request("GET", "/api/tickers/available")
                if isinstance(response, list):
                    result = response
                else:
                    result = response.get("tickers", [])
            except Exception as e:
                log.error(f"Failed to get available tickers: {e}")
                return []
        
        self._set_cache(cache_key, result)
        return result

    async def get_enabled_assets(self) -> List[str]:
        """Retrieve the list of assets currently enabled for trading."""
        cache_key = "enabled_assets"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if self.is_mock:
            assets = [ticker.replace("-USD", "") for ticker in self.mock_data.get("tickers", [])]
        else:
            try:
                response = await self._make_request("GET", "/attribute/enabled-assets")
                if isinstance(response, dict):
                    assets = response.get("assets", [])
                else:
                    assets = response
            except Exception as e:
                log.error(f"Failed to fetch enabled assets: {e}")
                return []

        self._set_cache(cache_key, assets, timedelta(minutes=10))
        return assets
    
    async def get_ticker_info(self, ticker: str) -> Dict[str, Any]:
        """Get detailed information about a specific ticker."""
        cache_key = f"ticker_info_{ticker}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if self.is_mock:
            # Find ticker in mock data
            ticker_data = next((t for t in self.mock_data["tickers"] if t["symbol"] == ticker), None)
            if not ticker_data:
                raise ForecastingAPIError(f"Ticker {ticker} not found")
            result = ticker_data
        else:
            try:
                response = await self._make_request("GET", f"/api/tickers/{ticker}/info")
                result = response
            except Exception as e:
                log.error(f"Failed to get ticker info for {ticker}: {e}")
                raise ForecastingAPIError(f"Failed to get ticker info: {e}")
        
        self._set_cache(cache_key, result, timedelta(hours=1))  # Cache for 1 hour
        return result
    
    async def get_action_recommendation(self, ticker: str, interval: str) -> Dict[str, Any]:
        """Get DQN action recommendation for a ticker and interval."""
        cache_key = f"action_{ticker}_{interval}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if self.is_mock:
            if self.mock_service:
                # Use comprehensive mock service
                mock_result = await self.mock_service.get_action_recommendation(ticker, interval)
                result = {
                    "action": 0 if mock_result["recommendation"] == "SELL" else 1 if mock_result["recommendation"] == "HOLD" else 2,
                    "action_confidence": mock_result["confidence"],
                    "forecast_price": mock_result.get("price_target", 100.0),
                    "q_values": [0.3, 0.5, 0.2],  # [SELL, HOLD, BUY]
                    "current_price": 100.0,
                    "recommendation": mock_result["recommendation"],
                    "reasoning": mock_result["reasoning"]
                }
            elif ticker in self.mock_data["actions"] and interval in self.mock_data["actions"][ticker]:
                result = self.mock_data["actions"][ticker][interval]
            else:
                # Default mock response
                result = {
                    "action": 1,  # HOLD
                    "action_confidence": 0.5,
                    "forecast_price": 100.0,
                    "q_values": [0.3, 0.5, 0.2],  # [SELL, HOLD, BUY]
                    "current_price": 100.0
                }
        else:
            try:
                if self._use_mcp_tools():
                    response = await self._make_request(
                        "GET",
                        "/tools/get_action_recommendation",
                        params={"ticker": ticker, "interval": interval},
                    )
                else:
                    response = await self._make_request("GET", f"/api/json/action/{ticker}/{interval}")
                if isinstance(response, dict) and "forecast" in response and "forecast_price" not in response:
                    response = {**response, "forecast_price": response.get("forecast")}
                result = response
            except AssetNotEnabledError:
                raise
            except Exception as e:
                log.error(f"Failed to get action recommendation for {ticker}/{interval}: {e}")
                raise ForecastingAPIError(f"Failed to get action recommendation: {e}")
        
        self._set_cache(cache_key, result, timedelta(minutes=2))  # Cache for 2 minutes
        return result
    
    async def get_stock_forecast(self, ticker: str, interval: str) -> Dict[str, Any]:
        """Get detailed stock forecast data."""
        cache_key = f"forecast_{ticker}_{interval}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if self.is_mock:
            if self.mock_service:
                # Use comprehensive mock service
                mock_result = await self.mock_service.get_stock_forecast(ticker, interval)
                result = {
                    "ticker": ticker,
                    "interval": interval,
                    "forecast_price": mock_result["forecast"][0]["price"] if mock_result["forecast"] else 100.0,
                    "confidence": mock_result["forecast"][0]["confidence"] if mock_result["forecast"] else 0.75,
                    "trend": mock_result["forecast"][0]["trend"] if mock_result["forecast"] else "bullish",
                    "support_levels": [95.0, 90.0],
                    "resistance_levels": [105.0, 110.0],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "forecast_data": mock_result["forecast"],
                    "model_version": mock_result.get("model_version", "v1.0.0")
                }
            else:
                # Generate mock forecast data
                result = {
                    "ticker": ticker,
                    "interval": interval,
                    "forecast_price": 100.0,
                    "confidence": 0.75,
                    "trend": "bullish",
                    "support_levels": [95.0, 90.0],
                    "resistance_levels": [105.0, 110.0],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
        else:
            try:
                if self._use_mcp_tools():
                    response = await self._make_request(
                        "GET",
                        "/tools/get_stock_forecast",
                        params={"ticker": ticker, "interval": interval},
                    )
                else:
                    response = await self._make_request("GET", f"/api/json/stock/{interval}/{ticker}")
                if isinstance(response, list):
                    normalised = [
                        record
                        for record in (
                            self._normalise_forecast_entry(ticker, interval, item)
                            for item in response
                        )
                        if record
                    ]
                    forecast_price = None
                    for record in reversed(normalised):
                        if record.get("forecast") is not None:
                            forecast_price = record["forecast"]
                            break

                    result = {
                        "ticker": ticker,
                        "interval": interval,
                        "forecast_price": forecast_price,
                        "forecast_data": normalised,
                    }
                elif isinstance(response, dict):
                    if "forecast_price" not in response:
                        forecast_val = response.get("forecast") or response.get("forecasting")
                        if forecast_val is not None:
                            try:
                                forecast_val = float(forecast_val)
                            except (TypeError, ValueError):
                                forecast_val = None
                        response = {**response, "forecast_price": forecast_val}
                    result = response
                else:
                    result = {
                        "ticker": ticker,
                        "interval": interval,
                        "forecast_price": None,
                        "forecast_data": [],
                    }
            except Exception as e:
                log.error(f"Failed to get stock forecast for {ticker}/{interval}: {e}")
                raise ForecastingAPIError(f"Failed to get stock forecast: {e}")
        
        self._set_cache(cache_key, result, timedelta(minutes=5))  # Cache for 5 minutes
        return result
    
    async def get_model_metrics(self, ticker: str, interval: str) -> Dict[str, Any]:
        """Get model performance metrics."""
        cache_key = f"metrics_{ticker}_{interval}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if self.is_mock:
            if ticker in self.mock_data["metrics"] and interval in self.mock_data["metrics"][ticker]:
                result = self.mock_data["metrics"][ticker][interval]
            else:
                # Default mock metrics
                result = {
                    "accuracy": 0.75,
                    "sharpe_ratio": 1.2,
                    "max_drawdown": 0.15,
                    "win_rate": 0.65,
                    "total_trades": 100,
                    "avg_return": 0.02
                }
        else:
            try:
                response = await self._make_request("GET", f"/api/json/metrics/{ticker}/{interval}")
                result = response
            except Exception as e:
                log.error(f"Failed to get model metrics for {ticker}/{interval}: {e}")
                raise ForecastingAPIError(f"Failed to get model metrics: {e}")
        
        self._set_cache(cache_key, result, timedelta(hours=1))  # Cache for 1 hour
        return result
    
    async def get_ohlc(self, ticker: str, interval: str, limit: int = 120) -> List[Dict[str, Any]]:
        """Fetch OHLC candles for a ticker/interval."""
        cache_key = f"ohlc_{ticker}_{interval}_{limit}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if self.is_mock:
            if self.mock_service:
                candles = await self.mock_service.get_ohlc(ticker, interval, limit=limit)
            else:
                candles = [
                    {
                        "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=limit - i)).isoformat(),
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.5,
                        "close": 100.5,
                        "volume": 1_000_000,
                    }
                    for i in range(limit)
                ]
        else:
            params = {"limit": limit}
            try:
                response = await self._make_request("GET", f"/api/json/ohlc/{interval}/{ticker}", params=params)
                if isinstance(response, dict):
                    candles = response.get("ohlc", [])
                elif isinstance(response, list):
                    candles = response
                else:
                    candles = []
            except Exception as e:
                log.error("Failed to fetch OHLC for {}/{}: {}", ticker, interval, e)
                raise ForecastingAPIError(f"Failed to fetch OHLC data: {e}")

        normalised = [
            record
            for record in (self._normalise_ohlc_entry(item) for item in candles)
            if record
        ]

        if not normalised:
            log.debug(
                "Unable to normalise OHLC data for %s/%s (received %d raw items)",
                ticker,
                interval,
                len(candles),
            )

        self._set_cache(cache_key, normalised, timedelta(minutes=2))
        return normalised
    
    async def get_market_sentiment(self) -> Dict[str, Any]:
        """Get overall market sentiment."""
        cache_key = "market_sentiment"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if self.is_mock:
            result = {
                "overall_sentiment": "bullish",
                "sentiment_score": 0.65,
                "fear_greed_index": 72,
                "market_trend": "upward",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            try:
                response = await self._make_request("GET", "/api/news/market-sentiment")
                result = response
            except Exception as e:
                log.error(f"Failed to get market sentiment: {e}")
                # Return neutral sentiment as fallback
                result = {
                    "overall_sentiment": "neutral",
                    "sentiment_score": 0.5,
                    "fear_greed_index": 50,
                    "market_trend": "sideways",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
        
        self._set_cache(cache_key, result, timedelta(minutes=15))  # Cache for 15 minutes
        return result
    
    async def get_trend_analysis(self, ticker: str, interval: str) -> Dict[str, Any]:
        """
        Get trend analysis with %change variations relative to REAL T0 price (actual current market price).
        
        **KEY APPROACH**: Uses REAL T0 price as base (0% change), all forecasted variations (T+1 to T+14) 
        are calculated relative to this real baseline. This avoids bias by anchoring all forecasts to the same real price.
        
        Uses T+1 to T+14 as the forecast window (forecasted data only, shown in CSV).
        T-N (historical forecasts) are also part of the forecast series and calculated relative to real T0,
        but they are not shown in the CSV to reduce data size.
        
        Returns data in CSV format: ticker,T+1,T+2,...,T+14\nBTC-USD,+2%,+3%,+4%,...
        This reduces data size by ~50% and makes variations immediately understandable.
        
        **IMPORTANT**: 
        - Base price (T0) is REAL (actual current market price) - not forecasted, not shown in CSV
        - All variations (T+1 to T+14) are FORECASTED relative to real T0: `(forecasted_price - real_T0_price) / real_T0_price * 100`
        - T-N (historical forecasts) are also forecasted series, all calculated relative to real T0, but not shown in CSV
        - Only the trend matters - small decalage between real and forecast T0 is acceptable (forecasted_serie - realT0_price)
        
        Args:
            ticker: Trading pair symbol (e.g., "BTC-USD")
            interval: Time interval ("minutes", "thirty", "hours", "days")
            
        Returns:
            Dict containing:
            - real_t0_price: The actual current market price (REAL, not forecasted)
            - base_t_delta: T-delta of base (always 0.0 for real T0)
            - trend_direction: "bullish", "bearish", or "sideways"
            - trend_magnitude: "strong", "moderate", or "weak"
            - csv_format: CSV string with variations (ticker,T+1,T+2,...,T+14\nBTC-USD,+2%,+3%,...)
            - csv_rows: List of dicts with T-delta and %change for easier parsing (T+1 to T+14 only)
            - t_plus_1_to_14_forecasts: List of forecasts from T+1 to T+14 with variations (relative to real T0)
            - summary: Human-readable trend summary
        """
        cache_key = f"trend_{ticker}_{interval}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if not self.is_mock and self._use_mcp_tools():
            try:
                response = await self._make_request(
                    "GET",
                    "/tools/get_trend_analysis",
                    params={"ticker": ticker, "interval": interval},
                )
                if isinstance(response, dict):
                    self._set_cache(cache_key, response, timedelta(minutes=5))
                    return response
            except Exception as e:
                log.warning(f"MCP trend analysis failed for {ticker}/{interval}: {e}")

        try:
            # Get forecast data - try API first, then Redis fallback
            forecast_result = None
            forecast_data = []
            
            try:
                forecast_result = await self.get_stock_forecast(ticker, interval)
                forecast_data = forecast_result.get("forecast_data", [])
            except ForecastingAPIError as api_error:
                # Try Redis fallback if API fails
                log.debug(f"API failed for {ticker}/{interval}, trying Redis fallback: {api_error}")
                try:
                    from core.clients.redis_client import RedisClient
                    redis_client = RedisClient()
                    await redis_client.connect()
                    
                    # Redis key format: forecast_{ticker}_{interval}
                    redis_key = f"forecast_{ticker}_{interval}"
                    forecast_data_str = await redis_client.get(redis_key)
                    
                    if forecast_data_str:
                        import json
                        try:
                            raw_data = json.loads(forecast_data_str) if isinstance(forecast_data_str, str) else forecast_data_str
                            
                            # Handle both list and dict formats
                            if isinstance(raw_data, dict):
                                forecast_data = raw_data.get("forecast_data", [])
                                if not forecast_data and "forecast" in raw_data:
                                    # Single forecast entry
                                    forecast_data = [raw_data]
                                # Also check for forecast_timeline format
                                if not forecast_data and "forecast_timeline" in raw_data:
                                    forecast_data = raw_data.get("forecast_timeline", [])
                            elif isinstance(raw_data, list):
                                forecast_data = raw_data
                            else:
                                forecast_data = []
                            
                            if forecast_data:
                                log.info(f"✅ Retrieved forecast data from Redis for {ticker}/{interval}: {len(forecast_data)} entries")
                            else:
                                log.debug(f"Redis data exists for {ticker}/{interval} but no valid forecast entries found")
                        except json.JSONDecodeError as json_err:
                            log.debug(f"Failed to parse Redis data for {ticker}/{interval}: {json_err}")
                            forecast_data = []
                    else:
                        log.debug(f"No forecast data in Redis for {ticker}/{interval}")
                except Exception as redis_error:
                    log.debug(f"Redis fallback failed for {ticker}/{interval}: {redis_error}")
                    # Re-raise original API error if Redis also fails
                    raise ForecastingAPIError(f"No forecast data available for {ticker}/{interval} (API and Redis both failed)")
            
            if not forecast_data or not isinstance(forecast_data, list):
                raise ForecastingAPIError(f"No forecast data available for {ticker}/{interval}")
            
            # Parse timestamps and calculate T-deltas
            now = datetime.now(timezone.utc)
            parsed_forecasts = []
            
            for entry in forecast_data:
                if not isinstance(entry, dict):
                    continue
                
                # Parse timestamp
                ts_raw = entry.get("timestamp") or entry.get("Date") or entry.get("date")
                if not ts_raw:
                    continue
                
                try:
                    if isinstance(ts_raw, str):
                        if "T" in ts_raw:
                            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        else:
                            ts = datetime.strptime(ts_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    else:
                        continue
                    
                    # Calculate T-delta (days from now)
                    delta_seconds = (ts - now).total_seconds()
                    t_delta = delta_seconds / 86400  # Keep as float for precision
                    
                    # Get forecast price (prefer forecast, fallback to price)
                    forecast_price = entry.get("forecast") or entry.get("forecasting") or entry.get("price")
                    if forecast_price is None:
                        continue
                    
                    try:
                        forecast_price = float(forecast_price)
                    except (TypeError, ValueError):
                        continue
                    
                    # Get actual price if available
                    actual_price = entry.get("close") or entry.get("actual_price")
                    if actual_price is not None:
                        try:
                            actual_price = float(actual_price)
                        except (TypeError, ValueError):
                            actual_price = None
                    else:
                        actual_price = None
                    
                    parsed_forecasts.append({
                        "T": t_delta,
                        "timestamp": ts.isoformat(),
                        "forecast_price": forecast_price,
                        "actual_price": actual_price,
                        "prediction_date": entry.get("pred_date") or entry.get("prediction_time"),
                        "raw_entry": entry
                    })
                except Exception as e:
                    log.debug(f"Failed to parse forecast entry: {e}")
                    continue
            
            if not parsed_forecasts:
                # Log as debug - this is expected for some tickers that don't have forecast data yet
                log.debug(f"No valid forecast data points for {ticker}/{interval} - data may not be available yet")
                raise ForecastingAPIError(f"No valid forecast data points for {ticker}/{interval}")
            
            # ✅ Find REAL T0 price (actual current market price) - not forecasted
            # Priority: 1) From action_recommendation (current_price is real), 2) actual_price from T0 forecast entry, 3) forecast_price from T0 as fallback
            real_t0_price = None
            
            # Try to get real T0 price from action_recommendation first (current_price is actual market price)
            try:
                action_result = await self.get_action_recommendation(ticker, interval)
                real_t0_price = action_result.get("current_price")
                if real_t0_price:
                    try:
                        real_t0_price = float(real_t0_price)
                        log.debug(f"Got real T0 price from action_recommendation: ${real_t0_price:,.2f}")
                    except (TypeError, ValueError):
                        real_t0_price = None
            except Exception as e:
                log.debug(f"Could not get real T0 price from action_recommendation: {e}")
            
            # If not available from action_recommendation, find T0 entry (closest to T=0) and use actual_price if available
            if real_t0_price is None:
                parsed_forecasts.sort(key=lambda x: abs(x["T"]))  # Sort by proximity to T=0
                t0_entry = parsed_forecasts[0]
                
                # Prefer actual_price if available (this is the real market price for T0), fallback to forecast_price
                real_t0_price = t0_entry.get("actual_price")
                if real_t0_price:
                    try:
                        real_t0_price = float(real_t0_price)
                        log.debug(f"Got real T0 price from T0 entry actual_price: ${real_t0_price:,.2f}")
                    except (TypeError, ValueError):
                        real_t0_price = None
                
                # Last resort: use forecast_price from T0 entry (if actual_price not available)
                # Note: This is still a forecast, but it's the closest to T=0, so small decalage is acceptable
                if real_t0_price is None:
                    real_t0_price = t0_entry.get("forecast_price")
                    if real_t0_price:
                        try:
                            real_t0_price = float(real_t0_price)
                            log.warning(f"Using forecast_price from T0 entry as real T0 price (actual_price not available): ${real_t0_price:,.2f}. Small decalage may exist.")
                        except (TypeError, ValueError):
                            real_t0_price = None
            
            if real_t0_price is None or real_t0_price <= 0:
                raise ForecastingAPIError(f"Could not determine real T0 price for {ticker}/{interval}. All methods failed.")
            
            log.info(f"Using real T0 price for {ticker}: ${real_t0_price:,.2f} (actual current market price)")
            
            # ✅ Calculate %change for all forecasted points relative to REAL T0 price
            # This avoids bias: all forecasts (T-N and T+1 to T+14) are compared to the same real baseline
            # T-N (historical forecasts) are also part of the forecast series, all relative to real T0
            forecasts_with_change = []
            for forecast in parsed_forecasts:
                forecast_price = forecast["forecast_price"]  # This is always forecasted (part of forecast series)
                
                # Calculate %change: ((forecasted_price - real_T0_price) / real_T0_price) * 100
                # This removes bias because we compare all forecasts to the same real baseline
                percent_change = ((forecast_price - real_t0_price) / real_t0_price) * 100.0
                
                # Determine change direction
                if abs(percent_change) < 0.1:  # Less than 0.1% is considered unchanged
                    direction = "unchanged"
                elif percent_change > 0:
                    direction = "up"
                else:
                    direction = "down"
                
                forecasts_with_change.append({
                    "T": forecast["T"],
                    "timestamp": forecast["timestamp"],
                    "forecast_price": forecast_price,  # Forecasted price (part of forecast series)
                    "actual_price": forecast.get("actual_price"),  # Real price if available (only for T0)
                    "percent_change": round(percent_change, 2),  # Variation relative to real T0
                    "direction": direction,
                    "prediction_date": forecast.get("prediction_date")
                })
            
            # ✅ FILTER: Show historical (T-6 to T-1) and future (T+1 to T+14) forecasted data in CSV
            # All variations are calculated relative to real T0 price to avoid bias
            # T-6 to T-1 (historical forecasts) show past trend context
            # T+1 to T+14 (future forecasts) show forecasted future
            # Note: T0 is forecasted (not real) but very close to real T0, small diff explains forecasted - real_T0
            historical_forecasts = [f for f in forecasts_with_change if -6 <= f["T"] <= -1]
            future_forecasts = [f for f in forecasts_with_change if 1 <= f["T"] <= 14]
            
            # Sort by T-delta for timeline view
            historical_forecasts.sort(key=lambda x: x["T"])
            future_forecasts.sort(key=lambda x: x["T"])
            
            # Determine overall trend direction and magnitude from T+1 to T+14 (future forecasts)
            # All variations are relative to real T0, so trend is unbiased
            if not future_forecasts:
                trend_direction = "sideways"
                trend_magnitude = "weak"
                avg_change = 0.0
                all_changes = []
            else:
                all_changes = [f["percent_change"] for f in future_forecasts]
                avg_change = sum(all_changes) / len(all_changes)
                max_change = max(all_changes)
                min_change = min(all_changes)
                
                # Determine direction based on average change
                if abs(avg_change) < 1.0:  # Less than 1% average change
                    trend_direction = "sideways"
                elif avg_change > 0:
                    trend_direction = "bullish"
                else:
                    trend_direction = "bearish"
                
                # Determine magnitude based on absolute change range
                change_range = abs(max_change - min_change)
                if change_range >= 5.0:  # Strong trend: >5% variation
                    trend_magnitude = "strong"
                elif change_range >= 2.0:  # Moderate trend: 2-5% variation
                    trend_magnitude = "moderate"
                else:  # Weak trend: <2% variation
                    trend_magnitude = "weak"
            
            # ✅ Generate CSV format: ticker,T-6,T-5,...,T-1,T+1,T+2,...,T+14
            # Format: BTC-USD,-0.5%,-0.3%,...,+0.2%,+2%,+3%,+4%,... (historical + future, relative to real T0)
            # Note: T0 column is omitted (it's 0% by definition relative to real T0, but T0 is forecasted - real_T0 explains small diff)
            csv_header_parts = ["ticker"]
            csv_row_parts = [ticker]  # Keep ticker as-is (e.g., "BTC-USD")
            
            # Build T-delta columns: T-6, T-5, ..., T-1, T+1, T+2, ..., T+14
            # First historical (T-6 to T-1), then future (T+1 to T+14)
            all_t_deltas = list(range(-6, 0)) + list(range(1, 15))  # T-6 to T-1, then T+1 to T+14
            all_forecasts = historical_forecasts + future_forecasts
            
            for t_delta in all_t_deltas:
                csv_header_parts.append(f"T{t_delta:+d}")  # T-6, T-5, ..., T-1, T+1, T+2, ..., T+14
                
                # Find forecast for this T-delta
                forecast_for_t = next((f for f in all_forecasts if abs(f["T"] - t_delta) < 0.5), None)
                if forecast_for_t:
                    percent_change = forecast_for_t["percent_change"]
                    # Format as: +2%, -1%, 0%, +2.5%, -1.2%
                    # Use integer format for whole numbers, decimal for fractional
                    if abs(percent_change) < 0.05:  # Less than 0.05% rounds to 0%
                        csv_row_parts.append("0%")
                    elif abs(percent_change % 1.0) < 0.01:  # Whole number (within 0.01% of integer)
                        # Format as: +2%, -1%
                        csv_row_parts.append(f"{int(round(percent_change)):+d}%")
                    else:  # Fractional number
                        # Format as: +2.5%, -1.2%
                        if percent_change > 0:
                            csv_row_parts.append(f"+{percent_change:.1f}%")
                        else:
                            csv_row_parts.append(f"{percent_change:.1f}%")  # Already includes minus
                else:
                    csv_row_parts.append("N/A")
            
            csv_format = ",".join(csv_header_parts) + "\n" + ",".join(csv_row_parts)
            
            # Create CSV rows as list of dicts for easier parsing (T-6 to T-1, T+1 to T+14)
            csv_rows = []
            for f in all_forecasts:
                csv_rows.append({
                    "T": f["T"],
                    "percent_change": f["percent_change"],  # Variation relative to real T0
                    "direction": f["direction"],
                    "timestamp": f["timestamp"]
                })
            csv_rows.sort(key=lambda x: x["T"])
            
            # Calculate T0 forecasted price difference (forecasted T0 - real T0) for context
            t0_forecast = next((f for f in forecasts_with_change if abs(f["T"]) < 0.5), None)
            t0_diff_pct = 0.0
            if t0_forecast:
                t0_diff_pct = abs(t0_forecast["percent_change"])  # This is the diff between forecasted T0 and real T0
            
            # Create human-readable summary
            if trend_direction == "bullish":
                direction_emoji = "📈"
                direction_desc = f"FORECASTED to rise by {abs(avg_change):.2f}% on average over T+1 to T+14 (relative to real T0: ${real_t0_price:,.2f})"
            elif trend_direction == "bearish":
                direction_emoji = "📉"
                direction_desc = f"FORECASTED to fall by {abs(avg_change):.2f}% on average over T+1 to T+14 (relative to real T0: ${real_t0_price:,.2f})"
            else:
                direction_emoji = "➡️"
                direction_desc = f"FORECASTED to remain relatively stable over T+1 to T+14 (relative to real T0: ${real_t0_price:,.2f})"
            
            # Note about T0: forecasted T0 is very close to real T0, small diff (forecasted - real_T0) explains why T0 column is omitted
            t0_note = f" **Note**: T0 column is omitted (it's 0% by definition relative to real T0). T0 is forecasted (not real) but very close: forecasted_T0 - real_T0 = {t0_diff_pct:.2f}% diff. Historical (T-6 to T-1) shows past trend context."
            
            summary = (
                f"{direction_emoji} {trend_direction.upper()} trend ({trend_magnitude}): "
                f"{ticker} is {direction_desc}. "
                f"**Real T0 price**: ${real_t0_price:,.2f} (actual current market price). "
                f"All forecasted variations (T-6 to T-1: past trend, T+1 to T+14: future forecast) are calculated relative to this real baseline to avoid bias.{t0_note}"
            )
            
            # Find T+1 forecast for quick reference
            t_plus_1_forecast = next((f for f in future_forecasts if 1 <= f["T"] < 2), None)
            if not t_plus_1_forecast and future_forecasts:
                # Use first forecast in T+1 to T+14 range
                t_plus_1_forecast = future_forecasts[0]
            
            result = {
                "ticker": ticker,
                "interval": interval,
                "real_t0_price": real_t0_price,  # ✅ REAL T0 price (actual current market price)
                "base_t_delta": 0.0,  # T0 (real, not forecasted)
                "trend_direction": trend_direction,
                "trend_magnitude": trend_magnitude,
                "average_change_percent": round(avg_change, 2),
                "csv_format": csv_format,  # ✅ CSV format: ticker,T-6,T-5,...,T-1,T+1,T+2,...,T+14\nBTC-USD,-0.5%,...,+2%,+3%,...
                "csv_rows": csv_rows,  # List of dicts for easier parsing (T-6 to T-1, T+1 to T+14)
                "t_minus_6_to_minus_1_forecasts": historical_forecasts,  # ✅ T-6 to T-1 (historical, past trend context)
                "t_plus_1_to_14_forecasts": future_forecasts,  # ✅ T+1 to T+14 (future forecasts, relative to real T0)
                "all_forecasted_variations": forecasts_with_change,  # All forecasted points (T-N, T+1 to T+14) relative to real T0
                "t_plus_1_forecast": t_plus_1_forecast,
                "t0_forecast_diff_pct": t0_diff_pct,  # T0 forecasted - real T0 difference percentage
                "summary": summary,
                "data_type": "FORECASTED_VARIATIONS_RELATIVE_TO_REAL_T0",  # ✅ Explicitly mark
                "forecast_window": "T-6 to T-1 (past trend), T+1 to T+14 (future forecast)",  # ✅ Forecast window shown in CSV
                "base_type": "REAL_T0_PRICE",  # ✅ Base is real, not forecasted
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Cache for 2 minutes (same as stock forecast)
            self._set_cache(cache_key, result, timedelta(minutes=2))
            return result
            
        except ForecastingAPIError:
            raise
        except Exception as e:
            log.error(f"Failed to get trend analysis for {ticker}/{interval}: {e}")
            raise ForecastingAPIError(f"Failed to get trend analysis: {e}")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get API health status."""
        try:
            if self.is_mock:
                return {
                    "status": "healthy",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "version": "1.0.0",
                    "uptime": "99.9%"
                }
            
            response = await self._make_request("GET", "/health")
            return response
            
        except Exception as e:
            log.error(f"Failed to get health status: {e}")
            return {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }

    async def get_wallet_distribution(
        self,
        strategy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch wallet distribution from the API endpoint.

        Uses the endpoint: /api/agentic/wallet-distribution
        Example: GET /api/agentic/wallet-distribution?strategy=trading
        """
        cache_key = f"wallet_distribution_{strategy or 'all'}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if self.is_mock:
            # Return mock wallet distribution
            result = {
                "strategies": {
                    "trading": {
                        "wallet_distribution": {"BTC": 0.25, "ETH": 0.20},
                        "reserve_pct": 0.10,
                        "buy_signals": [],
                        "sell_signals": [],
                        "ai_explanation": "Mock trading strategy distribution",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "strategy": "trading",
                        "total_allocated": 0.90,
                    }
                },
                "daily": {},
                "hourly": {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            try:
                params = {}
                if strategy:
                    params["strategy"] = strategy
                response = await self._make_request(
                    "GET",
                    "/api/agentic/wallet-distribution",
                    params=params,
                )
                result = response
            except Exception as e:
                log.error(f"Failed to get wallet distribution: {e}")
                raise ForecastingAPIError(f"Failed to get wallet distribution: {e}")

        # Cache for 10 minutes
        self._set_cache(cache_key, result, timedelta(minutes=10))
        return result

    async def get_agentic_wallet_distribution(
        self, strategy: str = "trading", interval: str = "daily"
    ) -> Dict[str, Any]:
        """
        Fetch agentic wallet distribution with filtering.

        Uses the endpoint: /api/agentic/wallet-distribution?strategy={strategy}
        """
        cache_key = f"agentic_wallet_{strategy}_{interval}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            full_response = await self.get_wallet_distribution(strategy)
            if isinstance(full_response, dict):
                strategies = full_response.get("strategies", {})
                if strategy in strategies:
                    result = strategies[strategy]
                else:
                    result = next(iter(strategies.values())) if strategies else {
                        "strategy": strategy,
                        "wallet_distribution": {},
                        "reserve_pct": 0.10,
                        "buy_signals": [],
                        "sell_signals": [],
                        "ai_explanation": "No data available",
                        "total_allocated": 0.0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
            else:
                result = full_response

            if "timestamp" not in result:
                result["timestamp"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            log.error(f"Failed to get agentic wallet distribution: {e}")
            raise ForecastingAPIError(f"Failed to get agentic wallet distribution: {e}")

        self._set_cache(cache_key, result, timedelta(minutes=10))
        return result
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache.clear()
        self.cache_ttl.clear()
        log.info("Forecasting API cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_size": len(self.cache),
            "cached_keys": list(self.cache.keys()),
            "cache_ttl_entries": len(self.cache_ttl)
        }


# Global forecasting client instance
from core.settings.config import settings

forecasting_client = ForecastingClient({
    "base_url": settings.mcp_api_url,
    "api_key": settings.mcp_api_key,
    "mock_mode": settings.use_mock_services,
    "timeout": 30.0,
    "retry_attempts": 3,
    "retry_delay": 1.0
})
