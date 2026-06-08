"""Tests for agent_invoker.agent_map.build_agent_map."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_invoker.agent_map import _parse_frontmatter, _normalize_tools, build_agent_map


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_inline_tools_string(self):
        text = "---\nname: my-agent\ntools: Read, Write, Edit\n---\nbody"
        fm = _parse_frontmatter(text)
        assert fm is not None
        assert fm["name"] == "my-agent"
        assert fm["tools"] == "Read, Write, Edit"

    def test_list_tools(self):
        text = "---\nname: my-agent\ntools:\n  - Read\n  - Write\n---\nbody"
        fm = _parse_frontmatter(text)
        assert fm is not None
        assert fm["tools"] == ["Read", "Write"]

    def test_missing_frontmatter_returns_none(self):
        text = "No frontmatter here at all."
        assert _parse_frontmatter(text) is None

    def test_frontmatter_without_closing_marker_returns_none(self):
        text = "---\nname: broken\nno closing marker"
        assert _parse_frontmatter(text) is None

    def test_empty_file_returns_none(self):
        assert _parse_frontmatter("") is None


class TestNormalizeTools:
    def test_comma_string(self):
        assert _normalize_tools("Read, Write, Edit") == ["Read", "Write", "Edit"]

    def test_list_form(self):
        assert _normalize_tools(["Read", "Write"]) == ["Read", "Write"]

    def test_none_returns_empty(self):
        assert _normalize_tools(None) == []

    def test_no_spaces(self):
        assert _normalize_tools("Read,Write,Bash") == ["Read", "Write", "Bash"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_agent(agents_dir: Path, name: str, description: str, tools: str = "Read", model: str = "sonnet") -> None:
    (agents_dir / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: \"{description}\"\ntools: {tools}\nmodel: {model}\n---\nBody.",
        encoding="utf-8",
    )


def _write_agent_list_tools(agents_dir: Path, name: str, description: str, tools: list[str]) -> None:
    tools_yaml = "\n".join(f"  - {t}" for t in tools)
    (agents_dir / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: \"{description}\"\ntools:\n{tools_yaml}\nmodel: sonnet\n---\nBody.",
        encoding="utf-8",
    )


def _write_no_frontmatter(agents_dir: Path, name: str) -> None:
    (agents_dir / f"{name}.md").write_text("No frontmatter, just body text.", encoding="utf-8")


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassification:
    def test_name_match_backend(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent(
            agents_dir,
            "backend-developer",
            "Builds REST APIs and microservices",
        )
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        backend_entries = result["domains"].get("backend", [])
        assert any(e["name"] == "backend-developer" for e in backend_entries)
        entry = next(e for e in backend_entries if e["name"] == "backend-developer")
        assert entry["source"] == "name"

    def test_description_fallback_classifies_backend(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        # Name not in _ROLE_DOMAIN, description clearly backend
        _write_agent(
            agents_dir,
            "my-custom-server-agent",
            "Designs REST API endpoints and server-side business logic for microservices",
        )
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        backend_entries = result["domains"].get("backend", [])
        assert any(e["name"] == "my-custom-server-agent" for e in backend_entries)
        entry = next(e for e in backend_entries if e["name"] == "my-custom-server-agent")
        assert entry["source"] == "description"

    def test_vague_description_goes_unmapped(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent(
            agents_dir,
            "haiku-writer",
            "Writes seasonal haiku about nature and poetry composition",
        )
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        unmapped = result["domains"].get("unmapped", [])
        assert any(e["name"] == "haiku-writer" for e in unmapped)
        entry = next(e for e in unmapped if e["name"] == "haiku-writer")
        assert entry["source"] == "unmapped"

    def test_no_frontmatter_file_skipped(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_no_frontmatter(agents_dir, "no-fm-agent")
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        all_names = {
            e["name"]
            for bucket in result["domains"].values()
            for e in bucket
        }
        assert "no-fm-agent" not in all_names


# ---------------------------------------------------------------------------
# Map shape
# ---------------------------------------------------------------------------

class TestMapShape:
    def test_required_top_level_keys(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent(agents_dir, "backend-developer", "Builds REST APIs")
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        assert "version" in result
        assert "platforms" in result
        assert "domains" in result

    def test_version_is_1(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        assert result["version"] == 1

    def test_platforms_records_agents_dir(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        assert result["platforms"]["claude"] == str(agents_dir)

    def test_tools_stored_as_list(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent(agents_dir, "backend-developer", "Builds REST APIs", tools="Read, Write, Bash")
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        entry = next(
            e
            for bucket in result["domains"].values()
            for e in bucket
            if e["name"] == "backend-developer"
        )
        assert isinstance(entry["tools"], list)
        assert "Read" in entry["tools"]

    def test_tools_list_form_stored_as_list(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent_list_tools(
            agents_dir,
            "backend-developer",
            "Builds REST APIs",
            ["Read", "Write", "Bash"],
        )
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        entry = next(
            e
            for bucket in result["domains"].values()
            for e in bucket
            if e["name"] == "backend-developer"
        )
        assert entry["tools"] == ["Read", "Write", "Bash"]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_run_adds_zero_new(self, tmp_path, capsys):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent(agents_dir, "backend-developer", "Builds REST APIs")
        build_agent_map(agents_dir=agents_dir, map_path=map_path)
        capsys.readouterr()  # discard first-run output

        build_agent_map(agents_dir=agents_dir, map_path=map_path)
        out = capsys.readouterr().out
        assert out.startswith("+0 new")

    def test_no_duplicate_names_after_two_runs(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent(agents_dir, "backend-developer", "Builds REST APIs")
        build_agent_map(agents_dir=agents_dir, map_path=map_path)
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)

        all_names: list[str] = [
            e["name"]
            for bucket in result["domains"].values()
            for e in bucket
        ]
        assert len(all_names) == len(set(all_names)), "duplicate names found after two runs"

    def test_domains_stable_after_two_runs(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"
        _write_agent(agents_dir, "backend-developer", "Builds REST APIs")
        map1 = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        map2 = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        assert map1["domains"] == map2["domains"]


# ---------------------------------------------------------------------------
# Additive merge
# ---------------------------------------------------------------------------

class TestAdditiveMerge:
    def test_hand_edited_entry_survives_rebuild(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"

        # First run — seeds backend-developer
        _write_agent(agents_dir, "backend-developer", "Builds REST APIs")
        build_agent_map(agents_dir=agents_dir, map_path=map_path)

        # Simulate hand-edit: add a custom field to the entry
        data = json.loads(map_path.read_text())
        for entry in data["domains"].get("backend", []):
            if entry["name"] == "backend-developer":
                entry["_hand_edited"] = "do-not-overwrite"
        map_path.write_text(json.dumps(data, indent=2))

        # Second run — add a new agent
        _write_agent(agents_dir, "frontend-developer", "Builds React UIs")
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)

        # Hand-edited entry must be intact
        backend_entry = next(
            e for e in result["domains"]["backend"]
            if e["name"] == "backend-developer"
        )
        assert backend_entry.get("_hand_edited") == "do-not-overwrite"

    def test_new_agent_added_on_disk_appears_in_map(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"

        _write_agent(agents_dir, "backend-developer", "Builds REST APIs")
        build_agent_map(agents_dir=agents_dir, map_path=map_path)

        _write_agent(agents_dir, "frontend-developer", "Builds React UIs with CSS components")
        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)

        all_names = {
            e["name"]
            for bucket in result["domains"].values()
            for e in bucket
        }
        assert "frontend-developer" in all_names

    def test_agent_removed_from_disk_stays_in_map(self, tmp_path):
        """Additive-only: no pruning — agents removed from disk stay in the map."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        map_path = tmp_path / "agent-map.json"

        _write_agent(agents_dir, "backend-developer", "Builds REST APIs")
        build_agent_map(agents_dir=agents_dir, map_path=map_path)

        # Remove the file from disk
        (agents_dir / "backend-developer.md").unlink()

        result = build_agent_map(agents_dir=agents_dir, map_path=map_path)
        all_names = {
            e["name"]
            for bucket in result["domains"].values()
            for e in bucket
        }
        assert "backend-developer" in all_names
