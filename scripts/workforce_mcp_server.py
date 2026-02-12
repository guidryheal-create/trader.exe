#!/usr/bin/env python3
"""Standalone MCP server runner for the CAMEL workforce.

Runs outside FastAPI to avoid event loop/thread coupling.
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Any, List

from core.camel_runtime import CamelTradingRuntime
from core.logging import log


def _parse_list(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


async def _build_and_run() -> None:
    name = os.getenv("MCP_NAME", "CAMEL-Workforce")
    description = os.getenv("MCP_DESCRIPTION", "A workforce system using the CAM multi-agent collaboration.")
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8001"))
    dependencies = _parse_list(os.getenv("MCP_DEPENDENCIES"))

    runtime = await CamelTradingRuntime.instance()
    workforce = await runtime.get_workforce()

    if not hasattr(workforce, "to_mcp"):
        raise RuntimeError("Workforce does not support to_mcp().")

    mcp = workforce.to_mcp(
        name=name,
        description=description,
        dependencies=dependencies or None,
        host=host,
        port=port,
    )

    serve_method = getattr(mcp, "serve", None)
    run_method = getattr(mcp, "run", None)
    if callable(serve_method):
        if asyncio.iscoroutinefunction(serve_method):
            log.info("Starting MCP server (async serve) on %s:%s", host, port)
            await serve_method()
        else:
            log.info("Starting MCP server (threaded serve) on %s:%s", host, port)
            thread = threading.Thread(target=serve_method, daemon=False)
            thread.start()
            thread.join()
    elif callable(run_method):
        log.info("Starting MCP server (threaded run) on %s:%s", host, port)
        thread = threading.Thread(target=run_method, daemon=False)
        thread.start()
        thread.join()
    else:
        raise RuntimeError("MCP instance does not expose serve() or run().")


def main() -> None:
    asyncio.run(_build_and_run())


if __name__ == "__main__":
    main()
