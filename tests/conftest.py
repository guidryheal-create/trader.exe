"""Test configuration and fixtures.

This conftest loads optional .env variables (project root .env), exposes CLI
options for docker host and mock mode, and provides fixtures used across the
Polymarket-focused tests. Collection pruning to a small set of Polymarket tests
is now opt-in via the --polymarket-standalone flag or POLYMARKET_STANDALONE env.
"""

from pathlib import Path
import os
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # don't override existing env vars
        if k not in os.environ:
            os.environ[k] = v


# Load .env from repository root if present
_load_dotenv(ROOT / '.env')

# Sanitize env vars that may contain inline comments (e.g. "80002 #137").
# Some CI or shell exports accidentally include comments which break pydantic int parsing.
for _k, _v in list(os.environ.items()):
    if isinstance(_v, str) and '#' in _v:
        cleaned = _v.split('#', 1)[0].strip()
        if cleaned != _v:
            os.environ[_k] = cleaned


# Optionally stub heavy native-extension modules to avoid segfaults in CI
# Set TEST_DISABLE_EXT=1 or USE_MOCKS=1 to enable.
_disable_ext = os.environ.get('TEST_DISABLE_EXT') in ('1', 'true', 'yes') or os.environ.get('USE_MOCKS') in ('1', 'true', 'yes')
if _disable_ext:
    import types, sys

    def _stub(name):
        if name in sys.modules:
            return
        m = types.ModuleType(name)
        # provide a minimal attribute set commonly used
        m.__all__ = []
        sys.modules[name] = m

    # modules that have caused segfaults in some environments
    for mod in [
        'pyarrow',
        'pyarrow.lib',
        'pandas',
        'pandas.compat.pyarrow',
        'neo4j',
        'neo4j._async',
        'neo4j._async.io',
        'ckzg',
    ]:
        try:
            _stub(mod)
        except Exception:
            pass


ALLOWED_FILES = {
    # API Endpoint Tests
    "tests/test_api_polymarket_config_logs_trades.py",
    "tests/test_api_polymarket_settings_results.py",
    # Workforce & Orchestration
    "tests/test_polymarket_workflow.py",
    # Toolkit Tests
    "tests/test_polymarket_toolkit.py",
    # Service Tests
    "tests/test_polymarket_trade_service.py",
    # Pipeline Tests
    "tests/test_polymarket_rss_flux_cycle.py",
    # MCP Client
    "tests/test_forecasting_mcp_client.py",
}


def pytest_addoption(parser):
    parser.addoption(
        "--docker-host",
        action="store",
        default=os.environ.get('DOCKER_HOST_URL') or os.environ.get('TEST_DOCKER_HOST') or 'http://localhost:8000',
        help="Docker host base URL for integration tests (overrides .env)",
    )
    parser.addoption(
        "--use-mock",
        action="store_true",
        default=os.environ.get('USE_MOCKS', '0') in ('1', 'true', 'yes'),
        help="Run tests using internal mocks instead of external services",
    )
    parser.addoption(
        "--polymarket-standalone",
        action="store_true",
        default=os.environ.get('POLYMARKET_STANDALONE', '0') in ('1', 'true', 'yes'),
        help="Run only essential Polymarket-focused tests (legacy behavior)",
    )


@pytest.fixture(scope='session')
def docker_host(request):
    return request.config.getoption('--docker-host')


@pytest.fixture(scope='session')
def use_mocks(request):
    return request.config.getoption('--use-mock')


@pytest.fixture(scope='session')
def use_real_services(request, docker_host):
    """Whether tests should talk to real services (docker_host) or not.

    Controlled by --use-mock flag (or USE_MOCKS env). If docker_host is a
    placeholder like http://localhost:8000 it's still considered a real host
    (user expected to run docker-compose). Tests should use this fixture to
    decide whether to call external services or use internal mocks.
    """
    return not request.config.getoption('--use-mock')


def pytest_collection_modifyitems(config, items):
    """Optionally prune the test collection to Polymarket-only tests.

    This behavior is now opt-in via the CLI flag `--polymarket-standalone` or
    env var `POLYMARKET_STANDALONE`. By default the full test suite runs.
    """
    standalone = config.getoption('--polymarket-standalone')
    if not standalone:
        return

    keep = []
    skip = []
    for item in items:
        path = str(item.fspath)
        if any(path.endswith(fname) for fname in ALLOWED_FILES):
            keep.append(item)
        else:
            skip.append(item)

    if skip:
        marker = pytest.mark.skip(reason="Skipped non-Polymarket tests for standalone focus")
        for item in skip:
            item.add_marker(marker)

