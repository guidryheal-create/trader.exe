"""Polymarket manager router - Market scanning and automated trading control.

Provides API endpoints to:
- Start/stop Polymarket Manager scanning pipeline
- Configure scan intervals and trading limits
- Get flux status and active positions
- Trigger manual market batch processing
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks

# instead the flux is not Agentic except if specified.
# use manual fetch and retreive then launch workforce for analysis and execution.
# use the @polymarket_flux internal more complete process when the trigger condiction is reached
# multiple trigger type : interval every N + limitation, RSS every new N + limitation + expire check, manual
# limitations : max trades per day, max active positions, min confidence, etc.

from core.pipelines.polymarket_manager import PolymarketManager, RSSFluxConfig
from core.clients.polymarket_client import PolymarketClient
from core.logging import log
from api.services.polymarket.logging_service import logging_service
from api.services.polymarket.config_service import process_config_service
import asyncio

router = APIRouter()

# Global manager instance (initialized on startup)
_manager_instance: Optional[PolymarketManager] = None


def set_polymarket_manager_instance(instance: PolymarketManager) -> None:
    """Set the global manager instance (called on API startup)."""
    global _manager_instance
    _manager_instance = instance
    log.info("[POLYMARKET MANAGER API] Global instance initialized")


def get_polymarket_manager() -> PolymarketManager:
    """Get the global manager instance."""
    if _manager_instance is None:
        raise HTTPException(
            status_code=503,
            detail="Polymarket manager service not initialized",
        )
    return _manager_instance


async def ensure_polymarket_manager() -> PolymarketManager:
    """Ensure manager instance is initialized for UI/API calls."""
    global _manager_instance
    if _manager_instance is None:
        trigger_cfg = process_config_service.get_workforce_config().trigger_config
        trading_cfg = process_config_service.get_workforce_config().trading_controls
        runtime_cfg = process_config_service.get_config()
        rss_cfg = runtime_cfg.get("rss_flux", {})
        _manager_instance = await PolymarketManager.build(
            api_client=PolymarketClient(),
            config=RSSFluxConfig(
                scan_interval=int(rss_cfg.get("scan_interval_seconds", trigger_cfg.interval_hours * 3600)),
                batch_size=int(rss_cfg.get("batch_size", 50)),
                review_threshold=int(rss_cfg.get("review_threshold", 25)),
                max_cache=int(rss_cfg.get("max_cache", 500)),
                trigger_type=trigger_cfg.trigger_type,
                interval_hours=trigger_cfg.interval_hours,
                max_trades_per_day=trading_cfg.max_trades_per_day,
                min_confidence=trading_cfg.min_probability,
            ),
            event_logger=logging_service.log_event,
        )
        task_flows = runtime_cfg.get("task_flows", {})
        if isinstance(task_flows, dict):
            _manager_instance.update_task_flows({str(k): bool(v) for k, v in task_flows.items()})
        log.info("[POLYMARKET MANAGER API] Lazy-initialized manager instance")
    return _manager_instance


# Backward compatibility for existing imports/routes.
set_rss_flux_instance = set_polymarket_manager_instance
get_rss_flux = get_polymarket_manager
ensure_rss_flux = ensure_polymarket_manager


# ============================================================================
# Control Endpoints
# ============================================================================


@router.post("/manager/start")
@router.post("/flux/start")
async def start_rss_flux() -> Dict[str, Any]:
    """Start the Polymarket Manager market scanning pipeline.
    
    Returns:
        Status dict with flux configuration and initial state
    """
    flux = await ensure_polymarket_manager()
    
    if flux._running:
        return {
            "status": "already_running",
            "message": "Polymarket Manager is already running",
            "config": {
                "scan_interval": flux.config.scan_interval,
                "batch_size": flux.config.batch_size,
                "max_trades_per_day": flux.config.max_trades_per_day,
            },
        }
    
    try:
        await flux.start()
        log.info("[POLYMARKET MANAGER API] Manager started successfully")
        return {
            "status": "started",
            "message": "Polymarket Manager market scanning started",
            "config": {
                "scan_interval": flux.config.scan_interval,
                "batch_size": flux.config.batch_size,
                "max_trades_per_day": flux.config.max_trades_per_day,
                "min_confidence": flux.config.min_confidence,
            },
        }
    except Exception as exc:
        log.error("[POLYMARKET MANAGER API] Failed to start manager: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start Polymarket Manager: {str(exc)}",
        )


@router.post("/manager/stop")
@router.post("/flux/stop")
async def stop_rss_flux() -> Dict[str, Any]:
    """Stop the Polymarket Manager market scanning pipeline.
    
    Returns:
        Status dict confirming shutdown
    """
    flux = await ensure_polymarket_manager()
    
    if not flux._running:
        return {
            "status": "already_stopped",
            "message": "Polymarket Manager is not running",
        }
    
    try:
        await flux.stop()
        log.info("[POLYMARKET MANAGER API] Manager stopped successfully")
        return {
            "status": "stopped",
            "message": "Polymarket Manager market scanning stopped",
            "positions_active": len(flux._active_positions),
        }
    except Exception as exc:
        log.error("[POLYMARKET MANAGER API] Failed to stop manager: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop Polymarket Manager: {str(exc)}",
        )


@router.post("/manager/trigger-scan")
@router.post("/flux/trigger-scan")
async def trigger_manual_scan(
    background_tasks: BackgroundTasks,
    verify_positions: bool = Query(False),
    start_if_stopped: bool = Query(False),
    trigger_type: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Manually trigger a market batch processing cycle.

    Runs the scan in a background task to avoid blocking the API response.

    Manual triggers bypass verification by default.

    Returns:
        Status dict with scan ID and configuration
    """
    flux = await ensure_polymarket_manager()
    
    if not flux._running and start_if_stopped:
        # Start the flux in background if requested
        background_tasks.add_task(flux.start)

    try:
        effective_trigger = trigger_type or flux.config.trigger_type or "manual"
        # Trigger scan in background
        scan_id = f"manual_scan_{int(__import__('time').time())}"
        background_tasks.add_task(
            flux.process_market_batch,
            trigger_type=effective_trigger,
            verify_positions=verify_positions,
        )
        
        log.info(
            "[POLYMARKET MANAGER API] Manual scan triggered: %s (verify_positions=%s)",
            scan_id,
            verify_positions,
        )
        logging_service.log_event(
            "INFO",
            "Polymarket manager manual trigger",
            {"scan_id": scan_id, "verify_positions": verify_positions, "trigger_type": effective_trigger},
        )
        
        return {
            "status": "triggered",
            "scan_id": scan_id,
            "message": "Market batch processing triggered in background",
            "config": {
                "batch_size": flux.config.batch_size,
                "review_threshold": flux.config.review_threshold,
                "verify_positions": verify_positions,
                "trigger_type": effective_trigger,
            },
        }
    except Exception as exc:
        log.error("[POLYMARKET MANAGER API] Failed to trigger scan: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger scan: {str(exc)}",
        )


# ============================================================================
# Status & Configuration Endpoints
# ============================================================================

@router.get("/manager/status")
@router.get("/flux/status")
async def flux_status() -> Dict[str, Any]:
    """
    Manager status is scheduler + observable state.
    """
    try:
        flux = await ensure_polymarket_manager()
        status = flux.get_status()
    except Exception:
        return {
            "status": "not_initialized",
            "scheduler_running": False,
            "trades_today": 0,
            "active_positions": 0,
            "cache_size": 0,
            "workforce_attached": False,
            "scan_in_progress": False,
            "last_trigger_at": None,
            "last_trigger_type": None,
        }

    return {
        "status": "ok",
        "scheduler_running": flux._running,
        "trades_today": flux._trades_today,
        "active_positions": len(flux._active_positions),
        "cache_size": len(flux._feed_cache),
        "workforce_attached": flux.workforce is not None,
        "scan_in_progress": status.get("scan_in_progress"),
        "last_trigger_at": status.get("last_trigger_at"),
        "last_trigger_type": status.get("last_trigger_type"),
    }


@router.get("/manager/config")
@router.get("/flux/config")
async def get_flux_config() -> Dict[str, Any]:
    """Get current Polymarket Manager configuration.
    
    Returns:
        Configuration dict with all tunable parameters
    """
    flux = await ensure_polymarket_manager()
    config = flux.config
    
    return {
        "scan_interval": config.scan_interval,
        "batch_size": config.batch_size,
        "review_threshold": config.review_threshold,
        "max_cache": config.max_cache,
        "max_trades_per_day": config.max_trades_per_day,
        "min_confidence": config.min_confidence,
        "cache_path": config.cache_path,
        "trigger_type": config.trigger_type,
        "interval_hours": config.interval_hours,
    }


@router.post("/manager/config")
@router.post("/flux/config")
async def update_flux_config(
    scan_interval: Optional[int] = Query(None, ge=10, le=3600),
    trigger_type: Optional[str] = Query(None),
    interval_hours: Optional[int] = Query(None, ge=1, le=168),
    interval_days: Optional[int] = Query(None, ge=1, le=30),
    batch_size: Optional[int] = Query(None, ge=1, le=100),
    review_threshold: Optional[int] = Query(None, ge=1, le=500),
    max_trades_per_day: Optional[int] = Query(None, ge=1, le=100),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
) -> Dict[str, Any]:
    """Update Polymarket Manager configuration.
    
    All parameters are optional. Unspecified parameters retain current values.
    Config changes take effect immediately.
    
    Args:
        scan_interval: Seconds between market scans (10-3600)
        batch_size: Number of markets per scan (1-100)
        review_threshold: Markets cached before review (1-500)
        max_trades_per_day: Maximum trades per day (1-100)
        min_confidence: Minimum confidence to trade (0.0-1.0)
    
    Returns:
        Updated configuration
    """
    flux = await ensure_polymarket_manager()
    config = flux.config
    
    # Update config values if provided
    if scan_interval is not None:
        config.scan_interval = scan_interval
        flux.scan_interval = scan_interval
        flux.interval_hours = max(1, int(scan_interval / 3600))
        config.interval_hours = flux.interval_hours
    if interval_days is not None:
        interval_hours = interval_days * 24
    if interval_hours is not None:
        config.interval_hours = interval_hours
        flux.interval_hours = interval_hours
        config.scan_interval = interval_hours * 3600
        flux.scan_interval = config.scan_interval
    if trigger_type is not None:
        config.trigger_type = trigger_type
        flux.trigger_type = trigger_type
    if batch_size is not None:
        config.batch_size = batch_size
        flux.batch_size = batch_size
    if review_threshold is not None:
        config.review_threshold = review_threshold
        flux.review_threshold = review_threshold
    if max_trades_per_day is not None:
        config.max_trades_per_day = max_trades_per_day
        process_config_service.update_config({
            "trading_controls": {"max_trades_per_day": max_trades_per_day}
        })
    if min_confidence is not None:
        config.min_confidence = min_confidence
        # Keep trading controls aligned with confidence threshold
        if hasattr(process_config_service.get_workforce_config().trading_controls, "min_probability"):
            process_config_service.update_config({
                "trading_controls": {"min_probability": min_confidence}
            })
    
    log.info(
        "[POLYMARKET MANAGER API] Configuration updated: scan_interval=%s, batch_size=%s, "
        "max_trades_per_day=%s, min_confidence=%s",
        scan_interval,
        batch_size,
        max_trades_per_day,
        min_confidence,
    )

    # Persist trigger config changes for UI/settings
    if trigger_type is not None or interval_hours is not None or interval_days is not None:
        effective_interval_hours = interval_hours
        if effective_interval_hours is None and interval_days is not None:
            effective_interval_hours = interval_days * 24
        payload: Dict[str, Any] = {"trigger_config": {}}
        if trigger_type is not None:
            payload["trigger_config"]["trigger_type"] = trigger_type
        if effective_interval_hours is not None:
            payload["trigger_config"]["interval_hours"] = effective_interval_hours
        process_config_service.update_config(payload)
    
    return {
        "status": "updated",
        "message": "Polymarket Manager configuration updated",
        "config": {
            "scan_interval": config.scan_interval,
            "batch_size": config.batch_size,
            "review_threshold": config.review_threshold,
            "max_cache": config.max_cache,
            "max_trades_per_day": config.max_trades_per_day,
            "min_confidence": config.min_confidence,
            "trigger_type": config.trigger_type,
            "interval_hours": config.interval_hours,
        },
    }


# ============================================================================
# Positions & Results Endpoints
# ============================================================================


@router.get("/manager/positions")
@router.get("/flux/positions")
async def get_active_positions() -> Dict[str, Any]:
    """Get all currently active trading positions.
    
    Returns:
        Dict mapping position IDs to position details
    """
    flux = await ensure_polymarket_manager()
    positions = flux.get_active_positions()
    
    return {
        "count": len(positions),
        "positions": positions,
    }


@router.get("/manager/positions/{position_id}")
@router.get("/flux/positions/{position_id}")
async def get_position_details(position_id: str) -> Dict[str, Any]:
    """Get details for a specific position.
    
    Args:
        position_id: Position ID to retrieve
    
    Returns:
        Position details or 404 if not found
    """
    flux = await ensure_polymarket_manager()
    positions = flux.get_active_positions()
    
    if position_id not in positions:
        raise HTTPException(
            status_code=404,
            detail=f"Position {position_id} not found",
        )
    
    return {
        "position_id": position_id,
        "details": positions[position_id],
    }


@router.get("/manager/metrics")
@router.get("/flux/metrics")
async def get_flux_metrics() -> Dict[str, Any]:
    """Get flux performance metrics and statistics.
    
    Returns:
        Metrics dict with trades, positions, and cache stats
    """
    flux = await ensure_polymarket_manager()
    status = flux.get_status()
    
    return {
        "status": status,
        "cache_efficiency": {
            "cached_markets": len(flux._feed_cache),
            "active_positions": len(flux._active_positions),
            "trades_today": flux._trades_today,
            "max_trades_allowed": flux.config.max_trades_per_day,
        },
        "configuration": {
            "scan_interval_seconds": flux.config.scan_interval,
            "batch_size": flux.config.batch_size,
            "review_threshold": flux.config.review_threshold,
        },
    }


# ============================================================================
# Health & Diagnostics
# ============================================================================
@router.get("/manager/health")
@router.get("/flux/health")
async def flux_health_check() -> Dict[str, Any]:
    """Check Polymarket Manager service health.
    
    Returns:
        Health status with component information
    """
    flux = await ensure_polymarket_manager()
    
    health = {
        "status": "healthy",
        "running": flux._running,
        "workforce": {
            "connected": hasattr(flux.workforce, "agents"),
            "type": type(flux.workforce).__name__ if flux.workforce else "None",
        },
        "api_client": {
            "connected": flux.api_client is not None,
            "type": type(flux.api_client).__name__ if flux.api_client else "None",
        },
        "cache": {
            "ready": True,
            "path": str(flux.cache_path),
            "cached_markets": len(flux._feed_cache),
        },
        "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    }
    
    return health
