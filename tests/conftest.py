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
def clean_ledger(tmp_path, monkeypatch):
    """Redirect ledger to a temp file so tests don't touch real user state."""
    test_ledger = tmp_path / "ledger.json"
    monkeypatch.setattr("agent_invoker.core._LEDGER_PATH", test_ledger)
    yield
    if test_ledger.exists():
        test_ledger.unlink()
