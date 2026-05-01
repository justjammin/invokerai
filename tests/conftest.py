import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def clean_spawn_token(tmp_path):
    """Remove spawn token before each test to avoid cross-test contamination."""
    from agent_invoker.mcp_server import _SPAWN_TOKEN
    _SPAWN_TOKEN.unlink(missing_ok=True)
    yield
    _SPAWN_TOKEN.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def clean_ledger():
    """Reset session ledger between tests."""
    from agent_invoker import mcp_server
    mcp_server._LEDGER.clear()
    yield
    mcp_server._LEDGER.clear()
