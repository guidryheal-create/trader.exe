#!/usr/bin/env python3
"""
Export agentic chat logs and decisions from Redis.

This script is intended for pre-deployment audits. It:
  - Scanne les historiques de chat `chat:history:*`
  - Scanne les décisions agentiques `ai_decision:*`
  - Écrit un fichier JSON unique avec:
      {
        "generated_at": "...",
        "env": {...},
        "chats": [...],
        "decisions": [...]
      }

Usage:
  cd agentic_system_trading
  uv run scripts/export_agentic_chat_logs.py --output exports/agentic_chat_export.json
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from core.logging import setup_logging, log  # type: ignore
from core.redis_client import RedisClient  # type: ignore


async def export_chat_and_decisions(output_path: Path, max_users: int = 200, max_decisions: int = 500) -> None:
    """Export chat histories and agentic decisions to a single JSON file."""
    try:
        setup_logging()
    except Exception:
        pass

    redis = RedisClient()
    await redis.connect()

    try:
        log.info("🔍 Scanning Redis for chat histories and decisions")

        # 1) Export chat histories
        chat_data: List[Dict[str, Any]] = []
        try:
            keys = await redis.redis.keys("chat:history:*")
            keys = keys[:max_users]
            log.info(f"Found {len(keys)} chat history keys")

            for key in keys:
                user_id = str(key).split("chat:history:")[-1]
                raw = await redis.get(key)
                if not raw:
                    continue
                try:
                    history = json.loads(raw)
                except Exception:
                    history = raw

                chat_data.append(
                    {
                        "user_id": user_id,
                        "key": key,
                        "history": history,
                    }
                )
        except Exception as e:
            log.error(f"Failed to export chat histories: {e}", exc_info=True)

        # 2) Export agentic decisions
        decisions: List[Dict[str, Any]] = []
        try:
            decision_keys = await redis.redis.keys("ai_decision:*")
            decision_keys = decision_keys[:max_decisions]
            log.info(f"Found {len(decision_keys)} ai_decision keys")

            for key in decision_keys:
                data = await redis.get_json(key)
                if not data or data.get("agentic") is not True:
                    continue
                decisions.append(
                    {
                        "key": key,
                        "decision": data,
                    }
                )
        except Exception as e:
            log.error(f"Failed to export ai_decision entries: {e}", exc_info=True)

        # 3) Build export payload
        payload: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "env": {
                "ENVIRONMENT": os.getenv("ENVIRONMENT"),
                "AGENT_INSTANCE_ID": os.getenv("AGENT_INSTANCE_ID"),
            },
            "stats": {
                "chat_users": len(chat_data),
                "decisions": len(decisions),
            },
            "chats": chat_data,
            "decisions": decisions,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        log.info(f"✅ Export complete: {output_path} (users={len(chat_data)}, decisions={len(decisions)})")
        print(f"Exported agentic chat logs to: {output_path}")
    finally:
        await redis.disconnect()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export agentic chat logs and decisions from Redis.")
    parser.add_argument(
        "--output",
        type=str,
        default="exports/agentic_chat_export.json",
        help="Output JSON file path (relative to agentic_system_trading root).",
    )
    parser.add_argument(
        "--max-users",
        type=int,
        default=200,
        help="Maximum number of chat history users to export.",
    )
    parser.add_argument(
        "--max-decisions",
        type=int,
        default=500,
        help="Maximum number of ai_decision entries to export.",
    )

    args = parser.parse_args()
    output_path = (ROOT / args.output).resolve()
    asyncio.run(export_chat_and_decisions(output_path, max_users=args.max_users, max_decisions=args.max_decisions))


if __name__ == "__main__":
    main()


