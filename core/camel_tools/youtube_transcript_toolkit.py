"""
YouTube Transcript MCP Toolkit for CAMEL Agents.

Provides tools for extracting and searching YouTube video transcripts via MCP.
Uses proper CAMEL toolkit patterns with BaseToolkit and FunctionTool.
"""
from typing import Dict, Any, List, Optional
from core.logging import log
from core.config import settings
from core.clients.youtube_transcript_client import YouTubeTranscriptMCPClient, YouTubeTranscriptMCPError

try:
    from camel.toolkits.base import BaseToolkit
    from camel.toolkits.function_tool import FunctionTool
    from camel.logger import get_logger
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    BaseToolkit = object  # type: ignore
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False

logger = get_logger(__name__)


# Global toolkit instance for backward compatibility
_toolkit_instance: Optional["YouTubeTranscriptMCPToolkit"] = None


def get_youtube_transcript_toolkit() -> "YouTubeTranscriptMCPToolkit":
    """Get or create the global YouTube Transcript toolkit instance."""
    global _toolkit_instance
    if _toolkit_instance is None:
        _toolkit_instance = YouTubeTranscriptMCPToolkit()
    return _toolkit_instance


class YouTubeTranscriptMCPToolkit(BaseToolkit):
    r"""A toolkit for interacting with YouTube Transcript MCP to extract and search video transcripts.
    
    Provides tools for:
    - Extracting full video transcripts
    - Searching transcripts for keywords
    - Getting video metadata
    """
    
    def __init__(self, timeout: Optional[float] = None):
        r"""Initializes the YouTubeTranscriptMCPToolkit and sets up the YouTube Transcript client.
        
        Args:
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        config = {
            "command": settings.youtube_transcript_mcp_command,
            "args": settings.youtube_transcript_mcp_args,
            "timeout": 60.0,  # Longer timeout for transcript extraction
            "retry_attempts": 3
        }
        self.youtube_client = YouTubeTranscriptMCPClient(config)
        self._initialized = False
    
    async def initialize(self):
        """Initialize the YouTube Transcript client connection."""
        if not self._initialized:
            # Mark as initialized (actual test would require a valid video ID)
            self._initialized = True
            log.info("YouTube Transcript MCP toolkit initialized")
    
    def get_transcript_tool(self):
        """Get tool for extracting video transcripts."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_video_transcript(
            url: str,
            lang: Optional[str] = "en",
            enable_paragraphs: Optional[bool] = False
        ) -> Dict[str, Any]:
            """
            Get full transcript for a YouTube video.
            
            Extracts the complete transcript text along with timestamps for each segment.
            Useful for analyzing video content, speeches, interviews, and educational content,
            especially for financial news, market analysis, and crypto discussions.
            
            Args:
                url: YouTube video URL or ID (e.g., "https://www.youtube.com/watch?v=VIDEO_ID" or just "VIDEO_ID")
                lang: Language code (e.g., "en", "es"). Default: "en"
                enable_paragraphs: Enable automatic paragraph breaks in transcript. Default: False
            """
            await toolkit_instance.initialize()
            try:
                # MCP server expects 'url' parameter and 'lang' (not 'language')
                result = await toolkit_instance.youtube_client.get_transcript(url, lang)
                
                transcript_text = result.get("transcript", "")
                segments = result.get("segments", [])
                metadata = result.get("metadata", {})
                
                return {
                    "success": True,
                    "video_id": metadata.get("videoId", url),
                    "title": result.get("title", metadata.get("title", "Unknown")),
                    "transcript": transcript_text,
                    "language": result.get("language", lang),
                    "segments": segments,
                    "duration": result.get("duration", metadata.get("totalDuration", 0.0)),
                    "word_count": len(transcript_text.split()) if transcript_text else 0,
                    "char_count": metadata.get("charCount", len(transcript_text))
                }
            except YouTubeTranscriptMCPError as e:
                log.error(f"YouTube Transcript MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "video_id": url,
                    "transcript": "",
                    "segments": [],
                    "word_count": 0
                }
            except Exception as e:
                log.error(f"Error getting transcript for video {url}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "video_id": url,
                    "transcript": "",
                    "segments": [],
                    "word_count": 0
                }
        
        get_video_transcript.__name__ = "get_video_transcript"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_video_transcript)
        
        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # url is required (no default), lang and enable_paragraphs are optional (have defaults)
        schema = {
            "type": "function",
            "function": {
                "name": get_video_transcript.__name__,
                "description": get_video_transcript.__doc__ or "Get full transcript for a YouTube video",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "YouTube video URL or ID (e.g., 'https://www.youtube.com/watch?v=VIDEO_ID' or just 'VIDEO_ID')"
                        },
                        "lang": {
                            "type": "string",
                            "description": "Language code (e.g., 'en', 'es'). Defaults to 'en' if not specified."
                        },
                        "enable_paragraphs": {
                            "type": "boolean",
                            "description": "Whether to enable automatic paragraph breaks in the transcript. Defaults to False if not specified."
                        }
                    },
                    "required": ["url"],  # Only url is required, lang and enable_paragraphs have defaults
                    "additionalProperties": False
                }
            }
        }
        
        # Override the auto-generated schema to ensure compliance
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema

        schema["function"]["name"] = get_video_transcript.__name__
        tool.openai_tool_schema = schema
        return tool
    
    def get_search_transcript_tool(self):
        """Get tool for searching transcripts."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def search_video_transcript(
            url: str,
            query: str,
            lang: Optional[str] = "en"
        ) -> Dict[str, Any]:
            """
            Search for keywords in a YouTube video transcript.
            
            Finds all segments containing the search query and returns them with
            timestamps and surrounding context. Useful for finding specific topics
            or discussions in financial/crypto videos.
            
            Args:
                url: YouTube video URL or ID
                query: Search query/keywords to find
                lang: Language code. Default: "en"
            """
            await toolkit_instance.initialize()
            try:
                segments = await toolkit_instance.youtube_client.search_transcript(url, query, lang)
                return {
                    "success": True,
                    "video_id": url,
                    "query": query,
                    "matches": segments,
                    "count": len(segments)
                }
            except YouTubeTranscriptMCPError as e:
                log.error(f"YouTube Transcript MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "video_id": url,
                    "query": query,
                    "matches": [],
                    "count": 0
                }
            except Exception as e:
                log.error(f"Error searching transcript for video {url}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "video_id": url,
                    "query": query,
                    "matches": [],
                    "count": 0
                }
        
        search_video_transcript.__name__ = "search_video_transcript"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(search_video_transcript)
        
        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # url and query are required (no defaults), lang is optional (has default)
        schema = {
            "type": "function",
            "function": {
                "name": search_video_transcript.__name__,
                "description": search_video_transcript.__doc__ or "Search for keywords in a YouTube video transcript",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "YouTube video URL or ID"
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query/keywords to find in transcript"
                        },
                        "lang": {
                            "type": "string",
                            "description": "Language code (e.g., 'en', 'es'). Defaults to 'en' if not specified."
                        }
                    },
                    "required": ["url", "query"],  # Only url and query are required, lang has default
                    "additionalProperties": False
                }
            }
        }
        
        # Override the auto-generated schema to ensure compliance
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
        return tool
    
    def get_video_info_tool(self):
        """Get tool for getting video metadata."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit_instance = self
        
        async def get_video_metadata(
            url: str
        ) -> Dict[str, Any]:
            """
            Get metadata for a YouTube video.
            
            Retrieves video information including title, description, channel,
            duration, view count, and publication date.
            
            Args:
                url: YouTube video URL or ID
            """
            await toolkit_instance.initialize()
            try:
                result = await toolkit_instance.youtube_client.get_video_info(url)
                return {
                    "success": True,
                    "video_id": result.get("video_id", url),
                    "title": result.get("title", "Unknown"),
                    "language": result.get("language", "en"),
                    "duration": result.get("duration", 0.0),
                    "transcript_count": result.get("transcript_count", 0),
                    "char_count": result.get("char_count", 0)
                }
            except YouTubeTranscriptMCPError as e:
                log.error(f"YouTube Transcript MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "video_id": url
                }
            except Exception as e:
                log.error(f"Error getting video info for {url}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "video_id": url
                }
        
        get_video_metadata.__name__ = "get_video_metadata"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(get_video_metadata)
        
        # ✅ CRITICAL: Always use explicit schema override to ensure OpenAI compliance
        # url is required (no default)
        schema = {
            "type": "function",
            "function": {
                "name": get_video_metadata.__name__,
                "description": get_video_metadata.__doc__ or "Get metadata for a YouTube video",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "YouTube video URL or ID"
                        }
                    },
                    "required": ["url"],  # url is required (no default)
                    "additionalProperties": False
                }
            }
        }
        
        # Override the auto-generated schema to ensure compliance
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema
        
        return tool
    
    def get_tools(self) -> List[FunctionTool]:
        r"""Returns a list of FunctionTool objects representing the
        functions in the toolkit.

        Returns:
            List[FunctionTool]: A list of FunctionTool objects
                representing the functions in the toolkit.
        """
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            logger.warning("CAMEL tools not available, returning empty list")
            return []
        
        return [
            self.get_transcript_tool(),
            self.get_search_transcript_tool(),
            self.get_video_info_tool(),
        ]
    
    def get_all_tools(self) -> List[FunctionTool]:
        """Alias for get_tools() for backward compatibility."""
        return self.get_tools()


__all__ = ["YouTubeTranscriptMCPToolkit", "get_youtube_transcript_toolkit"]
