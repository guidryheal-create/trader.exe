#!/usr/bin/env python3
"""Clear test data from Redis."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.clients.redis_client import RedisClient
from core.logging import log

async def main():
    r = RedisClient()
    await r.connect()
    
    # Get all keys
    keys = []
    cursor = 0
    while True:
        cursor, batch = await r.redis.scan(cursor, match='response_format:wallet:*', count=100)
        keys.extend(batch)
        if cursor == 0:
            break
    
    cursor = 0
    while True:
        cursor, batch = await r.redis.scan(cursor, match='ai_decision:*', count=100)
        keys.extend(batch)
        if cursor == 0:
            break
    
    # Delete keys
    if keys:
        for k in keys:
            await r.redis.delete(k)
        log.info(f"✅ Cleared {len(keys)} keys from Redis")
    else:
        log.info("✅ No keys to clear")
    
    await r.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

