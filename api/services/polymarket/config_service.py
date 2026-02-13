"""Process configuration service for Polymarket API."""
from __future__ import annotations

import json
import os
from typing import Any, Dict
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from core.models.workforce_config import (
    WorkforceConfigService,
)
from core.logging import log
from core.pipelines.polymarket.triggers import (
    apply_trigger_settings as apply_polymarket_trigger_settings,
    ensure_registered as ensure_polymarket_triggers_registered,
    extract_trigger_settings as extract_polymarket_trigger_settings,
)
from core.pipelines.trigger_registry import trigger_registry

CONFIG_FILE_PATH = "config/polymarket_config.json"


class ProcessConfigService:
    """In-memory runtime configuration with validation hooks and JSON persistence."""

    def __init__(self) -> None:
        self._config_service = WorkforceConfigService()
        self._active_flux = "polymarket_manager"
        self._trade_frequency_hours = 4
        self._max_ai_weighted_daily = 1.0
        self._max_ai_weighted_per_trade = 1.0
        self._rss_flux = {
            "scan_interval_seconds": self._config_service.trigger_config.interval_hours * 3600,
            "batch_size": 50,
            "review_threshold": 25,
            "max_cache": 500,
        }
        self._task_flows = {
            "batch_orchestration": True,
        }
        self._last_updated = datetime.now(timezone.utc).isoformat()
        self._load_config_from_file()

    def _load_config_from_file(self):
        """Loads configuration from the JSON file if it exists."""
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r") as f:
                    config = json.load(f)
                    self.update_config(config)
                    log.info(f"Loaded configuration from {CONFIG_FILE_PATH}")
            except (json.JSONDecodeError, IOError) as e:
                log.error(f"Error loading configuration from {CONFIG_FILE_PATH}: {e}")

    def _save_config_to_file(self):
        """Saves the current configuration to the JSON file."""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
            with open(CONFIG_FILE_PATH, "w") as f:
                json.dump(self.get_config(), f, indent=4)
            log.info(f"Saved configuration to {CONFIG_FILE_PATH}")
        except IOError as e:
            log.error(f"Error saving configuration to {CONFIG_FILE_PATH}: {e}")

    def get_config(self) -> Dict[str, Any]:
        return {
            "config_id": str(uuid4()),
            "active_flux": self._active_flux,
            "trade_frequency_hours": self._trade_frequency_hours,
            "max_ai_weighted_daily": self._max_ai_weighted_daily,
            "max_ai_weighted_per_trade": self._max_ai_weighted_per_trade,
            "trading_controls": asdict(self._config_service.trading_controls),
            "trigger_config": asdict(self._config_service.trigger_config),
            "rss_flux": dict(self._rss_flux),
            "task_flows": dict(self._task_flows),
            "agent_weights": asdict(self._config_service.agent_weights),
            "limits_status": self._config_service.get_limits_status(),
            "last_updated": self._last_updated,
        }

    def update_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        process = payload.get("process", {})
        trading_controls = payload.get("trading_controls", {})
        trigger_config = payload.get("trigger_config", {})
        agent_weights = payload.get("agent_weights", {})
        rss_flux = payload.get("rss_flux", {})
        task_flows = payload.get("task_flows", {})

        if "active_flux" in process:
            self._active_flux = str(process["active_flux"])
        if "trade_frequency_hours" in process:
            self._trade_frequency_hours = int(process["trade_frequency_hours"])
        if "max_ai_weighted_daily" in process:
            self._max_ai_weighted_daily = float(process["max_ai_weighted_daily"])
        if "max_ai_weighted_per_trade" in process:
            self._max_ai_weighted_per_trade = float(process["max_ai_weighted_per_trade"])

        # Update TradingControls
        for key, value in trading_controls.items():
            if hasattr(self._config_service.trading_controls, key):
                setattr(self._config_service.trading_controls, key, value)

        # Update TriggerConfig
        for key, value in trigger_config.items():
            if hasattr(self._config_service.trigger_config, key):
                setattr(self._config_service.trigger_config, key, value)

        # Update AgentWeightConfig
        for key, value in agent_weights.items():
            if hasattr(self._config_service.agent_weights, key):
                setattr(self._config_service.agent_weights, key, value)
        if isinstance(rss_flux, dict):
            for key in ["scan_interval_seconds", "batch_size", "review_threshold", "max_cache"]:
                if key in rss_flux:
                    self._rss_flux[key] = rss_flux[key]
        if isinstance(task_flows, dict):
            for key, value in task_flows.items():
                self._task_flows[str(key)] = bool(value)

        # Validate
        self._config_service.trading_controls.validate()
        self._config_service.trigger_config.validate()
        self._config_service.agent_weights.validate()

        self._last_updated = datetime.now(timezone.utc).isoformat()
        self._save_config_to_file()  # Persist changes
        return self.get_config()

    def list_trigger_specs(self) -> list[dict[str, Any]]:
        ensure_polymarket_triggers_registered()
        return [row for row in trigger_registry.describe() if row.get("pipeline") == "polymarket"]

    def get_trigger_settings(self, trigger_name: str) -> dict[str, Any]:
        ensure_polymarket_triggers_registered()
        spec = trigger_registry.get("polymarket", trigger_name)
        if not spec:
            raise KeyError(trigger_name)
        config = self.get_config()
        settings_payload = extract_polymarket_trigger_settings(trigger_name, config)
        return {
            "key": spec.key,
            "pipeline": spec.pipeline,
            "trigger": spec.trigger,
            "description": spec.description,
            "settings_schema": spec.settings_model.model_json_schema(),
            "settings": settings_payload,
            "last_updated": config.get("last_updated"),
        }

    def update_trigger_settings(self, trigger_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        ensure_polymarket_triggers_registered()
        spec = trigger_registry.get("polymarket", trigger_name)
        if not spec:
            raise KeyError(trigger_name)
        config = self.get_config()
        normalized = apply_polymarket_trigger_settings(trigger_name, config, payload)
        self.update_config(
            {
                "trigger_config": config.get("trigger_config", {}),
                "rss_flux": config.get("rss_flux", {}),
            }
        )
        log.info("Updated Polymarket trigger settings trigger=%s settings=%s", trigger_name, normalized)
        return self.get_trigger_settings(trigger_name)

    def get_workforce_config(self) -> WorkforceConfigService:
        return self._config_service


process_config_service = ProcessConfigService()
