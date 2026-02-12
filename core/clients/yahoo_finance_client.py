"""
Yahoo Finance MCP Client for financial news and data.

Provides access to Yahoo Finance data via MCP server using uvx.
Reference: https://github.com/modelcontextprotocol/servers/tree/main/src/yahoo-finance
"""
import asyncio
import json
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from core.logging import log
from core.config import settings


class YahooFinanceMCPError(Exception):
    """Base exception for Yahoo Finance MCP operations."""
    pass


class YahooFinanceMCPClient:
    """
    Client for interacting with Yahoo Finance MCP server.
    
    Supports querying:
    - Stock quotes and prices
    - Financial news and headlines
    - Market data and statistics
    - Company information
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Yahoo Finance MCP client.
        
        Args:
            config: Optional configuration dict with:
                - command: MCP command (default: uvx)
                - args: MCP command arguments (default: ["mcp-yahoo-finance"])
                - timeout: Request timeout in seconds (default: 30)
                - retry_attempts: Number of retry attempts (default: 3)
        """
        config = config or {}
        self.command = config.get(
            "command",
            getattr(settings, "yahoo_finance_mcp_command", "uvx")
        )
        args_raw = config.get(
            "args",
            getattr(settings, "yahoo_finance_mcp_args", '["mcp-yahoo-finance"]')
        )
        # Parse args from JSON string or list
        if isinstance(args_raw, str):
            import ast
            try:
                self.args = ast.literal_eval(args_raw)
            except (ValueError, SyntaxError):
                # If not JSON, treat as single string
                self.args = [args_raw]
        elif isinstance(args_raw, list):
            self.args = args_raw
        else:
            self.args = ["mcp-yahoo-finance"]
        
        self.timeout = config.get("timeout", 30.0)
        self.retry_attempts = config.get("retry_attempts", 3)
        self.retry_delay = config.get("retry_delay", 1.0)
        
        # Cache for frequently accessed data
        self.cache: Dict[str, Any] = {}
        self.cache_ttl: Dict[str, datetime] = {}
        self.default_cache_ttl = timedelta(minutes=5)
    
    async def _invoke_mcp_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Invoke an MCP tool via subprocess.
        
        Args:
            tool_name: Name of the MCP tool to invoke
            arguments: Tool arguments
            
        Returns:
            Tool response as dictionary
        """
        cache_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
        
        # Check cache
        if cache_key in self.cache:
            if datetime.now() < self.cache_ttl.get(cache_key, datetime.min):
                log.debug(f"Cache hit for {tool_name}")
                return self.cache[cache_key]
        
        for attempt in range(self.retry_attempts):
            process = None
            try:
                # Run MCP server via subprocess with persistent STDIO connection
                cmd = [self.command] + self.args
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # MCP initialization sequence
                # 1. Initialize
                init_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "agentic-trading-system",
                            "version": "1.0.0"
                        }
                    }
                }
                
                # 2. List tools
                list_tools_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
                
                # 3. Call tool
                call_tool_request = {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
                
                # Send all requests
                requests = [
                    json.dumps(init_request) + "\n",
                    json.dumps(list_tools_request) + "\n",
                    json.dumps(call_tool_request) + "\n"
                ]
                
                request_data = "".join(requests).encode()
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=request_data),
                    timeout=self.timeout
                )
                
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    if attempt < self.retry_attempts - 1:
                        log.warning(f"MCP error (attempt {attempt + 1}/{self.retry_attempts}): {error_msg}")
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                    raise YahooFinanceMCPError(f"MCP process failed: {error_msg}")
                
                # Parse responses (expect 3: init, list, call)
                response_lines = stdout.decode().strip().split("\n")
                available_tools = []
                call_result = None
                
                for line in response_lines:
                    if line.strip():
                        try:
                            response = json.loads(line)
                            response_id = response.get("id")
                            
                            # Handle tools/list response (id: 2)
                            if response_id == 2:
                                if "error" in response:
                                    log.warning(f"MCP tools/list error: {response['error']}")
                                else:
                                    tools_list = response.get("result", {}).get("tools", [])
                                    available_tools = [t.get("name") for t in tools_list if isinstance(t, dict)]
                                    log.debug(f"MCP available tools: {available_tools}")
                            
                            # Handle tools/call response (id: 3)
                            elif response_id == 3:
                                if "error" in response:
                                    error_data = response.get("error", {})
                                    error_code = error_data.get("code")
                                    error_msg = error_data.get("message", "")
                                    
                                    # If tool not found, log available tools
                                    if error_code == -32601 or "not found" in error_msg.lower():
                                        log.warning(f"Tool '{tool_name}' not found. Available tools: {available_tools}")
                                    
                                    raise YahooFinanceMCPError(f"MCP error: {error_data}")
                                
                                call_result = response.get("result", {})
                                
                        except json.JSONDecodeError:
                            continue
                
                if call_result is None:
                    raise YahooFinanceMCPError(f"No valid response from MCP server. Available tools: {available_tools}")
                
                # Cache the response
                self.cache[cache_key] = call_result
                self.cache_ttl[cache_key] = datetime.now() + self.default_cache_ttl
                
                return call_result
                
            except asyncio.TimeoutError:
                if attempt < self.retry_attempts - 1:
                    log.warning(f"MCP timeout (attempt {attempt + 1}/{self.retry_attempts})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise YahooFinanceMCPError(f"Request timeout after {self.timeout}s")
            except Exception as e:
                if attempt < self.retry_attempts - 1:
                    log.warning(f"MCP error (attempt {attempt + 1}/{self.retry_attempts}): {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise YahooFinanceMCPError(f"Request failed: {e}")
        
        raise YahooFinanceMCPError(f"Failed after {self.retry_attempts} attempts")
    
    async def get_quote(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """
        Get stock quote for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., "BTC-USD", "AAPL")
            
        Returns:
            Quote information including price, volume, market cap, etc.
        """
        try:
            # Try common Yahoo Finance MCP tool names
            # Note: Actual tool names depend on the MCP server implementation
            tool_names = ["yf_quote", "get_quote", "quote", "yahoo_finance_get_quote"]
            result = None
            last_error = None
            
            for tool_name in tool_names:
                try:
                    result = await self._invoke_mcp_tool(
                        tool_name,
                        {"symbol": symbol}
                    )
                    if result:
                        log.debug(f"Successfully used tool '{tool_name}' for quote")
                        break
                except YahooFinanceMCPError as e:
                    last_error = e
                    log.debug(f"Tool '{tool_name}' failed: {e}")
                    continue
            
            if result is None:
                raise last_error or YahooFinanceMCPError("Failed to get quote: tool not found. Check MCP server tool names.")
            
            return result
        except Exception as e:
            log.error(f"Error getting quote for {symbol}: {e}")
            raise YahooFinanceMCPError(f"Failed to get quote: {e}")
    
    async def search_news(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for financial news.
        
        Args:
            query: Search query (e.g., "Bitcoin", "crypto market")
            limit: Maximum number of results (default: 10)
            
        Returns:
            List of news articles with title, link, summary, etc.
        """
        try:
            # Try common Yahoo Finance MCP tool names
            tool_names = ["yf_news", "search_news", "news", "yahoo_finance_search_news"]
            result = None
            last_error = None
            
            for tool_name in tool_names:
                try:
                    result = await self._invoke_mcp_tool(
                        tool_name,
                        {
                            "query": query,
                            "limit": limit
                        }
                    )
                    if result:
                        log.debug(f"Successfully used tool '{tool_name}' for news search")
                        break
                except YahooFinanceMCPError as e:
                    last_error = e
                    log.debug(f"Tool '{tool_name}' failed: {e}")
                    continue
            
            if result is None:
                raise last_error or YahooFinanceMCPError("Failed to search news: tool not found. Check MCP server tool names.")
            
            articles = result.get("articles", result.get("content", []))
            return articles if isinstance(articles, list) else [articles] if articles else []
        except Exception as e:
            log.error(f"Error searching news for '{query}': {e}")
            raise YahooFinanceMCPError(f"Failed to search news: {e}")
    
    async def get_historical_data(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d"
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data.
        
        Args:
            symbol: Stock symbol
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            
        Returns:
            List of historical data points with date, open, high, low, close, volume
        """
        try:
            # Try common Yahoo Finance MCP tool names
            tool_names = ["yf_history", "get_historical", "historical", "yahoo_finance_get_historical"]
            result = None
            last_error = None
            
            for tool_name in tool_names:
                try:
                    result = await self._invoke_mcp_tool(
                        tool_name,
                        {
                            "symbol": symbol,
                            "period": period,
                            "interval": interval
                        }
                    )
                    if result:
                        log.debug(f"Successfully used tool '{tool_name}' for historical data")
                        break
                except YahooFinanceMCPError as e:
                    last_error = e
                    log.debug(f"Tool '{tool_name}' failed: {e}")
                    continue
            
            if result is None:
                raise last_error or YahooFinanceMCPError("Failed to get historical data: tool not found. Check MCP server tool names.")
            
            data = result.get("data", result.get("content", []))
            return data if isinstance(data, list) else [data] if data else []
        except Exception as e:
            log.error(f"Error getting historical data for {symbol}: {e}")
            raise YahooFinanceMCPError(f"Failed to get historical data: {e}")

