"""Tests for agent_invoker.sdk — orchestration SDK.

Verifies:
- Public import surface
- compose_agent_definition contract
- topological_order correctness and cycle detection
- parallel_groups behaviour
- orchestrate() end-to-end (zero side effects, fixture map for determinism)
"""
from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Import surface
# ---------------------------------------------------------------------------

class TestImportSurface:
    def test_import_from_sdk_module(self):
        import agent_invoker.sdk as sdk
        for name in [
            "decompose",
            "load_agent_map",
            "resolve_plan",
            "compose_agent_definition",
            "topological_order",
            "parallel_groups",
            "orchestrate",
        ]:
            assert hasattr(sdk, name), f"sdk.py missing public name: {name}"

    def test_import_from_package(self):
        from agent_invoker import (
            orchestrate,
            compose_agent_definition,
            topological_order,
            parallel_groups,
            decompose,
            load_agent_map,
            resolve_plan,
        )
        # All resolved without ImportError
        assert callable(orchestrate)
        assert callable(compose_agent_definition)
        assert callable(topological_order)
        assert callable(parallel_groups)
        assert callable(decompose)
        assert callable(load_agent_map)
        assert callable(resolve_plan)


# ---------------------------------------------------------------------------
# compose_agent_definition
# ---------------------------------------------------------------------------

def _backend_node() -> dict:
    """A resolved enriched bead-graph node shaped as orchestrate() produces."""
    return {
        "id": "s1",
        "role": "backend-developer",
        "action": "Implement backend",
        "deps": [],
        "annotation": None,
        "agent": "backend-developer",
        "description": "Builds server-side APIs, microservices, and backend systems with robust architecture",
        "tools": ["Read", "Write", "Edit", "Bash"],
        "model": "claude-sonnet",
    }


class TestComposeAgentDefinition:
    def test_returns_dict(self):
        from agent_invoker.sdk import compose_agent_definition
        result = compose_agent_definition(_backend_node(), "build a REST API")
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        from agent_invoker.sdk import compose_agent_definition
        result = compose_agent_definition(_backend_node(), "build a REST API")
        for key in ("name", "description", "prompt", "tools", "model"):
            assert key in result, f"compose_agent_definition result missing key: {key}"

    def test_name_matches_node_agent(self):
        from agent_invoker.sdk import compose_agent_definition
        node = _backend_node()
        result = compose_agent_definition(node, "build a REST API")
        assert result["name"] == node["agent"]

    def test_tools_match_node_tools(self):
        from agent_invoker.sdk import compose_agent_definition
        node = _backend_node()
        result = compose_agent_definition(node, "build a REST API")
        assert result["tools"] == node["tools"]

    def test_prompt_is_string(self):
        from agent_invoker.sdk import compose_agent_definition
        result = compose_agent_definition(_backend_node(), "build a REST API")
        assert isinstance(result["prompt"], str)

    def test_prompt_is_nonempty_for_known_agent(self):
        """backend-developer has agent files on disk — prompt must be non-empty."""
        from agent_invoker.sdk import compose_agent_definition
        result = compose_agent_definition(_backend_node(), "build a REST API")
        assert len(result["prompt"]) > 0, "Expected non-empty prompt for backend-developer"

    def test_prompt_is_string_for_unknown_agent(self):
        """Fallback path (no persona file) must return empty string, not raise."""
        from agent_invoker.sdk import compose_agent_definition
        node = {
            **_backend_node(),
            "agent": "general-purpose",
            "description": "",
            "tools": [],
            "model": "",
        }
        result = compose_agent_definition(node, "some task")
        assert isinstance(result["prompt"], str)

    def test_description_matches_node(self):
        from agent_invoker.sdk import compose_agent_definition
        node = _backend_node()
        result = compose_agent_definition(node, "build a REST API")
        assert result["description"] == node["description"]


# ---------------------------------------------------------------------------
# topological_order
# ---------------------------------------------------------------------------

def _fan_out_fan_in_graph() -> dict:
    """Synthetic DAG: s1 -> s2, s3, s4 -> s5 -> s6."""
    return {
        "root": {"title": "test", "type": "epic"},
        "nodes": [
            {"id": "s1", "role": "r1", "action": "a", "deps": [], "annotation": None},
            {"id": "s2", "role": "r2", "action": "a", "deps": ["s1"], "annotation": None},
            {"id": "s3", "role": "r3", "action": "a", "deps": ["s1"], "annotation": None},
            {"id": "s4", "role": "r4", "action": "a", "deps": ["s1"], "annotation": None},
            {"id": "s5", "role": "r5", "action": "a", "deps": ["s2", "s3", "s4"], "annotation": None},
            {"id": "s6", "role": "r6", "action": "a", "deps": ["s5"], "annotation": None},
        ],
    }


class TestTopologicalOrder:
    def test_returns_list_of_lists(self):
        from agent_invoker.sdk import topological_order
        result = topological_order(_fan_out_fan_in_graph())
        assert isinstance(result, list)
        for level in result:
            assert isinstance(level, list)

    def test_s1_is_first_level(self):
        from agent_invoker.sdk import topological_order
        levels = topological_order(_fan_out_fan_in_graph())
        assert levels[0] == ["s1"], f"Level 0 should be ['s1'], got {levels[0]}"

    def test_s2_s3_s4_share_a_level(self):
        from agent_invoker.sdk import topological_order
        levels = topological_order(_fan_out_fan_in_graph())
        parallel_level = next(
            (lvl for lvl in levels if len(lvl) == 3), None
        )
        assert parallel_level is not None, "Expected a level with s2, s3, s4 grouped together"
        assert set(parallel_level) == {"s2", "s3", "s4"}

    def test_s2_s3_s4_after_s1(self):
        from agent_invoker.sdk import topological_order
        levels = topological_order(_fan_out_fan_in_graph())
        flat = [nid for lvl in levels for nid in lvl]
        pos = {nid: i for i, nid in enumerate(flat)}
        assert pos["s1"] < pos["s2"]
        assert pos["s1"] < pos["s3"]
        assert pos["s1"] < pos["s4"]

    def test_s5_after_s2_s3_s4(self):
        from agent_invoker.sdk import topological_order
        levels = topological_order(_fan_out_fan_in_graph())
        flat = [nid for lvl in levels for nid in lvl]
        pos = {nid: i for i, nid in enumerate(flat)}
        assert pos["s2"] < pos["s5"]
        assert pos["s3"] < pos["s5"]
        assert pos["s4"] < pos["s5"]

    def test_s6_is_last(self):
        from agent_invoker.sdk import topological_order
        levels = topological_order(_fan_out_fan_in_graph())
        assert levels[-1] == ["s6"], f"Last level should be ['s6'], got {levels[-1]}"

    def test_s5_before_s6(self):
        from agent_invoker.sdk import topological_order
        levels = topological_order(_fan_out_fan_in_graph())
        flat = [nid for lvl in levels for nid in lvl]
        pos = {nid: i for i, nid in enumerate(flat)}
        assert pos["s5"] < pos["s6"]

    def test_exactly_four_levels(self):
        """s1 / s2+s3+s4 / s5 / s6 = 4 levels."""
        from agent_invoker.sdk import topological_order
        levels = topological_order(_fan_out_fan_in_graph())
        assert len(levels) == 4, f"Expected 4 levels, got {len(levels)}: {levels}"

    def test_empty_graph_returns_empty(self):
        from agent_invoker.sdk import topological_order
        result = topological_order({"nodes": []})
        assert result == []

    def test_single_node_no_deps(self):
        from agent_invoker.sdk import topological_order
        graph = {"nodes": [{"id": "s1", "deps": [], "role": "r", "action": "a", "annotation": None}]}
        result = topological_order(graph)
        assert result == [["s1"]]

    def test_raises_on_cycle(self):
        from agent_invoker.sdk import topological_order
        cyclic = {
            "nodes": [
                {"id": "s1", "deps": ["s2"], "role": "r", "action": "a", "annotation": None},
                {"id": "s2", "deps": ["s1"], "role": "r", "action": "a", "annotation": None},
            ]
        }
        with pytest.raises(ValueError, match="[Cc]ycle"):
            topological_order(cyclic)

    def test_all_ids_present_in_output(self):
        from agent_invoker.sdk import topological_order
        graph = _fan_out_fan_in_graph()
        levels = topological_order(graph)
        all_ids = {n["id"] for n in graph["nodes"]}
        output_ids = {nid for lvl in levels for nid in lvl}
        assert all_ids == output_ids


# ---------------------------------------------------------------------------
# parallel_groups
# ---------------------------------------------------------------------------

class TestParallelGroups:
    def test_returns_same_structure_as_topological_order(self):
        from agent_invoker.sdk import topological_order, parallel_groups
        graph = _fan_out_fan_in_graph()
        assert parallel_groups(graph) == topological_order(graph)

    def test_independent_nodes_in_same_group(self):
        from agent_invoker.sdk import parallel_groups
        levels = parallel_groups(_fan_out_fan_in_graph())
        parallel_level = next(lvl for lvl in levels if len(lvl) > 1)
        assert set(parallel_level) == {"s2", "s3", "s4"}

    def test_barrier_node_in_later_group(self):
        """s5 depends on s2+s3+s4 — must be in a group after the parallel level."""
        from agent_invoker.sdk import parallel_groups
        levels = parallel_groups(_fan_out_fan_in_graph())
        parallel_level_idx = next(i for i, lvl in enumerate(levels) if len(lvl) > 1)
        s5_level_idx = next(i for i, lvl in enumerate(levels) if "s5" in lvl)
        assert s5_level_idx > parallel_level_idx

    def test_raises_on_cycle(self):
        from agent_invoker.sdk import parallel_groups
        cyclic = {
            "nodes": [
                {"id": "s1", "deps": ["s2"], "role": "r", "action": "a", "annotation": None},
                {"id": "s2", "deps": ["s1"], "role": "r", "action": "a", "annotation": None},
            ]
        }
        with pytest.raises(ValueError):
            parallel_groups(cyclic)


# ---------------------------------------------------------------------------
# orchestrate() end-to-end — fixture agent-map for determinism
# ---------------------------------------------------------------------------

def _fixture_agent_map() -> dict:
    """Minimal deterministic agent-map covering frontend/backend/database domains."""
    def _entry(name: str, description: str) -> dict:
        return {
            "name": name,
            "description": description,
            "tools": ["Read", "Write", "Edit", "Bash"],
            "model": "claude-sonnet",
            "source": "name",
        }

    return {
        "version": 1,
        "domains": {
            "frontend": [_entry("frontend-developer", "Builds React/Vue/Angular frontends.")],
            "backend": [_entry("backend-developer", "Builds server-side APIs and microservices.")],
            "database": [_entry("database-optimizer", "Optimizes queries and schemas.")],
            "architecture": [_entry("architect-reviewer", "Reviews system architecture.")],
            "code-review": [_entry("code-reviewer", "Reviews code quality and security.")],
        },
    }


_FIXTURE_MAP_NAMES = {
    "frontend-developer",
    "backend-developer",
    "database-optimizer",
    "architect-reviewer",
    "code-reviewer",
}
_FALLBACK = "general-purpose"


class TestOrchestrateEndToEnd:
    _task = "build a react frontend, fastapi backend, migrate postgres"
    _domains = ["frontend", "backend", "database"]

    def test_returns_dict(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        for key in ("pattern", "levels", "coverage_gaps"):
            assert key in result, f"orchestrate() result missing key: {key}"

    def test_pattern_is_string(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        assert isinstance(result["pattern"], str)
        assert len(result["pattern"]) > 0

    def test_levels_is_list_of_lists(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        assert isinstance(result["levels"], list)
        for level in result["levels"]:
            assert isinstance(level, list)

    def test_levels_nonempty(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        assert len(result["levels"]) >= 1

    def test_every_node_has_required_keys(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        for level in result["levels"]:
            for node in level:
                for key in ("node_id", "agent", "prompt", "tools", "model", "deps", "annotation"):
                    assert key in node, f"Node missing key '{key}': {node}"

    def test_agent_names_are_installed_or_fallback(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        for level in result["levels"]:
            for node in level:
                name = node["agent"]
                assert name in _FIXTURE_MAP_NAMES or name == _FALLBACK, (
                    f"Node agent '{name}' not in fixture map and not fallback"
                )

    def test_prompt_values_are_strings(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        for level in result["levels"]:
            for node in level:
                assert isinstance(node["prompt"], str)

    def test_tools_values_are_lists(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        for level in result["levels"]:
            for node in level:
                assert isinstance(node["tools"], list)

    def test_deps_values_are_lists(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        for level in result["levels"]:
            for node in level:
                assert isinstance(node["deps"], list)

    def test_coverage_gaps_is_list(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        assert isinstance(result["coverage_gaps"], list)

    def test_no_spawn_token_written(self):
        """orchestrate() must not write the canonical spawn-token file.

        conftest.py's autouse clean_spawn_token fixture removes the token before
        each test, so if orchestrate() were to write it, this assertion would
        catch it.
        """
        from agent_invoker.sdk import orchestrate
        from agent_invoker.cli import _SPAWN_TOKEN
        assert not _SPAWN_TOKEN.exists()
        orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        assert not _SPAWN_TOKEN.exists(), (
            "orchestrate() must not write the spawn token — it is a pure-compute fn"
        )

    def test_no_exception_on_empty_agent_map(self):
        """Falls back gracefully when agent-map has no matching domains."""
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map={"domains": {}})
        assert isinstance(result, dict)
        assert "levels" in result

    def test_topological_ordering_honoured(self):
        """Nodes in each level must have all their deps in earlier levels."""
        from agent_invoker.sdk import orchestrate
        result = orchestrate(self._task, domains=self._domains, agent_map=_fixture_agent_map())
        seen: set[str] = set()
        for level in result["levels"]:
            for node in level:
                for dep in node["deps"]:
                    assert dep in seen, (
                        f"Node {node['node_id']} has dep '{dep}' not yet resolved — "
                        f"topological order violated"
                    )
            for node in level:
                seen.add(node["node_id"])

    def test_inferred_domains_path(self):
        """orchestrate without explicit domains still returns a valid plan."""
        from agent_invoker.sdk import orchestrate
        result = orchestrate(
            "build a backend service with a database",
            agent_map=_fixture_agent_map(),
        )
        assert isinstance(result, dict)
        assert len(result["levels"]) >= 1
