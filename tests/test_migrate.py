"""Tests for migrate.py — hook purge logic."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from migrate import _is_old_hook, _purge_old_hooks


# ---------------------------------------------------------------------------
# _is_old_hook
# ---------------------------------------------------------------------------

class TestIsOldHook:
    def test_old_route_task_echo(self):
        hook = {"command": "echo mcp__invokerai__route_task something"}
        assert _is_old_hook(hook) is True

    def test_old_required_call_marker(self):
        hook = {"command": "echo REQUIRED: call mcp__invokerai to route"}
        assert _is_old_hook(hook) is True

    def test_old_confirm_specialist_marker(self):
        hook = {"command": "echo confirm correct specialist before spawning"}
        assert _is_old_hook(hook) is True

    def test_new_hook_not_flagged(self):
        hook = {"command": 'bash "/Users/user/.invokerai/hooks/pre-agent.sh"'}
        assert _is_old_hook(hook) is False

    def test_empty_command_not_flagged(self):
        hook = {"command": ""}
        assert _is_old_hook(hook) is False

    def test_missing_command_key_not_flagged(self):
        hook = {}
        assert _is_old_hook(hook) is False

    def test_unrelated_hook_not_flagged(self):
        hook = {"command": "echo Hello World"}
        assert _is_old_hook(hook) is False


# ---------------------------------------------------------------------------
# _purge_old_hooks
# ---------------------------------------------------------------------------

class TestPurgeOldHooks:
    def _make_settings(self, hooks: dict) -> dict:
        return {"hooks": hooks}

    def test_purges_old_route_task_hook(self):
        settings = self._make_settings({
            "PreToolUse": [
                {
                    "matcher": "Agent",
                    "hooks": [
                        {"command": "echo mcp__invokerai__route_task required"},
                    ],
                }
            ]
        })
        removed = _purge_old_hooks(settings)
        assert removed == 1
        assert settings["hooks"] == {}

    def test_keeps_new_hook(self):
        settings = self._make_settings({
            "PreToolUse": [
                {
                    "matcher": "Agent",
                    "hooks": [
                        {"command": 'bash "/home/user/.invokerai/hooks/pre-agent.sh"'},
                    ],
                }
            ]
        })
        removed = _purge_old_hooks(settings)
        assert removed == 0
        assert len(settings["hooks"]["PreToolUse"]) == 1

    def test_purges_old_keeps_new_in_same_event(self):
        settings = self._make_settings({
            "PreToolUse": [
                {
                    "matcher": "Agent",
                    "hooks": [
                        {"command": "echo mcp__invokerai__route_task"},
                        {"command": 'bash "/home/user/.invokerai/hooks/pre-agent.sh"'},
                    ],
                }
            ]
        })
        removed = _purge_old_hooks(settings)
        assert removed == 1
        hooks_left = settings["hooks"]["PreToolUse"][0]["hooks"]
        assert len(hooks_left) == 1
        assert "pre-agent.sh" in hooks_left[0]["command"]

    def test_drops_entry_when_all_hooks_purged(self):
        settings = self._make_settings({
            "PreToolUse": [
                {
                    "matcher": "Agent",
                    "hooks": [
                        {"command": "echo mcp__invokerai__route_task"},
                    ],
                }
            ]
        })
        _purge_old_hooks(settings)
        # Outer entry dropped since no hooks remain
        assert "PreToolUse" not in settings["hooks"]

    def test_removes_empty_event_lists(self):
        settings = self._make_settings({
            "PreToolUse": [],
            "UserPromptSubmit": [
                {
                    "matcher": "*",
                    "hooks": [{"command": 'bash "/home/user/.invokerai/hooks/pre-agent.sh"'}],
                }
            ],
        })
        _purge_old_hooks(settings)
        assert "PreToolUse" not in settings["hooks"]
        assert "UserPromptSubmit" in settings["hooks"]

    def test_no_hooks_key_returns_zero(self):
        settings: dict = {}
        removed = _purge_old_hooks(settings)
        assert removed == 0

    def test_multi_event_purge(self):
        settings = self._make_settings({
            "PreToolUse": [
                {
                    "matcher": "Agent",
                    "hooks": [{"command": "echo REQUIRED: call mcp__invokerai route task"}],
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "*",
                    "hooks": [{"command": "echo confirm correct specialist here"}],
                }
            ],
        })
        removed = _purge_old_hooks(settings)
        assert removed == 2
        assert settings["hooks"] == {}

    def test_idempotent_on_clean_settings(self):
        settings = self._make_settings({
            "PreToolUse": [
                {
                    "matcher": "Agent",
                    "hooks": [{"command": 'bash "/home/user/.invokerai/hooks/pre-agent.sh"'}],
                }
            ]
        })
        r1 = _purge_old_hooks(settings)
        r2 = _purge_old_hooks(settings)
        assert r1 == 0
        assert r2 == 0
