# Agentic Trading System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Agentic trading platform for Polymarket, built around a collaborative AI workforce, configurable signal pipelines, and a FastAPI control surface.

## What It Does

- Runs an agentic workforce that can analyze markets and generate trading actions.
- Integrates external context sources (including RSS/news workflows) into decision-making.
- Exposes API routes and UI pages for monitoring, settings, logs, decisions, and execution controls.
- Supports manual and interval trigger modes for RSS/workforce flows.
- Can run as a local API service or via Docker Compose with Redis, Qdrant, Ollama, and Neo4j.

## Repository Layout

- `api/`: FastAPI application, route registry, routers, middleware, API services.
- `core/`: runtime, workforce logic, exchange/tool integrations, shared services.
- `frontend/`: static UI assets served by the API.
- `scripts/`: operational utilities (trade CLI, MCP server runner, export/pruning tools).
- `tests/`: unit/integration test coverage.

## Quick Start

For full setup, see [`QUICKSTART.md`](QUICKSTART.md).

Minimal local run (from repository root):

```bash
cp env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn api.main:app --reload
```

Then open:

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- UI: `http://localhost:8000/ui`

## Trigger Modes

- `Manual`: Runs immediately, bypassing RSS cache thresholds and trade-limit checks.
- `Interval`: Runs on schedule (hours/days), enforcing cache thresholds, verification, and limits.

Configure mode and cadence from the Workforce UI.

## MCP Server (Optional)

You can expose the workforce as an MCP server:

```bash
python scripts/workforce_mcp_server.py
```

Defaults:

- Host: `0.0.0.0`
- Port: `8001`

Override with `MCP_HOST` and `MCP_PORT` in your environment.

## Development Status

Active development is ongoing. See [`TODO.md`](TODO.md) for near-term priorities.

## Contributing

Contribution workflow and standards are documented in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE).
