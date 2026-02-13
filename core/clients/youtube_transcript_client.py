"""
YouTube Transcript MCP Client for video transcript extraction.

Provides access to YouTube video transcripts via MCP server using npx.
Reference: https://github.com/sinco-lab/mcp-youtube-transcript
"""
import asyncio
import json
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from core.logging import log
from core.settings.config import settings


class YouTubeTranscriptMCPError(Exception):
    """Base exception for YouTube Transcript MCP operations."""
    pass


class YouTubeTranscriptMCPClient:
    """
    Client for interacting with YouTube Transcript MCP server.
    
    Supports:
    - Extracting video transcripts
    - Searching transcripts for keywords
    - Getting video metadata
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize YouTube Transcript MCP client.
        
        Args:
            config: Optional configuration dict with:
                - command: MCP command (default: npx)
                - args: MCP command arguments (default: ["-y", "@sinco-lab/mcp-youtube-transcript"])
                - timeout: Request timeout in seconds (default: 60)
                - retry_attempts: Number of retry attempts (default: 3)
        """
        config = config or {}
        self.command = config.get(
            "command",
            getattr(settings, "youtube_transcript_mcp_command", "npx")
        )
        args_raw = config.get(
            "args",
            getattr(settings, "youtube_transcript_mcp_args", '["-y", "@sinco-lab/mcp-youtube-transcript"]')
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
            self.args = ["-y", "@sinco-lab/mcp-youtube-transcript"]
        
        self.timeout = config.get("timeout", 60.0)  # Longer timeout for transcript extraction
        self.retry_attempts = config.get("retry_attempts", 3)
        self.retry_delay = config.get("retry_delay", 1.0)
        
        # Cache for frequently accessed data
        self.cache: Dict[str, Any] = {}
        self.cache_ttl: Dict[str, datetime] = {}
        self.default_cache_ttl = timedelta(hours=24)  # Transcripts don't change
    
    async def _invoke_mcp_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Invoke an MCP tool via STDIO subprocess.
        
        MCP servers communicate via JSON-RPC over STDIO. This method:
        1. Spawns the MCP server process
        2. Sends initialize request
        3. Sends tools/list request to discover tools
        4. Sends tools/call request with tool name and arguments
        5. Parses and returns the result
        
        Args:
            tool_name: Name of the MCP tool to invoke
            arguments: Tool arguments
            
        Returns:
            Tool response as dictionary
        """
        import json
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
                    raise YouTubeTranscriptMCPError(f"MCP process failed: {error_msg}")
                
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
                                    
                                    raise YouTubeTranscriptMCPError(f"MCP error: {error_data}")
                                
                                call_result = response.get("result", {})
                                
                        except json.JSONDecodeError:
                            continue
                
                if call_result is None:
                    raise YouTubeTranscriptMCPError(f"No valid response from MCP server. Available tools: {available_tools}")
                
                # Cache the response
                self.cache[cache_key] = call_result
                self.cache_ttl[cache_key] = datetime.now() + self.default_cache_ttl
                
                return call_result
                
            except asyncio.TimeoutError:
                if attempt < self.retry_attempts - 1:
                    log.warning(f"MCP timeout (attempt {attempt + 1}/{self.retry_attempts})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise YouTubeTranscriptMCPError(f"Request timeout after {self.timeout}s")
            except Exception as e:
                if attempt < self.retry_attempts - 1:
                    log.warning(f"MCP error (attempt {attempt + 1}/{self.retry_attempts}): {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise YouTubeTranscriptMCPError(f"Request failed: {e}")
            finally:
                # Clean up process
                if process and process.returncode is None:
                    try:
                        process.kill()
                        await process.wait()
                    except:
                        pass
        
        raise YouTubeTranscriptMCPError(f"Failed after {self.retry_attempts} attempts")
    
    async def get_transcript(
        self,
        video_id: str,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get transcript for a YouTube video.
        
        Args:
            video_id: YouTube video ID (from URL: https://www.youtube.com/watch?v=VIDEO_ID)
            language: Optional language code (e.g., "en", "es"). If None, uses auto-detect
            
        Returns:
            Transcript information including:
                - transcript: Full transcript text
                - language: Detected language
                - segments: List of transcript segments with timestamps
                - duration: Video duration in seconds
        """
        try:
            # MCP server expects 'url' parameter (can be video ID or URL)
            arguments = {"url": video_id}
            if language:
                arguments["lang"] = language  # MCP server uses 'lang' not 'language'
            
            # Try common YouTube Transcript MCP tool names
            # Note: Actual tool names depend on the MCP server implementation
            # The MCP server provides: get_transcripts (plural)
            tool_names = ["get_transcripts", "get_transcript", "youtube_get_transcript", "transcript", "youtube_transcript_get"]
            result = None
            last_error = None
            
            for tool_name in tool_names:
                try:
                    result = await self._invoke_mcp_tool(tool_name, arguments)
                    if result:
                        log.debug(f"Successfully used tool '{tool_name}' for transcript")
                        break
                except YouTubeTranscriptMCPError as e:
                    last_error = e
                    log.debug(f"Tool '{tool_name}' failed: {e}")
                    continue
            
            if result is None:
                raise last_error or YouTubeTranscriptMCPError("Failed to get transcript: tool not found. Check MCP server tool names.")
            
            # Parse MCP server response format
            # The server returns content array with text and metadata
            content = result.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text_content = content[0].get("text", "")
                metadata = content[0].get("metadata", {})
                
                # Extract title from text (format: "# Title\n\nTranscript...")
                title = metadata.get("title", "Unknown")
                if text_content.startswith("# "):
                    lines = text_content.split("\n", 2)
                    if len(lines) >= 2:
                        title = lines[0].replace("# ", "").strip()
                        transcript_text = lines[2] if len(lines) > 2 else ""
                    else:
                        transcript_text = text_content
                else:
                    transcript_text = text_content
                
                # Build segments from metadata if available
                segments = []
                transcript_count = metadata.get("transcriptCount", 0)
                if transcript_count > 0:
                    # Note: Full segment data would need to be parsed from the original XML
                    # For now, we return the text and basic metadata
                    segments = [{
                        "text": transcript_text,
                        "timestamp": 0,
                        "duration": metadata.get("totalDuration", 0)
                    }]
                
                return {
                    "transcript": transcript_text,
                    "title": title,
                    "language": metadata.get("language", language or "en"),
                    "segments": segments,
                    "duration": metadata.get("totalDuration", 0),
                    "metadata": metadata
                }
            
            # Fallback: return raw result
            return result
        except Exception as e:
            log.error(f"Error getting transcript for video {video_id}: {e}")
            raise YouTubeTranscriptMCPError(f"Failed to get transcript: {e}")
    
    async def search_transcript(
        self,
        video_id: str,
        query: str,
        language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for keywords in a video transcript.
        
        Note: The MCP server doesn't have a search function, so we get the full
        transcript and search locally for matching segments.
        
        Args:
            video_id: YouTube video ID
            query: Search query/keywords
            language: Optional language code
            
        Returns:
            List of matching segments with timestamps and context
        """
        try:
            # Get full transcript first
            transcript_result = await self.get_transcript(video_id, language)
            
            # Extract transcript text and segments from result
            transcript_text = transcript_result.get("transcript", "")
            segments = transcript_result.get("segments", [])
            
            if not segments and transcript_text:
                # If we only have text, create segments from it
                # This is a fallback - ideally segments should be in the result
                return [{"text": transcript_text, "query": query, "matches": []}]
            
            # Search for query in segments
            query_lower = query.lower()
            matches = []
            
            for segment in segments:
                segment_text = segment.get("text", "").lower()
                if query_lower in segment_text:
                    matches.append({
                        "text": segment.get("text", ""),
                        "start": segment.get("start", segment.get("timestamp", 0)),
                        "duration": segment.get("duration", 0),
                        "context": segment.get("text", "")
                    })
            
            return matches
        except Exception as e:
            log.error(f"Error searching transcript for video {video_id}: {e}")
            raise YouTubeTranscriptMCPError(f"Failed to search transcript: {e}")
    
    async def get_video_info(
        self,
        video_id: str
    ) -> Dict[str, Any]:
        """
        Get video metadata.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Video information including title, description, channel, duration, etc.
        """
        try:
            # The MCP server doesn't have a separate video_info tool
            # But get_transcripts returns metadata including title
            # So we'll get the transcript which includes video info
            try:
                result = await self.get_transcript(video_id)
                # Extract metadata from transcript result
                metadata = result.get("metadata", {})
                return {
                    "video_id": video_id,
                    "title": metadata.get("title", "Unknown"),
                    "language": metadata.get("language", "en"),
                    "duration": metadata.get("totalDuration", 0),
                    "transcript_count": metadata.get("transcriptCount", 0),
                    "char_count": metadata.get("charCount", 0)
                }
            except Exception as e:
                log.error(f"Error getting video info for {video_id}: {e}")
                raise YouTubeTranscriptMCPError(f"Failed to get video info: {e}")
        except Exception as e:
            log.error(f"Error getting video info for {video_id}: {e}")
            raise YouTubeTranscriptMCPError(f"Failed to get video info: {e}")

