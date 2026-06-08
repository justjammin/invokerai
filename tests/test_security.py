"""Security regression tests for InvokerAI.

Covers:
1. _sanitize_session_id  — strips hostile chars, raises on empty result
2. _is_valid_role  — gates training-data writes to known registry entries
3. read_handoff / write_handoff  — path-traversal containment (end-to-end)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_invoker.core import (
    _is_valid_role,
    _sanitize_session_id,
    read_handoff,
    write_handoff,
)


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
# 2. _is_valid_role
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



