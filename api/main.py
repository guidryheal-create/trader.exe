"""
Polymarket Trading Bot - Standalone API
Separate from forecasting API, focused only on Polymarket prediction market trading
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import logging
from api.middleware.session import SessionAuthMiddleware
from core.camel_runtime import CamelTradingRuntime
from core.camel_runtime.registries import toolkit_registry
from api.services.polymarket.config_service import process_config_service
from api.routers.polymarket.rss_flux import ensure_polymarket_manager
from api.services.dex import dex_manager_service
from api.router_registry import get_router_bindings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Polymarket Trading Bot API",
    description="Agentic trading system for Polymarket prediction markets",
    version="0.1.0",
)

@app.on_event("startup")
async def startup_event():
    """
    Application startup event.
    Initializes the CamelTradingRuntime.
    """
    logger.info("Application startup: Initializing CamelTradingRuntime...")
    await CamelTradingRuntime.instance()
    logger.info("CamelTradingRuntime initialized.")
    try:
        await toolkit_registry.ensure_clients()
        logger.info("Shared toolkit registry initialized.")
    except Exception as exc:
        logger.warning("Shared toolkit registry initialization failed: %s", exc)
    try:
        config = process_config_service.get_config()
        if config.get("active_flux") in {"polymarket_manager", "polymarket_rss_flux"}:
            flux = await ensure_polymarket_manager()
            if flux.trigger_type == "interval" and not flux._running:
                await flux.start()
                logger.info("Polymarket Manager started on startup (interval trigger).")
    except Exception as exc:
        logger.warning("Polymarket Manager startup init failed: %s", exc)
    try:
        await dex_manager_service.auto_start_if_enabled()
    except Exception as exc:
        logger.warning("DEX trader startup init failed: %s", exc)

# Static assets for Jinja UI
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Attach session middleware so request.state.session is available
app.add_middleware(SessionAuthMiddleware)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "polymarket-trading-bot",
            "version": "0.1.0",
        },
    )


@app.get("/")
async def root():
    """Root endpoint redirects to UI menu."""
    return RedirectResponse(url="/ui", status_code=307)


for binding in get_router_bindings():
    app.include_router(binding.router, prefix=binding.prefix, tags=list(binding.tags))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
