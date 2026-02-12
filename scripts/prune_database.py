"""
Database and log pruning utility.
Cleans up old records from PostgreSQL and Redis to prevent database bloat.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from core.config import settings
from core.logging import log
from core.redis_client import get_redis_client


async def prune_postgres_tables(days_to_keep: int = 30):
    """Prune old records from PostgreSQL tables."""
    try:
        from sqlalchemy import text
        from core.database import get_db_session
        
        async with get_db_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            # Prune old trades
            result = await session.execute(
                text("DELETE FROM trades WHERE executed_at < :cutoff"),
                {"cutoff": cutoff_date}
            )
            trades_deleted = result.rowcount
            
            # Prune old portfolio snapshots (keep daily snapshots)
            result = await session.execute(
                text("""
                    DELETE FROM portfolio_snapshots 
                    WHERE snapshot_at < :cutoff 
                    AND id NOT IN (
                        SELECT DISTINCT ON (DATE(snapshot_at)) id 
                        FROM portfolio_snapshots 
                        WHERE snapshot_at >= :cutoff 
                        ORDER BY DATE(snapshot_at), snapshot_at DESC
                    )
                """),
                {"cutoff": cutoff_date}
            )
            snapshots_deleted = result.rowcount
            
            # Prune old agent signals
            result = await session.execute(
                text("DELETE FROM agent_signals WHERE created_at < :cutoff"),
                {"cutoff": cutoff_date}
            )
            signals_deleted = result.rowcount
            
            # Prune old performance metrics
            result = await session.execute(
                text("DELETE FROM performance_metrics WHERE timestamp < :cutoff"),
                {"cutoff": cutoff_date}
            )
            metrics_deleted = result.rowcount
            
            await session.commit()
            
            log.info(
                "PostgreSQL pruning completed",
                trades_deleted=trades_deleted,
                snapshots_deleted=snapshots_deleted,
                signals_deleted=signals_deleted,
                metrics_deleted=metrics_deleted,
                days_kept=days_to_keep
            )
            
            return {
                "trades_deleted": trades_deleted,
                "snapshots_deleted": snapshots_deleted,
                "signals_deleted": signals_deleted,
                "metrics_deleted": metrics_deleted,
            }
    except ImportError:
        log.warning("SQLAlchemy not available, skipping PostgreSQL pruning")
        return {}
    except Exception as e:
        log.error(f"Error pruning PostgreSQL: {e}")
        return {}


async def prune_redis_keys(days_to_keep: int = 30):
    """Prune old Redis keys and lists."""
    redis = await get_redis_client()
    
    try:
        cutoff_timestamp = (datetime.utcnow() - timedelta(days=days_to_keep)).timestamp()
        
        # Prune old logs
        log_keys = await redis.keys("logs:*")
        pruned_logs = 0
        for key in log_keys:
            try:
                # Check if key is a list (log entries)
                key_type = await redis.type(key)
                if key_type == "list":
                    # Trim list to keep only recent entries
                    await redis.ltrim(key, 0, 999)  # Keep last 1000 entries
                    pruned_logs += 1
            except Exception:
                pass
        
        # Prune old signal history
        signal_keys = [
            "memory:signals",
            "memory:news",
            "memory:trades",
        ]
        for key in signal_keys:
            try:
                # Keep only last N entries (handled by prune pipeline)
                await redis.ltrim(key, 0, settings.memory_prune_limit - 1)
            except Exception:
                pass
        
        # Prune old review history
        await redis.ltrim("orchestrator:agent_weights_history", 0, 29)  # Keep last 30
        
        # Prune old security events
        await redis.ltrim("security:events", 0, 999)  # Keep last 1000
        await redis.ltrim("security:alerts", 0, 499)  # Keep last 500
        
        log.info(
            "Redis pruning completed",
            log_keys_pruned=pruned_logs,
            days_kept=days_to_keep
        )
        
        return {"log_keys_pruned": pruned_logs}
    except Exception as e:
        log.error(f"Error pruning Redis: {e}")
        return {}


async def prune_log_files(days_to_keep: int = 7):
    """Prune old log files from disk."""
    try:
        log_dir = Path(settings.log_file).parent
        if not log_dir.exists():
            return {}
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        pruned_files = 0
        total_size_freed = 0
        
        # Prune backend logs
        for log_file in log_dir.glob("*.log*"):
            try:
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    size = log_file.stat().st_size
                    log_file.unlink()
                    pruned_files += 1
                    total_size_freed += size
            except Exception:
                pass
        
        # Prune frontend/UI logs
        frontend_log_dirs = [
            project_root / "ui" / "logs",
            project_root / "frontend" / "logs",
            project_root / "ui" / ".next" / "logs",
            project_root / "frontend" / ".next" / "logs",
            project_root / "logs" / "ui",
            project_root / "logs" / "frontend",
        ]
        
        frontend_files_pruned = 0
        for frontend_dir in frontend_log_dirs:
            if frontend_dir.exists():
                for log_file in frontend_dir.rglob("*.log*"):
                    try:
                        if log_file.stat().st_mtime < cutoff_date.timestamp():
                            size = log_file.stat().st_size
                            log_file.unlink()
                            frontend_files_pruned += 1
                            total_size_freed += size
                    except Exception:
                        pass
        
        # Prune browser console logs if stored
        console_log_dirs = [
            project_root / "logs" / "console",
            project_root / "ui" / "console-logs",
        ]
        
        console_files_pruned = 0
        for console_dir in console_log_dirs:
            if console_dir.exists():
                for log_file in console_dir.rglob("*"):
                    try:
                        if log_file.is_file() and log_file.stat().st_mtime < cutoff_date.timestamp():
                            size = log_file.stat().st_size
                            log_file.unlink()
                            console_files_pruned += 1
                            total_size_freed += size
                    except Exception:
                        pass
        
        log.info(
            "Log file pruning completed",
            files_pruned=pruned_files,
            frontend_files_pruned=frontend_files_pruned,
            console_files_pruned=console_files_pruned,
            size_freed_mb=round(total_size_freed / 1024 / 1024, 2),
            days_kept=days_to_keep
        )
        
        return {
            "files_pruned": pruned_files,
            "frontend_files_pruned": frontend_files_pruned,
            "console_files_pruned": console_files_pruned,
            "size_freed_bytes": total_size_freed
        }
    except Exception as e:
        log.error(f"Error pruning log files: {e}")
        return {}


async def main():
    """Main pruning function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Prune database and logs")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of data to keep (default: 30)"
    )
    parser.add_argument(
        "--log-days",
        type=int,
        default=7,
        help="Number of days of log files to keep (default: 7)"
    )
    parser.add_argument(
        "--postgres-only",
        action="store_true",
        help="Only prune PostgreSQL"
    )
    parser.add_argument(
        "--redis-only",
        action="store_true",
        help="Only prune Redis"
    )
    parser.add_argument(
        "--logs-only",
        action="store_true",
        help="Only prune log files"
    )
    
    args = parser.parse_args()
    
    results = {}
    
    if not args.redis_only and not args.logs_only:
        results["postgres"] = await prune_postgres_tables(args.days)
    
    if not args.postgres_only and not args.logs_only:
        results["redis"] = await prune_redis_keys(args.days)
    
    if not args.postgres_only and not args.redis_only:
        results["logs"] = await prune_log_files(args.log_days)
    
    print("\n=== Pruning Summary ===")
    for component, stats in results.items():
        print(f"\n{component.upper()}:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    await get_redis_client().disconnect()


if __name__ == "__main__":
    asyncio.run(main())

