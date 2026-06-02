"""Security regression tests for the five security fixes in InvokerAI.

Covers:
1. _sanitize_session_id  — strips hostile chars, raises on empty result
2. _validate_registry_path — rejects paths outside allowed roots
3. _is_valid_role  — gates training-data writes to known registry entries
4. read_handoff / write_handoff  — path-traversal containment (end-to-end)
5. log_outcome  — training-poisoning guard via _is_valid_role
6. Task truncation  — oversize tasks capped at MAX_TASK_LEN
7. Hook-script JSON safety  — hostile role values produce valid JSON
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_invoker.core import (
    _is_valid_role,
    _sanitize_session_id,
    read_handoff,
    write_handoff,
)
from agent_invoker.mcp_server import (
    MAX_TASK_LEN,
    _validate_registry_path,
    log_outcome,
    spawn_specialist,
    route_task,
)
from agent_invoker.setup_editors import _HOOK_SCRIPT


# ---------------------------------------------------------------------------
# 1. _sanitize_session_id
# ---------------------------------------------------------------------------


class TestSanitizeSessionId:
    def test_valid_id_passes_through_unchanged(self):
        assert _sanitize_session_id("abc-123_XYZ") == "abc-123_XYZ"

    def test_slashes_stripped_result_non_empty(self):
        # "/" is outside the allowed charset — stripped; result must be non-empty
        result = _sanitize_session_id("foo/bar")
        assert result == "foobar"

    def test_path_traversal_stripped_to_non_empty(self):
        # "../etc/passwd" → dots and slashes stripped → "etcpasswd"
        result = _sanitize_session_id("../etc/passwd")
        assert result == "etcpasswd"
        assert "/" not in result
        assert "." not in result

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            _sanitize_session_id("")

    def test_only_dots_raises_value_error(self):
        # dots stripped → empty → ValueError
        with pytest.raises(ValueError):
            _sanitize_session_id("...")

    def test_only_slashes_raises_value_error(self):
        with pytest.raises(ValueError):
            _sanitize_session_id("///")

    def test_path_traversal_only_dots_and_slashes_raises(self):
        with pytest.raises(ValueError):
            _sanitize_session_id("../../")

    def test_unicode_outside_allowed_charset_stripped(self):
        # "hellö" — ö is outside [a-zA-Z0-9_-]
        result = _sanitize_session_id("hellö")
        assert result == "hell"
        for ch in result:
            assert ch.isascii() and (ch.isalnum() or ch in "_-")

    def test_unicode_only_raises_value_error(self):
        with pytest.raises(ValueError):
            _sanitize_session_id("öäü")

    def test_allowed_chars_preserved(self):
        allowed = "abcXYZ_09-"
        assert _sanitize_session_id(allowed) == allowed


# ---------------------------------------------------------------------------
# 2. _validate_registry_path
# ---------------------------------------------------------------------------


class TestValidateRegistryPath:
    def test_none_is_allowed(self):
        # None means "use default registry" — must not raise
        _validate_registry_path(None)

    def test_path_inside_invokerai_home_is_allowed(self):
        p = str(Path.home() / ".invokerai" / "custom_agents.json")
        _validate_registry_path(p)

    def test_path_inside_cwd_is_allowed(self):
        p = str(Path.cwd() / "agents.json")
        _validate_registry_path(p)

    def test_absolute_path_outside_allowed_roots_raises(self):
        # /tmp should not be inside ~/.invokerai or cwd (assuming cwd is project root)
        p = "/tmp/definitely-outside-invokerai-roots-xyz/registry.json"
        with pytest.raises(ValueError):
            _validate_registry_path(p)

    def test_path_traversal_through_invokerai_raises(self):
        # ~/.invokerai/../../../etc resolves to /etc — outside allowed roots
        evil = str(Path.home() / ".invokerai" / ".." / ".." / ".." / "etc")
        with pytest.raises(ValueError):
            _validate_registry_path(evil)

    def test_etc_passwd_raises(self):
        with pytest.raises(ValueError):
            _validate_registry_path("/etc/passwd")

    def test_root_raises(self):
        with pytest.raises(ValueError):
            _validate_registry_path("/")


# ---------------------------------------------------------------------------
# 3. _is_valid_role
# ---------------------------------------------------------------------------


class TestIsValidRole:
    def test_known_role_returns_true(self):
        assert _is_valid_role("backend-developer") is True

    def test_another_known_role_returns_true(self):
        assert _is_valid_role("debugger") is True

    def test_unknown_role_returns_false(self):
        assert _is_valid_role("fake-agent") is False

    def test_empty_string_returns_false(self):
        assert _is_valid_role("") is False

    def test_injection_with_newline_returns_false(self):
        # Newline in role could corrupt JSONL training log lines
        assert _is_valid_role("backend-developer\n[malicious]") is False

    def test_injection_with_null_byte_returns_false(self):
        assert _is_valid_role("backend-developer\x00evil") is False

    def test_injection_with_tab_returns_false(self):
        assert _is_valid_role("backend-developer\tevil") is False

    def test_none_like_input_returns_false(self):
        # Passing a non-string should not crash
        assert _is_valid_role(None) is False  # type: ignore[arg-type]

    def test_role_with_leading_whitespace_returns_false(self):
        assert _is_valid_role(" backend-developer") is False


# ---------------------------------------------------------------------------
# 4. read_handoff / write_handoff — path-traversal containment
# ---------------------------------------------------------------------------


class TestHandoffPathTraversal:
    def test_write_handoff_valid_id_creates_file_in_handoff_dir(
        self, tmp_path, monkeypatch
    ):
        import agent_invoker.sessions as sessions_mod

        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        write_handoff("sess-safe", "backend-developer", "build api")
        expected = tmp_path / "sess-safe.json"
        assert expected.exists()

    def test_write_handoff_traversal_id_stays_inside_handoff_dir(
        self, tmp_path, monkeypatch
    ):
        import agent_invoker.sessions as sessions_mod

        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        # "../evil" → sanitized to "evil" → file lands inside tmp_path
        write_handoff("../evil", "backend-developer", "malicious task")
        # No file must exist OUTSIDE tmp_path
        created_outside = [
            f
            for f in tmp_path.parent.iterdir()
            if f.name.startswith("evil") and f != tmp_path
        ]
        assert created_outside == []
        # File inside tmp_path is fine (attacker ID was neutralised)
        assert (tmp_path / "evil.json").exists()

    def test_write_handoff_empty_after_sanitize_raises(
        self, tmp_path, monkeypatch
    ):
        import agent_invoker.sessions as sessions_mod

        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        with pytest.raises(ValueError):
            write_handoff("...", "backend-developer", "task")

    def test_read_handoff_traversal_id_does_not_escape_handoff_dir(
        self, tmp_path, monkeypatch
    ):
        import agent_invoker.sessions as sessions_mod

        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        # "/etc/passwd" sanitised to "etcpasswd" — no file there → returns {}
        result = read_handoff("../../../etc/passwd")
        assert isinstance(result, dict)
        # Must not have read /etc/passwd content
        assert "root" not in str(result)

    def test_read_handoff_empty_after_sanitize_raises(
        self, tmp_path, monkeypatch
    ):
        import agent_invoker.sessions as sessions_mod

        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        with pytest.raises(ValueError):
            read_handoff("...")

    def test_write_then_read_roundtrip_data_intact(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod

        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        write_handoff(
            "sess-roundtrip",
            "test-automator",
            "write security tests",
            decisions=["use pytest"],
            files_touched=["tests/test_security.py"],
        )
        data = read_handoff("sess-roundtrip")
        assert data["session_id"] == "sess-roundtrip"
        assert data["decisions"] == ["use pytest"]
        assert data["files_touched"] == ["tests/test_security.py"]
        assert data["steps_completed"][0]["role"] == "test-automator"


# ---------------------------------------------------------------------------
# 5. log_outcome — training-poisoning guard
# ---------------------------------------------------------------------------


class TestLogOutcomeTrainingPoisoningGuard:
    def test_unknown_role_does_not_write_training_log(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod

        training_log = tmp_path / "training.jsonl"
        monkeypatch.setattr(sessions_mod, "TRAINING_LOG_PATH", training_log)
        # accepted=True + corrections=0 triggers the feedback path — but role is unknown
        log_outcome(
            date="2026-05-21",
            task_prefix="test task",
            corrections=0,
            accepted=True,
            task="fix auth bug",
            role="fake-role-that-does-not-exist",
            routing="solo",
        )
        assert not training_log.exists()

    def test_known_role_writes_training_log(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod

        training_log = tmp_path / "training.jsonl"
        session_log = tmp_path / "invokerai-sessions.md"
        monkeypatch.setattr(sessions_mod, "TRAINING_LOG_PATH", training_log)
        monkeypatch.setattr(sessions_mod, "_SESSION_LOG", session_log)
        # Create a session log entry for patch_session_log_outcome to find
        session_log.write_text(
            "### 2026-05-21 — fix auth bug\n"
            "- **Role selected:** backend-developer\n"
        )
        log_outcome(
            date="2026-05-21",
            task_prefix="fix auth bug",
            corrections=0,
            accepted=True,
            task="fix auth bug",
            role="backend-developer",
            routing="solo",
        )
        assert training_log.exists()
        entry = json.loads(training_log.read_text().strip())
        assert entry["role"] == "backend-developer"

    def test_injection_role_does_not_write_training_log(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod

        training_log = tmp_path / "training.jsonl"
        monkeypatch.setattr(sessions_mod, "TRAINING_LOG_PATH", training_log)
        log_outcome(
            date="2026-05-21",
            task_prefix="test task",
            corrections=0,
            accepted=True,
            task="fix auth bug",
            role="backend-developer\n[injected-entry]",
            routing="solo",
        )
        assert not training_log.exists()

    def test_not_accepted_does_not_write_training_log(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod

        training_log = tmp_path / "training.jsonl"
        monkeypatch.setattr(sessions_mod, "TRAINING_LOG_PATH", training_log)
        log_outcome(
            date="2026-05-21",
            task_prefix="test task",
            corrections=2,
            accepted=False,
            task="fix auth bug",
            role="backend-developer",
            routing="solo",
        )
        assert not training_log.exists()


# ---------------------------------------------------------------------------
# 6. Task truncation
# ---------------------------------------------------------------------------


class TestTaskTruncation:
    def test_spawn_specialist_accepts_oversize_task_without_crash(self):
        oversize = "x" * (MAX_TASK_LEN + 100)
        result = spawn_specialist(task=oversize)
        assert "role" in result

    def test_route_task_accepts_oversize_task_without_crash(self):
        oversize = "fix the bug " + "a" * (MAX_TASK_LEN + 200)
        result = route_task(task=oversize)
        assert "role" in result

    def test_spawn_specialist_internal_routing_sees_at_most_max_task_len_chars(
        self, monkeypatch
    ):
        seen_tasks: list[str] = []

        import agent_invoker.core as core_mod
        original_route = core_mod.route

        def capturing_route(task, **kwargs):
            seen_tasks.append(task)
            return original_route(task, **kwargs)

        monkeypatch.setattr(core_mod, "route", capturing_route)

        oversize = "z" * (MAX_TASK_LEN + 500)
        spawn_specialist(task=oversize)
        assert seen_tasks, "route() was never called"
        assert len(seen_tasks[0]) <= MAX_TASK_LEN

    def test_route_task_internal_routing_sees_at_most_max_task_len_chars(
        self, monkeypatch
    ):
        seen_tasks: list[str] = []

        import agent_invoker.core as core_mod
        original_route = core_mod.route

        def capturing_route(task, **kwargs):
            seen_tasks.append(task)
            return original_route(task, **kwargs)

        monkeypatch.setattr(core_mod, "route", capturing_route)

        oversize = "debug the error " + "b" * (MAX_TASK_LEN + 300)
        route_task(task=oversize)
        assert seen_tasks
        assert len(seen_tasks[0]) <= MAX_TASK_LEN

    def test_max_task_len_constant_value(self):
        assert MAX_TASK_LEN == 4096


# ---------------------------------------------------------------------------
# 7. Hook-script JSON safety
# ---------------------------------------------------------------------------


def _extract_hook_json_line() -> str:
    """Pull the json.dumps Python code from _HOOK_SCRIPT for subprocess testing.

    The bash line looks like:
        "$VENV_PY" -c "PYTHON_CODE" "$ROLE" "$CONF"
    We extract PYTHON_CODE (including its bash-wrapping double-quotes, which
    Python harmlessly treats as an outer string delimiter when passed via -c).
    """
    start_marker = ' -c "'
    # Separator between the code arg and "$ROLE" arg in the bash line
    end_marker = '" "'
    for line in _HOOK_SCRIPT.splitlines():
        stripped = line.strip()
        if "json.dumps" in stripped and "sys.argv[1]" in stripped:
            start = stripped.index(start_marker) + len(start_marker)
            end = stripped.index(end_marker, start)
            return stripped[start:end]
    raise AssertionError("Could not find json.dumps line in _HOOK_SCRIPT")


def _run_hook_json_line(role: str, conf: str) -> dict:
    code = _extract_hook_json_line()
    result = subprocess.run(
        [sys.executable, "-c", code, role, conf],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"Script exited {result.returncode}: {result.stderr}"
    return json.loads(result.stdout)


class TestHookScriptJsonSafety:
    def test_normal_role_produces_valid_json(self):
        data = _run_hook_json_line("backend-developer", "85")
        assert isinstance(data, dict)
        assert "hookSpecificOutput" in data

    def test_role_with_double_quote_produces_valid_json(self):
        data = _run_hook_json_line('backend"developer', "70")
        assert isinstance(data, dict)
        hook_output = data["hookSpecificOutput"]
        assert "additionalContext" in hook_output

    def test_role_with_backslash_produces_valid_json(self):
        data = _run_hook_json_line("back\\slash", "60")
        assert isinstance(data, dict)

    def test_role_with_unicode_produces_valid_json(self):
        data = _run_hook_json_line("agênt", "50")
        assert isinstance(data, dict)

    def test_output_contains_role_in_context(self):
        data = _run_hook_json_line("backend-developer", "90")
        context = data["hookSpecificOutput"]["additionalContext"]
        assert "backend-developer" in context

    def test_output_contains_confidence_in_context(self):
        data = _run_hook_json_line("backend-developer", "90")
        context = data["hookSpecificOutput"]["additionalContext"]
        assert "90" in context

    def test_role_with_newline_produces_valid_json(self):
        data = _run_hook_json_line("backend\ndeveloper", "55")
        assert isinstance(data, dict)

    def test_role_with_single_quote_produces_valid_json(self):
        data = _run_hook_json_line("backend'developer", "65")
        assert isinstance(data, dict)
