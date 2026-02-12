# Quickstart

This guide gets the API and UI running locally with either a Python environment or Docker Compose.

## Prerequisites

- Python 3.11+
- Git
- Pip
- Optional: Docker + Docker Compose

## 1) Clone and Configure

```bash
git clone <repo-url>
cd agentic-system-trading
cp env.example .env
```

Update `.env` with the credentials/configuration you need.

## 2) Option A: Local Python Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn api.main:app --reload
```

App endpoints:

- API root: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- UI: `http://localhost:8000/ui`
- Health: `http://localhost:8000/health`

## 3) Option B: Docker Compose Run

```bash
docker compose up --build
```

This starts the API plus supporting services defined in `docker-compose.yml` (Redis, Qdrant, Ollama, Neo4j).

## Trigger Modes (UI)

- `Manual`: immediate run; bypasses RSS cache thresholds/trade-limit checks.
- `Interval`: scheduled run; enforces thresholds, verification, and limits.

Configure trigger mode and interval cadence in the Workforce UI.

## Optional: Run Workforce MCP Server

Run separately when you want an MCP endpoint:

```bash
python scripts/workforce_mcp_server.py
```

Default bind:

- `0.0.0.0:8001`

Set `MCP_HOST` / `MCP_PORT` in your environment to change it.

## Basic Development Checks

```bash
pytest
ruff check .
```

## Troubleshooting

- If startup fails, verify `.env` values first.
- If dependency install fails, remove and recreate `.venv`.
- If containers fail, run `docker compose logs <service>` to inspect service-specific errors.
