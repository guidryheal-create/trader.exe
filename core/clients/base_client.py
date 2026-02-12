"""
Base Client Classes

Base classes for MCP and HTTP clients with common patterns for initialization,
retry logic, error handling, and caching.
"""

import asyncio
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
import httpx
from core.logging import log


class BaseHTTPClient(ABC):
    """
    Base class for HTTP-based API clients.
    
    Provides common functionality:
    - HTTP client management
    - Retry logic
    - Error handling
    - Request timeout management
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize base HTTP client.
        
        Args:
            config: Configuration dict with:
                - base_url: Base URL for API
                - timeout: Request timeout in seconds (default: 30.0)
                - retry_attempts: Number of retry attempts (default: 3)
                - retry_delay: Delay between retries in seconds (default: 1.0)
        """
        config = config or {}
        self.base_url = config.get("base_url", "").rstrip("/")
        self.timeout = config.get("timeout", 30.0)
        self.retry_attempts = config.get("retry_attempts", 3)
        self.retry_delay = config.get("retry_delay", 1.0)
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop_id: Optional[int] = None
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """
        Ensure HTTP client is initialized and bound to current event loop.
        
        Returns:
            httpx.AsyncClient instance
        """
        current_loop_id = id(asyncio.get_event_loop())
        
        if self._client is None or self._client_loop_id != current_loop_id:
            if self._client is not None:
                await self._client.aclose()
            
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
            self._client_loop_id = current_loop_id
        
        return self._client
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments for httpx request
            
        Returns:
            httpx.Response
            
        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        client = await self._ensure_client()
        last_error = None
        
        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.RemoteProtocolError, 
                    httpx.ConnectError, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.retry_attempts:
                    log.warning(
                        f"Request failed (attempt {attempt}/{self.retry_attempts}): {e}. "
                        f"Retrying in {self.retry_delay}s..."
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    log.error(f"Request failed after {self.retry_attempts} attempts: {e}")
                    raise
        
        if last_error:
            raise last_error
    
    async def close(self):
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._client_loop_id = None


class BaseMCPClient(ABC):
    """
    Base class for MCP (Model Context Protocol) clients.
    
    Provides common functionality:
    - MCP command execution
    - Retry logic
    - Error handling
    - Process management
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize base MCP client.
        
        Args:
            config: Configuration dict with:
                - command: MCP command (e.g., "uvx")
                - args: MCP command arguments
                - timeout: Request timeout in seconds (default: 30)
                - retry_attempts: Number of retry attempts (default: 3)
        """
        config = config or {}
        self.command = config.get("command", "uvx")
        self.args = config.get("args", [])
        self.timeout = config.get("timeout", 30)
        self.retry_attempts = config.get("retry_attempts", 3)
        self._process: Optional[Any] = None
    
    async def _execute_mcp_command(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute MCP command with retry logic.
        
        Args:
            tool_name: MCP tool name to execute
            arguments: Arguments for the tool
            timeout: Optional timeout override
            
        Returns:
            Response dictionary from MCP server
            
        Raises:
            Exception: If command fails after all retries
        """
        timeout = timeout or self.timeout
        last_error = None
        
        for attempt in range(1, self.retry_attempts + 1):
            try:
                # This is a template - subclasses should implement actual MCP execution
                result = await self._run_mcp_tool(tool_name, arguments, timeout)
                return result
            except Exception as e:
                last_error = e
                if attempt < self.retry_attempts:
                    log.warning(
                        f"MCP command failed (attempt {attempt}/{self.retry_attempts}): {e}. "
                        f"Retrying..."
                    )
                    await asyncio.sleep(1.0)
                else:
                    log.error(f"MCP command failed after {self.retry_attempts} attempts: {e}")
                    raise
        
        if last_error:
            raise last_error
    
    @abstractmethod
    async def _run_mcp_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float
    ) -> Dict[str, Any]:
        """
        Execute MCP tool (to be implemented by subclasses).
        
        Args:
            tool_name: MCP tool name
            arguments: Tool arguments
            timeout: Request timeout
            
        Returns:
            Response dictionary
        """
        pass
    
    async def close(self):
        """Close MCP client and cleanup resources."""
        if self._process is not None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except Exception as e:
                log.warning(f"Error closing MCP process: {e}")
            self._process = None

