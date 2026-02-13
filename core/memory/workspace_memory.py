"""
Workspace Memory Module

Manages shared memory workspace for agent collaboration and context sharing.

Key features:
- Per-ticker workspace (isolated contexts)
- FIFO memory queue for each ticker
- Memory pruning on size limits
- Deterministic memory access patterns
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from core.logging import log
from core.clients.redis_client import RedisClient


class WorkspaceMemory:
    """
    Manages workspace memory for agent collaboration.
    
    Workspace memory stores:
    - Trend decisions and analysis
    - Fact insights and research
    - Memory records and patterns
    - Previous decisions and outcomes
    - Agent coordination state
    """

    # Key patterns
    MEMORY_KEY_PATTERN = "workspace:memory:{ticker}"
    CHAT_HISTORY_KEY_PATTERN = "workspace:chat:{ticker}"
    MEMORY_MAX_SIZE = 50  # Max records per ticker
    CHAT_HISTORY_MAX_SIZE = 2  # Max chat messages (1-2 conversation turns)
    MEMORY_TTL_SECONDS = 86400  # 24 hours

    def __init__(self, redis: RedisClient):
        self.redis = redis
        log.info("[WORKSPACE MEMORY] Initialized")

    async def write_record(
        self,
        ticker: str,
        record: Dict[str, Any],
        max_records: int = MEMORY_MAX_SIZE,
    ) -> bool:
        """
        Write a record to workspace memory.
        
        Args:
            ticker: Symbol identifier
            record: Data to store
            max_records: Maximum records to keep
            
        Returns:
            True if successful
        """
        try:
            key = self.MEMORY_KEY_PATTERN.format(ticker=ticker)
            
            # Add timestamp if not present
            if "timestamp" not in record:
                record["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            # Serialize record
            serialized = json.dumps(record)
            
            # Write to Redis list (FIFO)
            await self.redis.rpush(key, serialized)
            
            # Trim to max size (keep most recent)
            await self.redis.ltrim(key, -max_records, -1)
            
            # Set TTL
            await self.redis.expire(key, self.MEMORY_TTL_SECONDS)
            
            log.debug(f"[WORKSPACE MEMORY] Wrote record for {ticker}")
            return True
            
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Write failed for {ticker}: {e}")
            return False

    async def read_records(
        self,
        ticker: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Read recent records from workspace memory.
        
        Args:
            ticker: Symbol identifier
            limit: Maximum records to retrieve
            
        Returns:
            List of records
        """
        try:
            key = self.MEMORY_KEY_PATTERN.format(ticker=ticker)
            
            # Get most recent records (negative indices for LIFO-like behavior)
            raw_records = await self.redis.lrange(key, -limit, -1)
            
            if not raw_records:
                log.debug(f"[WORKSPACE MEMORY] No records found for {ticker}")
                return []
            
            # Deserialize records
            records = []
            for raw in raw_records:
                try:
                    record = json.loads(raw)
                    records.append(record)
                except json.JSONDecodeError:
                    log.warning(f"[WORKSPACE MEMORY] Failed to decode record for {ticker}")
            
            log.debug(f"[WORKSPACE MEMORY] Read {len(records)} records for {ticker}")
            return records
            
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Read failed for {ticker}: {e}")
            return []

    async def read_records_weighted(
        self,
        ticker: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Read records with date-weighted RAG (quadrant system).
        
        Records are weighted by date using a quadrant system:
        - Q1 (most recent 25%): weight = 1.0
        - Q2 (next 25%): weight = 0.75
        - Q3 (next 25%): weight = 0.5
        - Q4 (oldest 25%): weight = 0.25
        
        Args:
            ticker: Symbol identifier
            limit: Maximum records to retrieve
            
        Returns:
            List of records with 'weight' field added
        """
        try:
            key = self.MEMORY_KEY_PATTERN.format(ticker=ticker)
            
            # Get all records (we need full list for quadrant calculation)
            raw_records = await self.redis.lrange(key, 0, -1)
            
            if not raw_records:
                log.debug(f"[WORKSPACE MEMORY] No records found for {ticker}")
                return []
            
            # Deserialize records
            records = []
            for raw in raw_records:
                try:
                    record = json.loads(raw)
                    records.append(record)
                except json.JSONDecodeError:
                    log.warning(f"[WORKSPACE MEMORY] Failed to decode record for {ticker}")
            
            if not records:
                return []
            
            # Sort by timestamp (oldest first for quadrant calculation)
            # Handle both ISO string timestamps and datetime objects
            def get_timestamp(record):
                ts = record.get("timestamp", "")
                if isinstance(ts, str):
                    try:
                        # Parse ISO format timestamp
                        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        return datetime.min.replace(tzinfo=timezone.utc)
                elif isinstance(ts, datetime):
                    return ts
                else:
                    return datetime.min.replace(tzinfo=timezone.utc)
            
            records.sort(key=get_timestamp)
            
            # Calculate quadrant weights
            total_records = len(records)
            if total_records == 0:
                return []
            
            # Divide into 4 quadrants (most recent = highest weight)
            q1_size = max(1, total_records // 4)  # Most recent 25%
            q2_size = max(1, total_records // 4)  # Next 25%
            q3_size = max(1, total_records // 4)  # Next 25%
            q4_size = total_records - q1_size - q2_size - q3_size  # Oldest remaining
            
            # Assign weights (oldest records first in list, most recent last)
            weighted_records = []
            for i, record in enumerate(records):
                if i < q4_size:
                    weight = 0.25  # Q4 (oldest)
                elif i < q4_size + q3_size:
                    weight = 0.5  # Q3
                elif i < q4_size + q3_size + q2_size:
                    weight = 0.75  # Q2
                else:
                    weight = 1.0  # Q1 (most recent)
                
                record_with_weight = record.copy()
                record_with_weight["weight"] = weight
                weighted_records.append(record_with_weight)
            
            # Return most recent records (with weights), limited to requested limit
            # Reverse to get most recent first (highest weight)
            result = list(reversed(weighted_records[-limit:])) if limit > 0 else list(reversed(weighted_records))
            
            log.debug(f"[WORKSPACE MEMORY] Read {len(result)} weighted records for {ticker}")
            return result
            
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Read weighted failed for {ticker}: {e}")
            return []

    async def get_latest_trend(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest trend decision."""
        records = await self.read_records(ticker, limit=10)
        for record in reversed(records):
            if record.get("agent") == "TrendAgent":
                return record
        return None

    async def get_latest_fact(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest fact insight."""
        records = await self.read_records(ticker, limit=10)
        for record in reversed(records):
            if record.get("agent") == "FactAgent":
                return record
        return None

    async def get_latest_memory(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest memory record."""
        records = await self.read_records(ticker, limit=10)
        for record in reversed(records):
            if record.get("agent") == "MemoryAgent":
                return record
        return None

    async def clear_workspace(self, ticker: str) -> bool:
        """Clear all workspace memory for a ticker."""
        try:
            key = self.MEMORY_KEY_PATTERN.format(ticker=ticker)
            await self.redis.delete(key)
            log.info(f"[WORKSPACE MEMORY] Cleared workspace for {ticker}")
            return True
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Clear failed for {ticker}: {e}")
            return False

    async def add_chat_message(
        self,
        ticker: str,
        role: str,
        content: str,
    ) -> bool:
        """
        Add a chat message to the chat history (limited to 1-2 messages).
        
        Args:
            ticker: Symbol identifier
            role: Message role ("user" or "assistant")
            content: Message content
            
        Returns:
            True if successful
        """
        try:
            key = self.CHAT_HISTORY_KEY_PATTERN.format(ticker=ticker)
            
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Serialize message
            serialized = json.dumps(message)
            
            # Write to Redis list
            await self.redis.rpush(key, serialized)
            
            # Trim to max size (keep most recent 1-2 messages)
            await self.redis.ltrim(key, -self.CHAT_HISTORY_MAX_SIZE, -1)
            
            # Set TTL
            await self.redis.expire(key, self.MEMORY_TTL_SECONDS)
            
            log.debug(f"[WORKSPACE MEMORY] Added chat message for {ticker}")
            return True
            
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Add chat message failed for {ticker}: {e}")
            return False

    async def get_chat_history(
        self,
        ticker: str,
    ) -> List[Dict[str, Any]]:
        """
        Get chat history for a ticker (1-2 messages).
        
        Args:
            ticker: Symbol identifier
            
        Returns:
            List of chat messages
        """
        try:
            key = self.CHAT_HISTORY_KEY_PATTERN.format(ticker=ticker)
            
            # Get all chat messages
            raw_messages = await self.redis.lrange(key, 0, -1)
            
            if not raw_messages:
                log.debug(f"[WORKSPACE MEMORY] No chat history found for {ticker}")
                return []
            
            # Deserialize messages
            messages = []
            for raw in raw_messages:
                try:
                    message = json.loads(raw)
                    messages.append(message)
                except json.JSONDecodeError:
                    log.warning(f"[WORKSPACE MEMORY] Failed to decode chat message for {ticker}")
            
            log.debug(f"[WORKSPACE MEMORY] Read {len(messages)} chat messages for {ticker}")
            return messages
            
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Get chat history failed for {ticker}: {e}")
            return []

    async def clear_chat_history(self, ticker: str) -> bool:
        """Clear chat history for a ticker."""
        try:
            key = self.CHAT_HISTORY_KEY_PATTERN.format(ticker=ticker)
            await self.redis.delete(key)
            log.info(f"[WORKSPACE MEMORY] Cleared chat history for {ticker}")
            return True
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Clear chat history failed for {ticker}: {e}")
            return False

    async def get_workspace_stats(self, ticker: str) -> Dict[str, Any]:
        """Get statistics about workspace memory."""
        try:
            key = self.MEMORY_KEY_PATTERN.format(ticker=ticker)
            
            # Get all records
            all_records = await self.read_records(ticker, limit=1000)
            
            # Count by agent
            agent_counts = {}
            for record in all_records:
                agent = record.get("agent", "unknown")
                agent_counts[agent] = agent_counts.get(agent, 0) + 1
            
            # Get chat history count
            chat_history = await self.get_chat_history(ticker)
            
            return {
                "ticker": ticker,
                "total_records": len(all_records),
                "agent_counts": agent_counts,
                "chat_history_count": len(chat_history),
                "key": key,
            }
        except Exception as e:
            log.error(f"[WORKSPACE MEMORY] Stats failed for {ticker}: {e}")
            return {}


class WorkspaceMemoryManager:
    """
    High-level manager for workspace memory across multiple tickers.
    
    Handles:
    - Memory initialization
    - Batch operations
    - Memory cleanup
    - Statistics aggregation
    """

    def __init__(self, redis: RedisClient):
        self.workspace = WorkspaceMemory(redis)
        self.redis = redis

    async def initialize_ticker(self, ticker: str) -> bool:
        """Initialize workspace for a new ticker."""
        log.info(f"[WORKSPACE MANAGER] Initializing workspace for {ticker}")
        # Just write an init record
        return await self.workspace.write_record(
            ticker,
            {
                "agent": "system",
                "event": "workspace_initialized",
                "ticker": ticker,
            },
        )

    async def get_agent_context(self, ticker: str) -> Dict[str, Any]:
        """
        Assemble complete agent context from workspace memory.
        
        Returns context with latest trend, fact, and memory records.
        """
        trend = await self.workspace.get_latest_trend(ticker)
        fact = await self.workspace.get_latest_fact(ticker)
        memory = await self.workspace.get_latest_memory(ticker)
        
        return {
            "ticker": ticker,
            "trend": trend,
            "fact": fact,
            "memory": memory,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def cleanup_old_memory(self, ticker: str, keep_recent: int = 100) -> bool:
        """Cleanup old memory records, keeping only recent ones."""
        try:
            key = f"workspace:memory:{ticker}"
            all_records = await self.redis.lrange(key, 0, -1)
            
            if len(all_records) > keep_recent:
                # Remove older records
                await self.redis.ltrim(key, -keep_recent, -1)
                log.info(f"[WORKSPACE MANAGER] Cleaned up {len(all_records) - keep_recent} old records for {ticker}")
            
            return True
        except Exception as e:
            log.error(f"[WORKSPACE MANAGER] Cleanup failed for {ticker}: {e}")
            return False

    async def get_all_stats(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all tickers."""
        stats = {}
        for ticker in tickers:
            stats[ticker] = await self.workspace.get_workspace_stats(ticker)
        return stats

