# Contributing

Thanks for contributing. This guide keeps contributions consistent and reviewable.

## Prerequisites

- Python 3.11+
- Git
- Optional: Docker + Docker Compose (for full stack/local infra testing)

## Setup

```bash
git clone <your-fork-or-repo-url>
cd agentic-system-trading
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp env.example .env
```

## Branch and Commit Workflow

1. Create a focused branch from `main`.
2. Keep changes scoped (feature, bugfix, or docs update).
3. Add/update tests when behavior changes.
4. Run quality checks before opening a PR.

## Quality Checks

Run these from repository root:

```bash
ruff check .
black --check .
isort --check-only .
mypy .
pytest
```

If formatting fails, run:

```bash
black .
isort .
```

## Running the App Locally

```bash
uvicorn api.main:app --reload
```

Useful endpoints:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/ui`

## Project Structure

```text
api/                  FastAPI app, routers, middleware, API services
core/                 Runtime, workforce, trading/domain logic
frontend/             Static UI assets
scripts/              Utility scripts (MCP server, trade CLI, exports)
tests/                Unit/integration tests
.github/workflows/    CI and lint/test workflows
```

## Pull Request Checklist

- [ ] Clear PR title and description with problem/solution summary.
- [ ] Related issue linked (if applicable).
- [ ] Tests added/updated and passing locally.
- [ ] Lint/type checks passing locally.
- [ ] Docs updated for any user-facing behavior/config changes.

## Notes

- Never commit secrets (`.env`, private keys, API tokens).
- Prefer small, incremental PRs over large mixed changes.
- Keep API/behavior changes backwards-compatible when practical, or document breaking changes clearly.
