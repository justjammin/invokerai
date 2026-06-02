"""Tests for the bead_graph DAG emitter (_to_bead_graph) and handoff file losslessness."""
from __future__ import annotations

import pytest

from agent_invoker.decompose import _to_bead_graph, decompose
from agent_invoker.domains import (
    PATTERN_PIPELINE,
    PATTERN_PARALLEL,
    PATTERN_SUPERVISOR,
    PATTERN_HIERARCHICAL,
    PATTERN_FEEDBACK_LOOP,
)


# ---------------------------------------------------------------------------
# _to_bead_graph — pure function unit tests
# ---------------------------------------------------------------------------

class TestToBeadGraphLinear:
    """Linear chain: each step depends on the single prior step."""

    def _linear_steps(self) -> list[dict]:
        return [
            {"step": 1, "role": "architect-reviewer", "action": "Plan", "parallel": False},
            {"step": 2, "role": "backend-developer", "action": "Build API", "parallel": False},
            {"step": 3, "role": "code-reviewer", "action": "Review", "parallel": False},
        ]

    def test_root_shape(self):
        graph = _to_bead_graph(self._linear_steps(), PATTERN_PIPELINE, "build an API")
        assert graph["root"]["type"] == "epic"
        assert graph["root"]["title"] == "build an API"

    def test_first_node_has_no_deps(self):
        graph = _to_bead_graph(self._linear_steps(), PATTERN_PIPELINE, "t")
        assert graph["nodes"][0]["id"] == "s1"
        assert graph["nodes"][0]["deps"] == []

    def test_linear_chain_deps(self):
        graph = _to_bead_graph(self._linear_steps(), PATTERN_PIPELINE, "t")
        nodes = graph["nodes"]
        assert nodes[1]["deps"] == ["s1"]
        assert nodes[2]["deps"] == ["s2"]

    def test_no_annotations_on_pipeline(self):
        graph = _to_bead_graph(self._linear_steps(), PATTERN_PIPELINE, "t")
        for node in graph["nodes"]:
            assert node["annotation"] is None

    def test_node_count_matches_steps(self):
        graph = _to_bead_graph(self._linear_steps(), PATTERN_PIPELINE, "t")
        assert len(graph["nodes"]) == 3


class TestToBeadGraphParallelFanOut:
    """Parallel fan: parallel steps depend on last non-parallel, next non-parallel fans in."""

    def _parallel_steps(self) -> list[dict]:
        return [
            {"step": 1, "role": "api-designer", "action": "Design contract", "parallel": False},
            {"step": 2, "role": "backend-developer", "action": "Implement backend", "parallel": True},
            {"step": 3, "role": "frontend-developer", "action": "Implement frontend", "parallel": True},
            {"step": 4, "role": "database-engineer", "action": "Implement DB layer", "parallel": True},
            {"step": 5, "role": "code-reviewer", "action": "Review all", "parallel": False},
        ]

    def test_parallel_steps_all_depend_on_last_nonparallel(self):
        graph = _to_bead_graph(self._parallel_steps(), PATTERN_PARALLEL, "t")
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["s2"]["deps"] == ["s1"]
        assert nodes["s3"]["deps"] == ["s1"]
        assert nodes["s4"]["deps"] == ["s1"]

    def test_fan_in_step_depends_on_all_parallel(self):
        graph = _to_bead_graph(self._parallel_steps(), PATTERN_PARALLEL, "t")
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert set(nodes["s5"]["deps"]) == {"s2", "s3", "s4"}

    def test_no_annotation_on_parallel_pattern(self):
        graph = _to_bead_graph(self._parallel_steps(), PATTERN_PARALLEL, "t")
        for node in graph["nodes"]:
            assert node["annotation"] is None


class TestToBeadGraphParallelFromStart:
    """Parallel block with no preceding non-parallel → deps=[]."""

    def _steps(self) -> list[dict]:
        return [
            {"step": 1, "role": "backend-developer", "action": "Backend", "parallel": True},
            {"step": 2, "role": "frontend-developer", "action": "Frontend", "parallel": True},
            {"step": 3, "role": "code-reviewer", "action": "Review", "parallel": False},
        ]

    def test_first_parallel_has_no_deps(self):
        graph = _to_bead_graph(self._steps(), PATTERN_PARALLEL, "t")
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["s1"]["deps"] == []
        assert nodes["s2"]["deps"] == []

    def test_fan_in_depends_on_all_parallel(self):
        graph = _to_bead_graph(self._steps(), PATTERN_PARALLEL, "t")
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert set(nodes["s3"]["deps"]) == {"s1", "s2"}


class TestToBeadGraphFeedbackLoop:
    """feedback_loop pattern → first code-reviewer node gets annotation='loop'."""

    def _steps(self) -> list[dict]:
        return [
            {"step": 1, "role": "code-reviewer", "action": "Audit quality", "parallel": False},
            {"step": 2, "role": "code-simplifier", "action": "Apply fixes", "parallel": False},
        ]

    def test_code_reviewer_annotated_loop(self):
        graph = _to_bead_graph(self._steps(), PATTERN_FEEDBACK_LOOP, "t")
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["s1"]["annotation"] == "loop"

    def test_non_reviewer_node_not_annotated(self):
        graph = _to_bead_graph(self._steps(), PATTERN_FEEDBACK_LOOP, "t")
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["s2"]["annotation"] is None


class TestToBeadGraphSupervisor:
    """supervisor pattern → first architect-reviewer node gets annotation='expand'."""

    def _steps(self) -> list[dict]:
        return [
            {"step": 1, "role": "architect-reviewer", "action": "Decompose and assign", "parallel": False},
            {"step": 2, "role": "backend-developer", "action": "Execute subtask", "parallel": False},
            {"step": 3, "role": "architect-reviewer", "action": "Review and integrate", "parallel": False},
        ]

    def test_first_architect_annotated_expand(self):
        graph = _to_bead_graph(self._steps(), PATTERN_SUPERVISOR, "t")
        nodes = graph["nodes"]
        assert nodes[0]["annotation"] == "expand"

    def test_second_architect_not_annotated(self):
        graph = _to_bead_graph(self._steps(), PATTERN_SUPERVISOR, "t")
        nodes = graph["nodes"]
        # Third step (index 2) is also architect-reviewer but must NOT be annotated.
        assert nodes[2]["annotation"] is None


class TestToBeadGraphHierarchical:
    """hierarchical pattern → first architect-reviewer gets annotation='expand'."""

    def _steps(self) -> list[dict]:
        return [
            {"step": 1, "role": "architect-reviewer", "action": "Top-level decomposition", "parallel": False},
            {"step": 2, "role": "backend-developer", "action": "Lead backend cluster", "parallel": False},
            {"step": 3, "role": "frontend-developer", "action": "Lead frontend cluster", "parallel": True},
        ]

    def test_hierarchical_architect_annotated_expand(self):
        graph = _to_bead_graph(self._steps(), PATTERN_HIERARCHICAL, "t")
        nodes = graph["nodes"]
        assert nodes[0]["annotation"] == "expand"


class TestToBeadGraphRootTitleTruncation:
    def test_title_truncated_to_80(self):
        long_task = "x" * 200
        graph = _to_bead_graph(
            [{"step": 1, "role": "backend-developer", "action": "do", "parallel": False}],
            PATTERN_PIPELINE,
            long_task,
        )
        assert len(graph["root"]["title"]) == 80

    def test_short_title_preserved(self):
        graph = _to_bead_graph(
            [{"step": 1, "role": "backend-developer", "action": "do", "parallel": False}],
            PATTERN_PIPELINE,
            "short task",
        )
        assert graph["root"]["title"] == "short task"


# ---------------------------------------------------------------------------
# decompose() integration — bead_graph populated on real calls
# ---------------------------------------------------------------------------

class TestDecomposeBeadGraphIntegration:
    def test_explicit_domains_parallel_has_bead_graph(self):
        result = decompose(
            "build backend, frontend, and migrate db",
            domains=["backend", "frontend", "database"],
        )
        assert result.bead_graph
        assert "root" in result.bead_graph
        assert "nodes" in result.bead_graph
        assert len(result.bead_graph["nodes"]) >= 3

    def test_bead_graph_nodes_have_required_keys(self):
        result = decompose("build an api", domains=["backend"])
        for node in result.bead_graph["nodes"]:
            assert "id" in node
            assert "role" in node
            assert "action" in node
            assert "deps" in node
            assert "annotation" in node

    def test_inferred_path_also_has_bead_graph(self):
        result = decompose("fix the login bug")
        assert isinstance(result.bead_graph, dict)
        assert "nodes" in result.bead_graph

    def test_default_construction_without_bead_graph_arg(self):
        """DecomposeResult can still be constructed without bead_graph (default empty dict)."""
        from agent_invoker.decompose import DecomposeResult
        dr = DecomposeResult(pattern="pipeline", steps=[], domain_roles=[])
        assert dr.bead_graph == {}

    def test_parallel_fan_produces_correct_deps_via_decompose(self):
        """backend+frontend+database → parallel block → fan-in on reviewer."""
        result = decompose(
            "build backend api, frontend ui, and database schema",
            domains=["backend", "frontend", "database"],
            complexity="medium",
        )
        nodes = {n["id"]: n for n in result.bead_graph["nodes"]}
        # Find the reviewer node (last non-parallel step).
        reviewer_node = result.bead_graph["nodes"][-1]
        # It should have multiple deps (fan-in from parallel block).
        assert len(reviewer_node["deps"]) >= 2, (
            f"Expected fan-in deps, got {reviewer_node['deps']}"
        )


# ---------------------------------------------------------------------------
# Handoff round-trip losslessness (file backend)
# ---------------------------------------------------------------------------

class TestHandoffRoundTrip:
    def test_decisions_survive_write_then_read(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff(
            "rt-session",
            "backend-developer",
            "build api",
            decisions=["use REST", "postgres"],
            open_questions=["auth method?"],
            files_touched=["api.py", "models.py"],
        )
        result = read_handoff("rt-session")
        assert result["decisions"] == ["use REST", "postgres"]
        assert result["open_questions"] == ["auth method?"]
        assert result["files_touched"] == ["api.py", "models.py"]

    def test_cumulative_writes_accumulate(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("acc-session", "backend-developer", "step 1", decisions=["use REST"])
        write_handoff("acc-session", "frontend-developer", "step 2", decisions=["use React"])
        result = read_handoff("acc-session")
        assert "use REST" in result["decisions"]
        assert "use React" in result["decisions"]
        assert len(result["steps_completed"]) == 2

    def test_steps_completed_role_preserved(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("role-session", "database-engineer", "migrate schema", files_touched=["migration.sql"])
        result = read_handoff("role-session")
        assert result["steps_completed"][0]["role"] == "database-engineer"
        assert "migration.sql" in result["files_touched"]

    def test_missing_session_returns_empty_dict(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import read_handoff

        assert read_handoff("nonexistent-session") == {}

    def test_handoff_backend_always_file(self):
        from agent_invoker.sessions import _get_session_handoff_backend
        assert _get_session_handoff_backend("any-session") == "file"
        assert _get_session_handoff_backend("another-session") == "file"
