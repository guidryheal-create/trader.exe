"""
Compatibility wrapper for the canonical YouTube transcript client.

This module re-exports the implementation from `core.clients.youtube_transcript_client`.
"""

from core.clients.youtube_transcript_client import *  # noqa: F401,F403
from core.clients.youtube_transcript_client import YouTubeTranscriptMCPClient, YouTubeTranscriptMCPError

__all__ = ["YouTubeTranscriptMCPClient", "YouTubeTranscriptMCPError"]
