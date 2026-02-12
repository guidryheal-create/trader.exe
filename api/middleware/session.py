"""Session middleware and Redis-backed session store.

This middleware checks for a session token header `X-Session-Token` and attaches
session data to the request state as `request.state.session`.

If Redis is available (via `REDIS_URL` env var) it will be used; otherwise an
in-memory fallback store is used.
"""
from __future__ import annotations

import os
import json
from typing import Optional, Dict, Any

try:
    import redis
except Exception:
    redis = None

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REDIS_URL = os.getenv("REDIS_URL")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))  # 1 day default


class BaseStore:
    def set(self, key: str, data: Dict[str, Any]) -> None:
        raise NotImplementedError()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError()

    def delete(self, key: str) -> None:
        raise NotImplementedError()


class RedisStore(BaseStore):
    def __init__(self, url: str):
        if redis is None:
            raise RuntimeError("redis package not available")
        self.client = redis.from_url(url, decode_responses=True)

    def set(self, key: str, data: Dict[str, Any]) -> None:
        self.client.setex(key, SESSION_TTL_SECONDS, json.dumps(data))

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        raw = self.client.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def delete(self, key: str) -> None:
        self.client.delete(key)


class MemoryStore(BaseStore):
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def set(self, key: str, data: Dict[str, Any]) -> None:
        self._store[key] = data

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)

    def delete(self, key: str) -> None:
        if key in self._store:
            del self._store[key]


# Choose store based on REDIS_URL
if REDIS_URL and redis is not None:
    try:
        store: BaseStore = RedisStore(REDIS_URL)
    except Exception:
        store = MemoryStore()
else:
    store = MemoryStore()


def set_session(token: str, data: Dict[str, Any]) -> None:
    store.set(token, data)


def get_session(token: str) -> Optional[Dict[str, Any]]:
    return store.get(token)


def delete_session(token: str) -> None:
    store.delete(token)


class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Default no session
        request.state.session = None

        token = None
        # Prefer custom header
        token = request.headers.get("X-Session-Token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
        if not token:
            # Fallback to cookie named 'session_token'
            token = request.cookies.get("session_token")

        if token:
            try:
                session = get_session(token)
                if session:
                    request.state.session = session
            except Exception:
                # swallow errors to avoid breaking requests
                request.state.session = None

        response: Response = await call_next(request)
        return response
