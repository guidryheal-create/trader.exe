"""DEX manager runtime/config/logging service for API and UI."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redis import Redis

from core.camel_tools.wallet_analysis_toolkit import WalletAnalysisToolkit
from core.settings.config import settings
from core.logging import log
from core.pipelines.dex.triggers import (
    apply_trigger_settings as apply_dex_trigger_settings,
    ensure_registered as ensure_dex_triggers_registered,
    extract_trigger_settings as extract_dex_trigger_settings,
)
from core.pipelines.trigger_registry import trigger_registry
from core.pipelines.dex_manager import DexManager, DexTraderConfig, ReviewMode


DEX_CONFIG_FILE_PATH = "config/dex_manager_config.json"


class DexTraderService:
    """Manages DEX manager lifecycle, persistent config, and dashboard metrics."""

    CONFIG_KEY = "dex:config"
    LOGS_KEY = "dex:logs"
    METRICS_KEY = "dex:metrics"
    CYCLE_HISTORY_KEY = "dex:cycle_history"
    TASK_HISTORY_KEY = "dex:task_history"
    TRADE_HISTORY_KEY = "dex:trade_history"

    def __init__(self) -> None:
        self._redis = self._init_redis()
        self._trader: DexManager | None = None
        self._in_memory_logs: list[dict[str, Any]] = []
        self._config = self._default_config()
        self._load_config()

    @staticmethod
    def _init_redis() -> Redis | None:
        try:
            client = Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
            )
            client.ping()
            return client
        except Exception as exc:
            log.warning(f"DEX manager service Redis unavailable: {exc}")
            return None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _default_config(self) -> dict[str, Any]:
        return {
            "process": {
                "active_bot": "dex",
                "cycle_hours": settings.dex_trader_cycle_hours,
                "watchlist_scan_seconds": settings.watchlist_scan_seconds,
                "watchlist_trigger_pct": settings.watchlist_trigger_pct,
                "watchlist_fast_trigger_pct": settings.watchlist_fast_trigger_pct,
                "watchlist_global_roi_trigger_enabled": settings.watchlist_global_roi_trigger_enabled,
                "watchlist_global_roi_trigger_pct": settings.watchlist_global_roi_trigger_pct,
                "watchlist_global_roi_fast_trigger_pct": settings.watchlist_global_roi_fast_trigger_pct,
                "token_exploration_limit": settings.dex_trader_token_exploration_limit,
                "wallet_review_cache_seconds": settings.dex_wallet_review_cache_seconds,
                "strategy_hint_interval_hours": settings.dex_strategy_hint_interval_hours,
                "auto_enhancement_enabled": settings.auto_enhancement_enabled,
                "task_flows": {
                    "cycle_pipeline": True,
                    "watchlist_review_pipeline": True,
                },
            },
            "runtime": {
                "cycle_enabled": False,
                "watchlist_enabled": False,
                "auto_start_on_boot": True,
            },
            "last_updated": self._now_iso(),
        }

    def _persist_config(self) -> None:
        self._config["last_updated"] = self._now_iso()
        if self._redis:
            try:
                self._redis.set(self.CONFIG_KEY, json.dumps(self._config))
            except Exception as exc:
                log.warning(f"Failed persisting DEX config to Redis: {exc}")
        try:
            os.makedirs(os.path.dirname(DEX_CONFIG_FILE_PATH), exist_ok=True)
            Path(DEX_CONFIG_FILE_PATH).write_text(json.dumps(self._config, indent=2))
        except Exception as exc:
            log.warning(f"Failed persisting DEX config file: {exc}")

    def _load_config(self) -> None:
        data: dict[str, Any] | None = None
        if self._redis:
            try:
                raw = self._redis.get(self.CONFIG_KEY)
                if raw:
                    data = json.loads(raw)
            except Exception:
                data = None
        if data is None and Path(DEX_CONFIG_FILE_PATH).exists():
            try:
                data = json.loads(Path(DEX_CONFIG_FILE_PATH).read_text())
            except Exception:
                data = None
        if isinstance(data, dict):
            self._config.update(data)

    def get_config(self) -> dict[str, Any]:
        return dict(self._config)

    def update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        process = payload.get("process") or {}
        runtime = payload.get("runtime") or {}
        if isinstance(process, dict):
            self._config.setdefault("process", {}).update(process)
        if isinstance(runtime, dict):
            self._config.setdefault("runtime", {}).update(runtime)
        self._persist_config()
        if self._trader:
            self._apply_config_to_trader()
        self._record_event("INFO", "DEX config updated", {"process": process, "runtime": runtime})
        return self.get_config()

    def _apply_config_to_trader(self) -> None:
        if not self._trader:
            return
        process = self._config.get("process", {})
        runtime = self._config.get("runtime", {})
        trader_cfg = self._trader.config
        trader_cfg.cycle_hours = int(process.get("cycle_hours", trader_cfg.cycle_hours))
        trader_cfg.watchlist_enabled = bool(runtime.get("watchlist_enabled", trader_cfg.watchlist_enabled))
        trader_cfg.watchlist_scan_seconds = int(process.get("watchlist_scan_seconds", trader_cfg.watchlist_scan_seconds))
        trader_cfg.watchlist_trigger_pct = float(process.get("watchlist_trigger_pct", trader_cfg.watchlist_trigger_pct))
        trader_cfg.watchlist_fast_trigger_pct = float(process.get("watchlist_fast_trigger_pct", trader_cfg.watchlist_fast_trigger_pct))
        trader_cfg.watchlist_global_roi_trigger_enabled = bool(
            process.get("watchlist_global_roi_trigger_enabled", trader_cfg.watchlist_global_roi_trigger_enabled)
        )
        trader_cfg.watchlist_global_roi_trigger_pct = float(
            process.get("watchlist_global_roi_trigger_pct", trader_cfg.watchlist_global_roi_trigger_pct)
        )
        trader_cfg.watchlist_global_roi_fast_trigger_pct = float(
            process.get("watchlist_global_roi_fast_trigger_pct", trader_cfg.watchlist_global_roi_fast_trigger_pct)
        )
        trader_cfg.token_exploration_limit = int(process.get("token_exploration_limit", trader_cfg.token_exploration_limit))
        trader_cfg.wallet_review_cache_seconds = int(
            process.get("wallet_review_cache_seconds", trader_cfg.wallet_review_cache_seconds)
        )
        trader_cfg.strategy_hint_interval_hours = int(
            process.get("strategy_hint_interval_hours", trader_cfg.strategy_hint_interval_hours)
        )
        trader_cfg.auto_enhancement_enabled = bool(
            process.get("auto_enhancement_enabled", trader_cfg.auto_enhancement_enabled)
        )
        if hasattr(self._trader, "_cycle_runtime"):
            self._trader._cycle_runtime.update_cycle_hours(int(trader_cfg.cycle_hours))
        flow_flags = process.get("task_flows", {})
        if isinstance(flow_flags, dict):
            self._trader.update_task_flows({str(k): bool(v) for k, v in flow_flags.items()})

    def _record_event(self, level: str, message: str, context: dict[str, Any]) -> None:
        event = {
            "timestamp": self._now_iso(),
            "level": level.upper(),
            "message": message,
            "context": context or {},
        }
        self._in_memory_logs.append(event)
        self._in_memory_logs = self._in_memory_logs[-500:]
        if self._redis:
            try:
                self._redis.lpush(self.LOGS_KEY, json.dumps(event))
                self._redis.ltrim(self.LOGS_KEY, 0, 999)
            except Exception:
                pass
            try:
                self._redis.hincrby(self.METRICS_KEY, "events_total", 1)
                msg = event["message"].lower()
                if "cycle started" in msg:
                    self._redis.hincrby(self.METRICS_KEY, "cycles_started", 1)
                if "cycle completed" in msg:
                    self._redis.hincrby(self.METRICS_KEY, "cycles_completed", 1)
                if "task started" in msg:
                    self._redis.hincrby(self.METRICS_KEY, "tasks_started", 1)
                    self._redis.lpush(self.TASK_HISTORY_KEY, json.dumps(event))
                    self._redis.ltrim(self.TASK_HISTORY_KEY, 0, 1000)
                if "task completed" in msg:
                    self._redis.hincrby(self.METRICS_KEY, "tasks_completed", 1)
                    self._redis.lpush(self.TASK_HISTORY_KEY, json.dumps(event))
                    self._redis.ltrim(self.TASK_HISTORY_KEY, 0, 1000)
                if "task failed" in msg:
                    self._redis.hincrby(self.METRICS_KEY, "tasks_failed", 1)
                    self._redis.lpush(self.TASK_HISTORY_KEY, json.dumps(event))
                    self._redis.ltrim(self.TASK_HISTORY_KEY, 0, 1000)
                if "watchlist notification" in msg:
                    self._redis.hincrby(self.METRICS_KEY, "watchlist_notifications", 1)
            except Exception:
                pass

    async def ensure_trader(self) -> DexManager:
        if self._trader:
            return self._trader

        process = self._config.get("process", {})
        trader_cfg = DexTraderConfig(
            cycle_hours=int(process.get("cycle_hours", settings.dex_trader_cycle_hours)),
            watchlist_enabled=bool(self._config.get("runtime", {}).get("watchlist_enabled", settings.watchlist_enabled)),
            watchlist_scan_seconds=int(process.get("watchlist_scan_seconds", settings.watchlist_scan_seconds)),
            watchlist_trigger_pct=float(process.get("watchlist_trigger_pct", settings.watchlist_trigger_pct)),
            watchlist_fast_trigger_pct=float(process.get("watchlist_fast_trigger_pct", settings.watchlist_fast_trigger_pct)),
            watchlist_global_roi_trigger_enabled=bool(
                process.get("watchlist_global_roi_trigger_enabled", settings.watchlist_global_roi_trigger_enabled)
            ),
            watchlist_global_roi_trigger_pct=float(
                process.get("watchlist_global_roi_trigger_pct", settings.watchlist_global_roi_trigger_pct)
            ),
            watchlist_global_roi_fast_trigger_pct=float(
                process.get("watchlist_global_roi_fast_trigger_pct", settings.watchlist_global_roi_fast_trigger_pct)
            ),
            token_exploration_limit=int(process.get("token_exploration_limit", settings.dex_trader_token_exploration_limit)),
            wallet_review_cache_seconds=int(process.get("wallet_review_cache_seconds", settings.dex_wallet_review_cache_seconds)),
            strategy_hint_interval_hours=int(
                process.get("strategy_hint_interval_hours", settings.dex_strategy_hint_interval_hours)
            ),
            auto_enhancement_enabled=bool(process.get("auto_enhancement_enabled", settings.auto_enhancement_enabled)),
        )

        try:
            self._trader = await DexManager.build(
                config=trader_cfg,
                event_logger=self._record_event,
            )
            self._record_event("INFO", "DEX manager initialized with shared runtime workforce", {})
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize DEX manager with shared workforce: {exc}") from exc

        self._apply_config_to_trader()
        return self._trader

    async def start(self, cycle_enabled: bool = True, watchlist_enabled: bool = True) -> dict[str, Any]:
        trader = await self.ensure_trader()
        await trader.start(cycle_enabled=cycle_enabled, watchlist_enabled=watchlist_enabled)
        self._config.setdefault("runtime", {})["cycle_enabled"] = bool(cycle_enabled)
        self._config.setdefault("runtime", {})["watchlist_enabled"] = bool(watchlist_enabled)
        self._persist_config()
        workforce_status = trader.get_status()
        return {
            "status": "ok",
            "running": bool(workforce_status.get("running")),
            "cycle_enabled": bool(cycle_enabled),
            "watchlist_enabled": bool(watchlist_enabled),
        }

    async def stop(self) -> dict[str, Any]:
        if self._trader:
            await self._trader.stop()
        self._config.setdefault("runtime", {})["cycle_enabled"] = False
        self._config.setdefault("runtime", {})["watchlist_enabled"] = False
        self._persist_config()
        self._record_event("INFO", "DEX manager stopped via API", {})
        return {"status": "ok", "running": False}

    async def trigger_cycle(self, mode: str = "long_study", reason: str = "manual_trigger") -> dict[str, Any]:
        trader = await self.ensure_trader()
        review_mode = ReviewMode.FAST_DECISION if mode == ReviewMode.FAST_DECISION.value else ReviewMode.LONG_STUDY
        self._record_event("INFO", "DEX cycle trigger requested", {"mode": review_mode.value, "reason": reason})
        execution_id = trader.launch_execution(mode=review_mode, reason=reason)
        if self._redis:
            try:
                payload = {"timestamp": self._now_iso(), "mode": review_mode.value, "reason": reason, "execution_id": execution_id}
                self._redis.lpush(self.CYCLE_HISTORY_KEY, json.dumps(payload))
                self._redis.ltrim(self.CYCLE_HISTORY_KEY, 0, 500)
            except Exception:
                pass
        return {"status": "accepted", "execution_id": execution_id}

    async def trigger_cycle_sync(self, mode: str = "long_study", reason: str = "manual_trigger") -> dict[str, Any]:
        trader = await self.ensure_trader()
        review_mode = ReviewMode.FAST_DECISION if mode == ReviewMode.FAST_DECISION.value else ReviewMode.LONG_STUDY
        self._record_event("INFO", "DEX cycle sync trigger requested", {"mode": review_mode.value, "reason": reason})
        result = await trader.run_trader_cycle(mode=review_mode, reason=reason)
        return {"status": "ok", "result": result}

    async def auto_start_if_enabled(self) -> None:
        runtime = self._config.get("runtime", {})
        if not runtime.get("auto_start_on_boot", True):
            return
        cycle_enabled = bool(runtime.get("cycle_enabled", False))
        watchlist_enabled = bool(runtime.get("watchlist_enabled", False))
        if cycle_enabled or watchlist_enabled:
            await self.start(cycle_enabled=cycle_enabled, watchlist_enabled=watchlist_enabled)

    async def get_status(self) -> dict[str, Any]:
        trader = await self.ensure_trader()
        workforce_status = trader.get_status()
        wallet_state = {}
        try:
            wallet_state = WalletAnalysisToolkit(redis_client=trader.watchlist_toolkit.redis).get_global_wallet_state(
                wallet_address=settings.wallet_address or ""
            )
        except Exception as exc:
            wallet_state = {"success": False, "error": str(exc)}
        return {
            "status": "ok",
            "pipeline": workforce_status.get("pipeline", "dex"),
            "system_name": workforce_status.get("system_name", "dex_manager"),
            "running": bool(workforce_status.get("running")),
            "cycle_enabled": bool(workforce_status.get("cycle_enabled")),
            "watchlist_enabled": bool(workforce_status.get("watchlist_enabled")),
            "active_bot": str(self._config.get("process", {}).get("active_bot", "dex")),
            "workforce": workforce_status,
            "wallet_state": wallet_state,
            "metrics": self.get_metrics(),
            "workers": workforce_status.get("workers", []),
            "task_flows": workforce_status.get("task_flows", []),
            "timestamp": self._now_iso(),
        }

    async def list_task_flows(self) -> list[dict[str, Any]]:
        trader = await self.ensure_trader()
        return trader.list_task_flows()

    async def update_task_flows(self, flags: dict[str, bool]) -> list[dict[str, Any]]:
        trader = await self.ensure_trader()
        updated = trader.update_task_flows(flags)
        process = self._config.setdefault("process", {})
        stored = process.setdefault("task_flows", {})
        for task_id, value in flags.items():
            stored[str(task_id)] = bool(value)
        self._persist_config()
        return updated

    def log_event(self, level: str, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = context or {}
        self._record_event(level, message, payload)
        return {
            "timestamp": self._now_iso(),
            "level": str(level).upper(),
            "message": message,
            "context": payload,
        }

    def list_trigger_specs(self) -> list[dict[str, Any]]:
        ensure_dex_triggers_registered()
        specs = []
        for row in trigger_registry.describe():
            if row.get("pipeline") == "dex":
                specs.append(row)
        return specs

    def get_trigger_settings(self, trigger_name: str) -> dict[str, Any]:
        ensure_dex_triggers_registered()
        spec = trigger_registry.get("dex", trigger_name)
        if not spec:
            raise KeyError(trigger_name)
        settings_payload = extract_dex_trigger_settings(trigger_name, self._config)
        return {
            "key": spec.key,
            "pipeline": spec.pipeline,
            "trigger": spec.trigger,
            "description": spec.description,
            "settings_schema": spec.settings_model.model_json_schema(),
            "settings": settings_payload,
            "last_updated": self._config.get("last_updated"),
        }

    def update_trigger_settings(self, trigger_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        ensure_dex_triggers_registered()
        spec = trigger_registry.get("dex", trigger_name)
        if not spec:
            raise KeyError(trigger_name)
        normalized = apply_dex_trigger_settings(trigger_name, self._config, payload)
        self._persist_config()
        if self._trader:
            self._apply_config_to_trader()
        self._record_event("INFO", "DEX trigger settings updated", {"trigger": trigger_name, "settings": normalized})
        return self.get_trigger_settings(trigger_name)

    def _read_json_list(self, key: str, limit: int) -> list[dict[str, Any]]:
        if self._redis:
            try:
                rows = self._redis.lrange(key, 0, max(0, limit - 1))
                items: list[dict[str, Any]] = []
                for row in rows:
                    try:
                        items.append(json.loads(row))
                    except Exception:
                        continue
                return items
            except Exception:
                return []
        return []

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._redis:
            logs = self._read_json_list(self.LOGS_KEY, limit)
            if logs:
                return logs
        return list(reversed(self._in_memory_logs))[:limit]

    def clear_logs(self) -> None:
        self._in_memory_logs.clear()
        if self._redis:
            try:
                self._redis.delete(self.LOGS_KEY)
            except Exception:
                pass

    def get_metrics(self) -> dict[str, Any]:
        if not self._redis:
            return {"events_total": len(self._in_memory_logs)}
        try:
            data = self._redis.hgetall(self.METRICS_KEY)
            metrics: dict[str, Any] = {}
            for k, v in data.items():
                try:
                    metrics[k] = int(v)
                except Exception:
                    metrics[k] = v
            return metrics
        except Exception:
            return {}

    async def get_dashboard_snapshot(self) -> dict[str, Any]:
        status = await self.get_status()
        wallet_state = status.get("wallet_state", {})
        trades = self.list_trade_history(limit=200)
        tasks = self.list_task_history(limit=200)
        cycles = self.list_cycle_history(limit=100)
        logs = self.list_logs(limit=200)
        return {
            "status": "ok",
            "active_bot": status.get("active_bot"),
            "runtime": {
                "running": status.get("running"),
                "cycle_enabled": status.get("cycle_enabled"),
                "watchlist_enabled": status.get("watchlist_enabled"),
                "workforce": status.get("workforce", {}),
            },
            "wallet_state": wallet_state,
            "metrics": status.get("metrics", {}),
            "counts": {
                "trade_history": len(trades),
                "task_history": len(tasks),
                "cycle_history": len(cycles),
                "logs": len(logs),
                "open_positions": wallet_state.get("open_position_count", 0),
            },
            "latest": {
                "trades": trades[:20],
                "tasks": tasks[:20],
                "cycles": cycles[:20],
                "logs": logs[:50],
            },
            "timestamp": status.get("timestamp"),
        }

    def list_trade_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._read_json_list(self.TRADE_HISTORY_KEY, limit)

    def list_cycle_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._read_json_list(self.CYCLE_HISTORY_KEY, limit)

    def list_task_history(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._read_json_list(self.TASK_HISTORY_KEY, limit)

    async def get_execution(self, execution_id: str) -> dict[str, Any]:
        trader = await self.ensure_trader()
        return trader.get_execution_status(execution_id)

    async def list_executions(self, limit: int = 50) -> list[dict[str, Any]]:
        trader = await self.ensure_trader()
        return trader.list_executions(limit=limit)


dex_trader_service = DexTraderService()
dex_manager_service = dex_trader_service
