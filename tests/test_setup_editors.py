"""Tests for inject_agents_md() in setup_editors.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_invoker.setup_editors import (
    AGENTS_MD_MARKER_END,
    AGENTS_MD_MARKER_START,
    AGENTS_MD_NODE,
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
