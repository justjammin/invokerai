"""Tests for Gas City integration: gc_client, handoff backend, get_crew_status."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_invoker.gc_client import (
    GcClient,
    GcError,
    _gc_cache,
    _sweep_tmp_personas,
    gc_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_gc_cache():
    _gc_cache.clear()


# ---------------------------------------------------------------------------
# gc_client() — availability probing
# ---------------------------------------------------------------------------

class TestGcClientAvailability:
    def setup_method(self):
        _reset_gc_cache()

    def teardown_method(self):
        _reset_gc_cache()

    def test_returns_none_when_gc_not_in_path(self):
        with patch("shutil.which", return_value=None):
            result = gc_client()
        assert result is None

    def test_returns_gc_client_when_gc_found(self):
        with patch("shutil.which", return_value="/usr/local/bin/gc"):
            result = gc_client()
        assert isinstance(result, GcClient)

    def test_ttl_cache_second_call_hits_cache(self):
        with patch("shutil.which", return_value="/usr/local/bin/gc") as mock_which:
            first = gc_client()
            second = gc_client()
        # shutil.which called exactly once because second call uses cache
        assert mock_which.call_count == 1
        assert first is second

    def test_ttl_cache_expired_re_probes(self):
        with patch("shutil.which", return_value="/usr/local/bin/gc") as mock_which:
            gc_client()
            # Force cache to look expired
            _gc_cache["ts"] = time.monotonic() - 400
            gc_client()
        assert mock_which.call_count == 2


# ---------------------------------------------------------------------------
# GcClient.run()
# ---------------------------------------------------------------------------

class TestGcClientRun:
    def _make_proc(self, returncode: int, stdout: str, stderr: str = ""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def test_raises_gc_error_on_nonzero_exit(self):
        client = GcClient()
        proc = self._make_proc(1, "", "something went wrong")
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(GcError) as exc_info:
                client.run(["bd", "show", "abc123"])
        err = exc_info.value
        assert err.exit_code == 1
        assert err.cmd == ["bd", "show", "abc123"]

    def test_returns_dict_on_valid_json_stdout(self):
        client = GcClient()
        payload = {"id": "abc", "status": "open"}
        proc = self._make_proc(0, json.dumps(payload))
        with patch("subprocess.run", return_value=proc):
            result = client.run(["bd", "show", "abc"])
        assert result == payload

    def test_returns_raw_on_non_json_stdout(self):
        client = GcClient()
        proc = self._make_proc(0, "not valid json at all")
        with patch("subprocess.run", return_value=proc):
            result = client.run(["bd", "list", "--json"])
        assert isinstance(result, dict)
        assert "raw" in result
        assert result["raw"] == "not valid json at all"

    def test_parse_json_false_returns_string(self):
        client = GcClient()
        proc = self._make_proc(0, "plain text output")
        with patch("subprocess.run", return_value=proc):
            result = client.run(["gc", "version"], parse_json=False)
        assert result == "plain text output"

    def test_gc_error_dataclass_fields(self):
        err = GcError(cmd=["gc", "mail"], exit_code=2, stdout="out", stderr="err")
        assert err.cmd == ["gc", "mail"]
        assert err.exit_code == 2
        assert err.stdout == "out"
        assert err.stderr == "err"

    def test_file_not_found_raises_gc_error_and_invalidates_cache(self):
        client = GcClient()
        _gc_cache["client"] = client
        _gc_cache["ts"] = time.monotonic()
        with patch("subprocess.run", side_effect=FileNotFoundError("gc not found")):
            with pytest.raises(GcError):
                client.run(["gc", "something"])
        # Cache should have been cleared by the invalidation
        assert not _gc_cache


# ---------------------------------------------------------------------------
# _sweep_tmp_personas()
# ---------------------------------------------------------------------------

class TestSweepTmpPersonas:
    def test_deletes_files_older_than_2h(self, tmp_path):
        old_file = tmp_path / "invokerai-sess1-step1.persona.md"
        old_file.write_text("old persona")
        # Set mtime to 3 hours ago
        old_mtime = time.time() - 10800
        import os
        os.utime(old_file, (old_mtime, old_mtime))

        _sweep_tmp_personas(tmp_dir=str(tmp_path))

        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        recent_file = tmp_path / "invokerai-sess2-step1.persona.md"
        recent_file.write_text("recent persona")
        # mtime is now (default) — well within 2h window

        _sweep_tmp_personas(tmp_dir=str(tmp_path))

        assert recent_file.exists()

    def test_ignores_non_matching_files(self, tmp_path):
        other_file = tmp_path / "something-else.txt"
        other_file.write_text("unrelated")
        old_mtime = time.time() - 10800
        import os
        os.utime(other_file, (old_mtime, old_mtime))

        _sweep_tmp_personas(tmp_dir=str(tmp_path))

        assert other_file.exists()

    def test_handles_empty_dir_gracefully(self, tmp_path):
        # Should not raise
        _sweep_tmp_personas(tmp_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# handoff_backend — legacy session default
# ---------------------------------------------------------------------------

class TestHandoffBackend:
    def test_legacy_session_defaults_to_file(self, tmp_path, monkeypatch):
        """Sessions with no handoff_backend key must default to 'file'."""
        import agent_invoker.core as core

        # Simulate a ledger with a session that has no handoff_backend
        ledger_path = tmp_path / "ledger.json"
        session_data = {
            "legacy-session": {
                "active_role": "backend-developer",
                "prior_routes": [],
                "last_seen": time.time(),
                # No "handoff_backend" key — legacy session
            }
        }
        ledger_path.write_text(json.dumps(session_data))
        monkeypatch.setattr(core, "_LEDGER_PATH", ledger_path)

        backend = core._get_session_handoff_backend("legacy-session")
        assert backend == "file"

    def test_new_session_gets_file_when_gc_unavailable(self, tmp_path, monkeypatch):
        import agent_invoker.core as core

        ledger_path = tmp_path / "ledger.json"
        monkeypatch.setattr(core, "_LEDGER_PATH", ledger_path)

        _reset_gc_cache()
        with patch("shutil.which", return_value=None):
            _reset_gc_cache()
            with patch("agent_invoker.gc_client.shutil.which", return_value=None):
                core.update_session("new-session", "backend-developer", "solo")

        data = json.loads(ledger_path.read_text())
        assert data["new-session"]["handoff_backend"] == "file"
        _reset_gc_cache()

    def test_new_session_gets_mail_when_gc_available(self, tmp_path, monkeypatch):
        import agent_invoker.core as core

        ledger_path = tmp_path / "ledger.json"
        monkeypatch.setattr(core, "_LEDGER_PATH", ledger_path)

        _reset_gc_cache()
        with patch("agent_invoker.gc_client.shutil.which", return_value="/usr/local/bin/gc"):
            _reset_gc_cache()
            core.update_session("gc-session", "backend-developer", "solo")

        data = json.loads(ledger_path.read_text())
        assert data["gc-session"]["handoff_backend"] == "mail"
        _reset_gc_cache()

    def test_handoff_backend_not_overwritten_on_second_call(self, tmp_path, monkeypatch):
        import agent_invoker.core as core

        ledger_path = tmp_path / "ledger.json"
        monkeypatch.setattr(core, "_LEDGER_PATH", ledger_path)

        _reset_gc_cache()
        with patch("agent_invoker.gc_client.shutil.which", return_value="/usr/local/bin/gc"):
            _reset_gc_cache()
            core.update_session("stable-session", "backend-developer", "solo")

        # Second call with gc unavailable — backend must remain "mail"
        _reset_gc_cache()
        with patch("agent_invoker.gc_client.shutil.which", return_value=None):
            _reset_gc_cache()
            core.update_session("stable-session", "frontend-developer", "crew")

        data = json.loads(ledger_path.read_text())
        assert data["stable-session"]["handoff_backend"] == "mail"
        _reset_gc_cache()


# ---------------------------------------------------------------------------
# get_crew_status — MCP tool
# ---------------------------------------------------------------------------

class TestGetCrewStatus:
    def test_returns_error_when_gc_unavailable(self, monkeypatch):
        import agent_invoker.mcp_server as srv

        monkeypatch.setattr(srv, "_gc_effective", lambda: None)
        result = srv.get_crew_status("bead-abc")
        assert "error" in result
        assert result["crew_root_bead_id"] == "bead-abc"

    def test_returns_crew_status_with_steps(self, monkeypatch):
        import agent_invoker.mcp_server as srv

        root_bead = {"id": "root-1", "title": "my crew", "status": "in_progress"}
        step_beads = [
            {"id": "step-1", "title": "backend-developer", "status": "closed", "claimed_at": "2026-01-01T00:00:00Z", "closed_at": "2026-01-01T01:00:00Z"},
            {"id": "step-2", "title": "code-reviewer", "status": "open", "claimed_at": None, "closed_at": None},
        ]

        mock_client = MagicMock()
        mock_client.run.side_effect = [root_bead, step_beads]
        monkeypatch.setattr(srv, "_gc_effective", lambda: mock_client)

        result = srv.get_crew_status("root-1")

        assert result["crew_id"] == "root-1"
        assert result["crew_status"] == "running"
        assert len(result["steps"]) == 2
        assert result["steps"][0]["status"] == "done"
        assert result["steps"][1]["status"] == "pending"

    def test_truncates_bead_id_to_max_task_len(self, monkeypatch):
        import agent_invoker.mcp_server as srv

        monkeypatch.setattr(srv, "_gc_effective", lambda: None)
        long_id = "x" * 10000
        result = srv.get_crew_status(long_id)
        assert len(result["crew_root_bead_id"]) <= srv.MAX_TASK_LEN


# ---------------------------------------------------------------------------
# INVOKERAI_GASCITY=off ignores gc even if binary is installed
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# persona_file written end-to-end through spawn_specialist
# ---------------------------------------------------------------------------

class TestPersonaFileWritten:
    def test_persona_file_set_in_result_when_gc_available(self, tmp_path, monkeypatch):
        """spawn_specialist must populate persona_file when gc is available."""
        import agent_invoker.mcp_server as srv
        import agent_invoker.core as core

        ledger_path = tmp_path / "ledger.json"
        monkeypatch.setattr(core, "_LEDGER_PATH", ledger_path)
        _reset_gc_cache()

        with patch("agent_invoker.gc_client.shutil.which", return_value="/usr/local/bin/gc"):
            _reset_gc_cache()
            result = srv.spawn_specialist(
                task="fix the bug in auth.py",
                session_id="persona-test-session",
            )

        persona_file = result.get("persona_file")
        assert persona_file is not None, "persona_file should be set when gc is available"
        assert Path(persona_file).exists(), f"persona temp file should exist at {persona_file}"
        content = Path(persona_file).read_text()
        assert len(content) > 0, "persona file must not be empty"
        _reset_gc_cache()

    def test_persona_file_none_when_gc_unavailable(self, tmp_path, monkeypatch):
        """spawn_specialist must not set persona_file when gc is absent."""
        import agent_invoker.mcp_server as srv
        import agent_invoker.core as core

        ledger_path = tmp_path / "ledger.json"
        monkeypatch.setattr(core, "_LEDGER_PATH", ledger_path)
        _reset_gc_cache()

        with patch("agent_invoker.gc_client.shutil.which", return_value=None):
            _reset_gc_cache()
            result = srv.spawn_specialist(
                task="fix the bug in auth.py",
                session_id="no-gc-session",
            )

        assert result.get("persona_file") is None
        _reset_gc_cache()


class TestGcEffectiveEnvVar:
    def test_off_returns_none_even_if_gc_installed(self, monkeypatch):
        import agent_invoker.mcp_server as srv

        monkeypatch.setattr(srv, "INVOKERAI_GASCITY", "off")
        _reset_gc_cache()
        with patch("agent_invoker.gc_client.shutil.which", return_value="/usr/local/bin/gc"):
            _reset_gc_cache()
            result = srv._gc_effective()
        assert result is None
        _reset_gc_cache()

    def test_on_returns_client_when_gc_installed(self, monkeypatch):
        import agent_invoker.mcp_server as srv

        monkeypatch.setattr(srv, "INVOKERAI_GASCITY", "on")
        _reset_gc_cache()
        with patch("agent_invoker.gc_client.shutil.which", return_value="/usr/local/bin/gc"):
            _reset_gc_cache()
            result = srv._gc_effective()
        assert isinstance(result, GcClient)
        _reset_gc_cache()

    def test_auto_logs_warning_once_on_first_gc_detection(self, monkeypatch, caplog):
        import agent_invoker.mcp_server as srv
        import logging

        monkeypatch.setattr(srv, "INVOKERAI_GASCITY", "auto")
        monkeypatch.setattr(srv, "_gc_auto_warned", False)
        _reset_gc_cache()

        with patch("agent_invoker.gc_client.shutil.which", return_value="/usr/local/bin/gc"):
            _reset_gc_cache()
            with caplog.at_level(logging.WARNING, logger="invokerai"):
                srv._gc_effective()
                srv._gc_effective()  # Second call must not log again

        warning_count = sum(
            1 for r in caplog.records
            if "Gas City detected" in r.message
        )
        assert warning_count == 1
        _reset_gc_cache()
