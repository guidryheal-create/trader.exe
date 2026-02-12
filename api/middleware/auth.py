"""API Authentication & Rate Limiting Middleware"""

import os
import time
from typing import Dict, Optional
from fastapi import HTTPException, Request
from functools import lru_cache

# Get API key from environment
API_KEY = os.getenv("POLYMARKET_API_KEY", "")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

# In-memory rate limiter (use Redis in production)
_request_log: Dict[str, list] = {}


@lru_cache(maxsize=1)
def get_api_key() -> str:
    """Get API key, fallback to env var."""
    if not API_KEY:
        raise ValueError("POLYMARKET_API_KEY not set in environment")
    return API_KEY


def verify_api_key(api_key: Optional[str]) -> bool:
    """Verify API key matches configured key."""
    if not API_KEY:
        # No key configured - allow all (dev mode)
        return True
    return api_key == API_KEY


def check_rate_limit(client_id: str) -> bool:
    """Check if client has exceeded rate limit."""
    now = time.time()
    minute_ago = now - 60
    
    if client_id not in _request_log:
        _request_log[client_id] = []
    
    # Remove old requests
    _request_log[client_id] = [ts for ts in _request_log[client_id] if ts > minute_ago]
    
    # Check limit
    if len(_request_log[client_id]) >= RATE_LIMIT_PER_MINUTE:
        return False
    
    # Log this request
    _request_log[client_id].append(now)
    return True


async def verify_auth_header(request: Request) -> str:
    """Extract and verify API key from Authorization header.
    
    Returns:
        API key if valid
        
    Raises:
        HTTPException if not valid
    """
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )
    
    # Expected format: "Bearer <api_key>"
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected 'Bearer <api_key>'",
        )
    
    api_key = auth_header[7:]  # Remove "Bearer " prefix
    
    if not verify_api_key(api_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )
    
    return api_key


async def check_client_rate_limit(request: Request) -> None:
    """Check rate limit for client.
    
    Raises:
        HTTPException if rate limit exceeded
    """
    client_id = request.client.host if request.client else "unknown"
    
    if not check_rate_limit(client_id):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {RATE_LIMIT_PER_MINUTE} requests per minute",
        )
