"""
Tests for the InvokerAI MCP server (FastMCP 3.x).

Tool handlers are called directly — no subprocess spawning.
Server-level tests (tools/list, resources, prompts) use FastMCP async client.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from agent_invoker.mcp_server import (
    spawn_specialist,
    route_task,
    confirm_route,
    list_agents,
    decompose_task,
    get_handoff,
    put_handoff,
    persona_for_role,
    get_project_context,
    _agent_resources,
    _read_agent_resource,
    _SPAWN_TOKEN,
    SERVER_INFO,
    mcp,
)
from agent_invoker.core import get_session, update_session, _LEDGER_PATH, _LEDGER_TTL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


async def _tool_call(name: str, args: dict):
    from fastmcp import Client
    async with Client(mcp) as client:
        return await client.call_tool(name, args)


def call_tool(name: str, args: dict):
    return _run(_tool_call(name, args))



# ---------------------------------------------------------------------------
# 1. server info / tools/list via async client
# ---------------------------------------------------------------------------

class TestServerInfo:
    def test_server_info_correct(self):
        assert SERVER_INFO == {"name": "invokerai", "version": "0.2.0"}

    def test_tools_list_names(self):
        async def _t():
            from fastmcp import Client
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return {t.name for t in tools}
        names = _run(_t())
        assert names == {"route_task", "spawn_specialist", "confirm_route", "list_agents", "decompose_task", "log_outcome", "get_handoff", "put_handoff", "get_project_context", "persona_for_role"}

    def test_resources_list(self):
        resources = _agent_resources()
        assert isinstance(resources, list)

    def test_prompts_list(self):
        async def _t():
            from fastmcp import Client
            async with Client(mcp) as client:
                return await client.list_prompts()
        prompts = _run(_t())
        names = [p.name for p in prompts]
        assert "route" in names


# ---------------------------------------------------------------------------
# 2. route_task
# ---------------------------------------------------------------------------

class TestRouteTask:
    def test_valid_task_has_required_fields(self):
        result = route_task(task="fix the null pointer crash in auth.py")
        for field in ("routing", "role", "confidence", "tools", "session_id"):
            assert field in result, f"missing field: {field}"

    def test_routing_reflects_task_complexity(self):
        result = route_task(task="fix the null pointer crash in auth.py")
        assert result["routing"] == "solo"

    def test_empty_task_raises(self):
        with pytest.raises(Exception):
            route_task(task="")

    def test_session_id_custom(self):
        result = route_task(task="explain the codebase", session_id="my-session")
        assert result["session_id"] == "my-session"

    def test_session_id_defaults_to_default(self):
        result = route_task(task="explain the codebase")
        assert result["session_id"] == "default"

    def test_confidence_is_integer(self):
        result = route_task(task="debug the failing test")
        assert isinstance(result["confidence"], int)

    def test_tools_is_list(self):
        result = route_task(task="fix the null pointer crash in auth.py")
        assert isinstance(result["tools"], list)

    def test_explicit_domains_used(self):
        result = route_task(task="build an API", domains=["backend", "testing"])
        assert result["routing"] == "crew"


# ---------------------------------------------------------------------------
# 3. spawn_specialist
# ---------------------------------------------------------------------------

class TestSpawnSpecialist:
    def test_returns_spawn_authorized(self):
        result = spawn_specialist(task="fix the null pointer crash in auth.py")
        assert result.get("spawn_authorized") is True

    def test_spawn_token_file_written(self):
        spawn_specialist(task="fix the null pointer crash in auth.py")
        assert _SPAWN_TOKEN.exists(), "_SPAWN_TOKEN file was not created"

    def test_spawn_token_format(self):
        spawn_specialist(task="fix the null pointer crash in auth.py")
        raw = _SPAWN_TOKEN.read_text().strip()
        # New format: count:timestamp or just timestamp (legacy)
        if ":" in raw:
            count, ts = raw.split(":", 1)
            assert count.isdigit()
            assert ts.isdigit()
            assert abs(int(ts) - int(time.time())) < 10
        else:
            assert raw.isdigit()

    def test_spawn_count_always_at_least_2(self):
        result = spawn_specialist(task="fix the null pointer crash in auth.py")
        assert result.get("spawn_count", 0) >= 2

    def test_always_includes_steps(self):
        result = spawn_specialist(
            task="build a REST API with frontend and database",
            domains=["backend", "frontend", "database"],
        )
        assert result["routing"] == "crew"
        assert "pattern" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) > 0

    def test_spawn_count_matches_steps(self):
        result = spawn_specialist(
            task="build a REST API with frontend and database",
            domains=["backend", "frontend", "database"],
        )
        assert result["spawn_count"] == len(result["steps"])

    def test_empty_task_raises(self):
        with pytest.raises(Exception):
            spawn_specialist(task="")

    def test_single_domain_still_has_steps(self):
        result = spawn_specialist(task="fix the null pointer crash in auth.py")
        assert result["routing"] == "solo"
        assert "pattern" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) >= 1

    def test_dry_run_returns_preview_shape(self):
        result = spawn_specialist(task="add a fastapi endpoint", dry_run=True)
        assert result["dry_run"] is True
        assert result["spawn_authorized"] is False
        assert "role" in result
        assert "steps" in result

    def test_dry_run_does_not_write_spawn_token(self):
        token_mtime_before = _SPAWN_TOKEN.stat().st_mtime if _SPAWN_TOKEN.exists() else None
        spawn_specialist(task="add a fastapi endpoint", dry_run=True)
        token_mtime_after = _SPAWN_TOKEN.stat().st_mtime if _SPAWN_TOKEN.exists() else None
        assert token_mtime_before == token_mtime_after

    def test_dry_run_false_still_writes_token(self):
        _SPAWN_TOKEN.unlink(missing_ok=True)
        spawn_specialist(task="fix the null pointer crash in auth.py", dry_run=False)
        assert _SPAWN_TOKEN.exists()


# ---------------------------------------------------------------------------
# 4. confirm_route
# ---------------------------------------------------------------------------

class TestConfirmRoute:
    def test_matching_role_returns_ok_true(self):
        result = confirm_route(
            task="fix the undefined is not a function traceback in app.js",
            expected_role="debugger",
        )
        assert result["ok"] is True

    def test_missing_task_raises(self):
        with pytest.raises(Exception):
            confirm_route(task="", expected_role="debugger")

    def test_missing_expected_role_raises(self):
        with pytest.raises(Exception):
            confirm_route(task="fix the bug", expected_role="")

    def test_response_has_confidence(self):
        result = confirm_route(task="fix the null check in auth.py", expected_role="debugger")
        assert isinstance(result["confidence"], int)

    def test_session_id_echoed(self):
        result = confirm_route(
            task="fix the null check in auth.py",
            expected_role="debugger",
            session_id="test-session-42",
        )
        assert result["session_id"] == "test-session-42"

    def test_response_has_required_fields(self):
        result = confirm_route(task="fix the null check in auth.py", expected_role="debugger")
        for field in ("ok", "expected_role", "confirmed_role", "confidence"):
            assert field in result


# ---------------------------------------------------------------------------
# 5. list_agents
# ---------------------------------------------------------------------------

class TestListAgents:
    def test_returns_agents_key(self):
        result = list_agents()
        assert "agents" in result

    def test_agents_is_list(self):
        result = list_agents()
        assert isinstance(result["agents"], list)

    def test_each_agent_has_required_fields(self):
        result = list_agents()
        for agent in result["agents"]:
            for field in ("id", "category", "description"):
                assert field in agent, f"agent missing field: {field}"

    def test_category_filter(self):
        all_result = list_agents()
        if not all_result["agents"]:
            pytest.skip("No agents in registry")
        first_category = all_result["agents"][0]["category"]
        if not first_category:
            pytest.skip("Category empty")
        filtered = list_agents(category=first_category)
        assert all(a["category"].lower() == first_category.lower() for a in filtered["agents"])

    def test_unknown_category_returns_empty(self):
        result = list_agents(category="nonexistent-category-xyz-123")
        assert result["agents"] == []

    def test_empty_registry_returns_empty_list(self):
        import unittest.mock as mock
        with mock.patch(
            "agent_invoker.registry.loader.load_registry",
            side_effect=Exception("registry unavailable"),
        ):
            result = list_agents()
        assert result == {"agents": []}


# ---------------------------------------------------------------------------
# 6. decompose_task
# ---------------------------------------------------------------------------

class TestDecomposeTask:
    def test_returns_required_fields(self):
        result = decompose_task(task="build a REST API with a database")
        for field in ("pattern", "steps", "domain_roles"):
            assert field in result

    def test_bead_graph_present_with_nodes(self):
        result = decompose_task(
            task="build backend, frontend, migrate db",
            domains=["backend", "frontend", "database"],
        )
        assert "bead_graph" in result
        assert "nodes" in result["bead_graph"]

    def test_explicit_domains_structure(self):
        result = decompose_task(
            task="build an API with tests",
            domains=["backend", "testing"],
        )
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) >= 2

    def test_steps_have_required_fields(self):
        result = decompose_task(task="build a REST API", domains=["backend"])
        for step in result["steps"]:
            for field in ("step", "role", "action", "parallel"):
                assert field in step

    def test_code_review_only_feedback_loop(self):
        result = decompose_task(task="review the auth code", domains=["code-review"])
        assert result["pattern"] == "feedback_loop"
        assert len(result["steps"]) >= 1
        assert result["steps"][0]["role"] == "code-reviewer"

    def test_three_domains_parallel_pattern(self):
        result = decompose_task(
            task="build full stack app",
            domains=["frontend", "backend", "database"],
        )
        assert result["pattern"] == "parallel"

    def test_devops_adds_deploy_plan_step(self):
        result = decompose_task(
            task="deploy the API",
            domains=["backend", "devops"],
        )
        roles = [s["role"] for s in result["steps"]]
        assert "cloud-architect" in roles
        # Deploy plan must be last step
        assert result["steps"][-1]["role"] == "cloud-architect"

    def test_reviewer_always_present(self):
        result = decompose_task(task="build an API", domains=["backend"])
        roles = [s["role"] for s in result["steps"]]
        assert "code-reviewer" in roles or "architect-reviewer" in roles

    def test_architecture_domain_uses_architect_reviewer(self):
        result = decompose_task(task="design the system", domains=["architecture", "backend"])
        roles = [s["role"] for s in result["steps"]]
        assert "architect-reviewer" in roles


# ---------------------------------------------------------------------------
# 7. resources helpers
# ---------------------------------------------------------------------------

class TestResourcesHelpers:
    def test_agent_resources_returns_list(self):
        resources = _agent_resources()
        assert isinstance(resources, list)

    def test_agent_resources_uris_start_with_agent(self):
        resources = _agent_resources()
        for r in resources:
            assert r["uri"].startswith("agent://")

    def test_absent_agents_dir_returns_empty(self):
        import unittest.mock as mock
        from pathlib import Path
        fake_path = Path("/tmp/_nonexistent_agents_dir_xyz_invokerai")
        with mock.patch("agent_invoker.mcp_server._AGENTS_DIR", fake_path):
            result = _agent_resources()
        assert result == []

    def test_path_traversal_denied(self):
        text = _read_agent_resource("agent://../../etc/passwd")
        assert "Access denied" in text

    def test_path_traversal_double_dot_denied(self):
        text = _read_agent_resource("agent://../../../etc/hosts")
        assert "Access denied" in text

    def test_valid_role_unknown_returns_not_found(self):
        text = _read_agent_resource("agent://nonexistent-agent-xyz-abc")
        assert "not found" in text.lower()


# ---------------------------------------------------------------------------
# 8. session ledger
# ---------------------------------------------------------------------------

class TestSessionLedger:
    def test_update_session_stores_role(self):
        update_session("sess-1", "debugger", "solo")
        s = get_session("sess-1")
        assert s["active_role"] == "debugger"

    def test_get_session_returns_stored_data(self):
        update_session("sess-2", "backend-developer", "solo")
        s = get_session("sess-2")
        assert s["active_role"] == "backend-developer"

    def test_prior_routes_appended(self):
        update_session("sess-3", "debugger", "solo")
        update_session("sess-3", "frontend-developer", "solo")
        s = get_session("sess-3")
        assert len(s["prior_routes"]) == 2
        assert s["prior_routes"][0]["role"] == "debugger"
        assert s["prior_routes"][1]["role"] == "frontend-developer"

    def test_new_session_has_none_role(self):
        s = get_session("brand-new-session-xyz")
        assert s["active_role"] is None

    def test_ttl_expiry_clears_stale_entry(self):
        import agent_invoker.sessions as _sessions
        stale_id = "stale-session"
        stale_data = {
            stale_id: {
                "active_role": "debugger",
                "prior_routes": [],
                "last_seen": time.time() - _LEDGER_TTL - 1,
            }
        }
        ledger = _sessions._LEDGER_PATH
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps(stale_data))
        get_session("trigger-cleanup")
        data = json.loads(ledger.read_text())
        assert stale_id not in data

    def test_prior_routes_capped_at_20(self):
        for i in range(25):
            update_session("sess-cap", f"role-{i}", "solo")
        s = get_session("sess-cap")
        assert len(s["prior_routes"]) <= 20


# ---------------------------------------------------------------------------
# 9. project memory
# ---------------------------------------------------------------------------

def test_get_project_context_empty():
    result = get_project_context("nonexistent-project-xyz")
    assert result["project_id"] == "nonexistent-project-xyz"
    assert result["frequent_roles"] == []


# ---------------------------------------------------------------------------
# 10. write_handoff node_id tagging (A2)
# ---------------------------------------------------------------------------

class TestWriteHandoffNodeId:
    def test_with_node_id_step_carries_per_step_lists(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff(
            "nid-session",
            "backend-developer",
            "build api",
            decisions=["use REST"],
            open_questions=["auth method?"],
            files_touched=["api.py"],
            node_id="s2",
        )
        result = read_handoff("nid-session")
        step = result["steps_completed"][0]
        assert step["node_id"] == "s2"
        assert step["decisions"] == ["use REST"]
        assert step["open_questions"] == ["auth method?"]
        assert step["files_touched"] == ["api.py"]

    def test_with_node_id_flat_top_level_still_cumulative(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("nid2-session", "backend-developer", "step1", decisions=["d1"], node_id="s1")
        write_handoff("nid2-session", "frontend-developer", "step2", decisions=["d2"], node_id="s2")
        result = read_handoff("nid2-session")
        assert "d1" in result["decisions"]
        assert "d2" in result["decisions"]
        assert len(result["steps_completed"]) == 2

    def test_without_node_id_step_shape_unchanged(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("legacy-session", "backend-developer", "build api", decisions=["use REST"])
        result = read_handoff("legacy-session")
        step = result["steps_completed"][0]
        assert "node_id" not in step
        assert "decisions" not in step
        assert step["role"] == "backend-developer"
        assert step["task"] == "build api"
        assert "ts" in step

    def test_without_node_id_flat_cumulative_still_works(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("legacy2-session", "backend-developer", "step1", decisions=["d1"])
        write_handoff("legacy2-session", "frontend-developer", "step2", decisions=["d2"])
        result = read_handoff("legacy2-session")
        assert result["decisions"] == ["d1", "d2"]


# ---------------------------------------------------------------------------
# 11. read_handoff deps filtering (A3)
# ---------------------------------------------------------------------------

class TestReadHandoffDepsFilter:
    def test_deps_filter_returns_only_matching_nodes(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("deps-session", "backend-developer", "step s2", decisions=["s2-decision"], node_id="s2")
        write_handoff("deps-session", "frontend-developer", "step s3", decisions=["s3-decision"], node_id="s3")

        scoped = read_handoff("deps-session", deps=["s2"])
        assert len(scoped["steps_completed"]) == 1
        assert scoped["steps_completed"][0]["node_id"] == "s2"
        assert scoped["decisions"] == ["s2-decision"]
        assert "s3-decision" not in scoped["decisions"]

    def test_deps_none_returns_full_cumulative(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("full-session", "backend-developer", "step s2", decisions=["s2-d"], node_id="s2")
        write_handoff("full-session", "frontend-developer", "step s3", decisions=["s3-d"], node_id="s3")

        full = read_handoff("full-session", deps=None)
        assert len(full["steps_completed"]) == 2
        assert "s2-d" in full["decisions"]
        assert "s3-d" in full["decisions"]

    def test_deps_empty_list_returns_full_cumulative(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("empty-deps-session", "backend-developer", "step s2", decisions=["d1"], node_id="s2")
        full = read_handoff("empty-deps-session", deps=[])
        assert len(full["steps_completed"]) == 1
        assert "d1" in full["decisions"]

    def test_deps_filter_legacy_steps_without_node_id_excluded(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        # Legacy step (no node_id) should not appear when filtering by node_id
        write_handoff("mixed-session", "backend-developer", "legacy step", decisions=["legacy-d"])
        write_handoff("mixed-session", "frontend-developer", "tagged step", decisions=["tagged-d"], node_id="s2")

        scoped = read_handoff("mixed-session", deps=["s2"])
        assert len(scoped["steps_completed"]) == 1
        assert scoped["decisions"] == ["tagged-d"]

    def test_deps_union_across_multiple_matching_nodes(self, tmp_path, monkeypatch):
        import agent_invoker.sessions as sessions_mod
        monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
        from agent_invoker.sessions import write_handoff, read_handoff

        write_handoff("union-session", "backend-developer", "s2", decisions=["s2-d"], files_touched=["api.py"], node_id="s2")
        write_handoff("union-session", "frontend-developer", "s3", decisions=["s3-d"], files_touched=["ui.tsx"], node_id="s3")
        write_handoff("union-session", "database-engineer", "s4", decisions=["s4-d"], node_id="s4")

        scoped = read_handoff("union-session", deps=["s2", "s3"])
        assert set(scoped["decisions"]) == {"s2-d", "s3-d"}
        assert set(scoped["files_touched"]) == {"api.py", "ui.tsx"}
        assert len(scoped["steps_completed"]) == 2


# ---------------------------------------------------------------------------
# 12. prior_handoff regression — spawn_specialist still gets it (A3 no-deps path)
# ---------------------------------------------------------------------------

def test_prior_handoff_still_injected_after_put_handoff(tmp_path, monkeypatch):
    import agent_invoker.sessions as sessions_mod
    monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
    from agent_invoker.sessions import write_handoff

    sid = "prior-regression-session"
    write_handoff(sid, "backend-developer", "completed step", decisions=["use postgres"])

    result = spawn_specialist(task="fix the null pointer crash in auth.py", session_id=sid)
    assert "prior_handoff" in result
    assert "use postgres" in result["prior_handoff"].get("decisions", [])


# ---------------------------------------------------------------------------
# 13. persona_for_role (A4)
# ---------------------------------------------------------------------------

class TestPersonaForRole:
    def test_known_role_returns_system_prompt_fragment(self):
        result = persona_for_role(role="backend-developer")
        assert "system_prompt_fragment" in result

    def test_fragment_is_composed_not_raw_frontmatter(self):
        from agent_invoker.domains import _CAVEMAN_PREFIX
        result = persona_for_role(role="backend-developer")
        fragment = result["system_prompt_fragment"]
        assert fragment.startswith(_CAVEMAN_PREFIX), (
            f"Expected composed prefix, got: {fragment[:80]!r}"
        )

    def test_fragment_does_not_start_with_frontmatter(self):
        result = persona_for_role(role="backend-developer")
        fragment = result["system_prompt_fragment"]
        assert not fragment.startswith("---\nname:"), (
            "Got raw frontmatter instead of composed fragment"
        )

    def test_resource_uri_present(self):
        result = persona_for_role(role="backend-developer")
        assert result["resource_uri"] == "agent://backend-developer"

    def test_unknown_role_returns_uri_only(self):
        result = persona_for_role(role="nonexistent-role-xyz-abc")
        assert result["resource_uri"] == "agent://nonexistent-role-xyz-abc"
        assert "system_prompt_fragment" not in result

    def test_task_param_accepted(self):
        result = persona_for_role(role="backend-developer", task="build a REST API")
        assert "resource_uri" in result
