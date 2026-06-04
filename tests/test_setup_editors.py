"""Tests for inject_agents_md() and injection-surface content in setup_editors.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_invoker.setup_editors import (
    AGENTS_MD_MARKER_END,
    AGENTS_MD_MARKER_START,
    AGENTS_MD_NODE,
    _INVOKERAI_NODE_BODY,
    _PROMPT_HOOK_COMMAND,
    _SUBAGENT_HOOK_COMMAND,
    inject_agents_md,
)


def test_inject_agents_md_creates_when_no_file(tmp_path: Path) -> None:
    agents_md = tmp_path / "AGENTS.md"
    result = inject_agents_md(agents_md)
    assert result is True
    assert agents_md.exists()
    assert "INVOKERAI-START" in agents_md.read_text()


def test_inject_agents_md_appends_when_file_exists(tmp_path: Path) -> None:
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("")

    result = inject_agents_md(agents_md)

    assert result is True
    content = agents_md.read_text()
    assert AGENTS_MD_MARKER_START in content
    assert AGENTS_MD_MARKER_END in content


def test_inject_agents_md_updates_existing_block(tmp_path: Path) -> None:
    agents_md = tmp_path / "AGENTS.md"
    stale = (
        "# Project\n\n"
        "<!-- INVOKERAI-START -->\n"
        "## Old stale content\n"
        "<!-- INVOKERAI-END -->\n"
    )
    agents_md.write_text(stale)

    result = inject_agents_md(agents_md)

    assert result is True
    content = agents_md.read_text()
    assert "Old stale content" not in content
    assert AGENTS_MD_NODE in content


def test_inject_agents_md_idempotent(tmp_path: Path) -> None:
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Project\n")

    inject_agents_md(agents_md)
    inject_agents_md(agents_md)

    content = agents_md.read_text()
    assert content.count(AGENTS_MD_MARKER_START) == 1
    assert content.count(AGENTS_MD_MARKER_END) == 1


def test_inject_agents_md_creates_parent_dir(tmp_path: Path) -> None:
    agents_md = tmp_path / "subdir" / "AGENTS.md"
    result = inject_agents_md(agents_md)
    assert result is True
    assert agents_md.exists()


# ---------------------------------------------------------------------------
# Injection surface content: MCP-free, invoker-spawn present
# ---------------------------------------------------------------------------

MCP_SYMBOLS = ["mcp__invokerai__spawn_specialist", "mcp__invokerai__confirm_route", "spawn_specialist"]


class TestInjectionSurfaceContent:
    def test_node_body_references_invoker_spawn(self):
        assert "invoker spawn" in _INVOKERAI_NODE_BODY

    def test_node_body_has_no_mcp_symbols(self):
        for sym in MCP_SYMBOLS:
            assert sym not in _INVOKERAI_NODE_BODY, f"Found MCP symbol in node body: {sym}"

    def test_prompt_hook_references_invoker_spawn(self):
        assert "invoker spawn" in _PROMPT_HOOK_COMMAND

    def test_prompt_hook_has_no_mcp_symbols(self):
        for sym in MCP_SYMBOLS:
            assert sym not in _PROMPT_HOOK_COMMAND, f"Found MCP symbol in prompt hook: {sym}"

    def test_subagent_hook_references_invoker_spawn(self):
        assert "invoker spawn" in _SUBAGENT_HOOK_COMMAND

    def test_subagent_hook_has_no_mcp_symbols(self):
        for sym in MCP_SYMBOLS:
            assert sym not in _SUBAGENT_HOOK_COMMAND, f"Found MCP symbol in subagent hook: {sym}"

    def test_node_body_skill_never_spawns(self):
        # Skill plans; host spawns — not the other way around.
        assert "Spawn the returned agents yourself" in _INVOKERAI_NODE_BODY

    def test_node_body_bd_optional(self):
        # bd/beads mentioned only as optional
        assert "Optional" in _INVOKERAI_NODE_BODY
        assert "bd" in _INVOKERAI_NODE_BODY
