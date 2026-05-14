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
        assert names == {"route_task", "spawn_specialist", "confirm_route", "list_agents", "decompose_task", "log_outcome"}

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

    def test_routing_is_always_orchestrate(self):
        result = route_task(task="fix the null pointer crash in auth.py")
        assert result["routing"] == "orchestrate"

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
        assert result["routing"] == "orchestrate"


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
        assert result["routing"] == "orchestrate"
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
        assert result["routing"] == "orchestrate"
        assert "pattern" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) >= 2


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
        update_session("sess-1", "debugger", "direct")
        s = get_session("sess-1")
        assert s["active_role"] == "debugger"

    def test_get_session_returns_stored_data(self):
        update_session("sess-2", "backend-developer", "direct")
        s = get_session("sess-2")
        assert s["active_role"] == "backend-developer"

    def test_prior_routes_appended(self):
        update_session("sess-3", "debugger", "direct")
        update_session("sess-3", "frontend-developer", "direct")
        s = get_session("sess-3")
        assert len(s["prior_routes"]) == 2
        assert s["prior_routes"][0]["role"] == "debugger"
        assert s["prior_routes"][1]["role"] == "frontend-developer"

    def test_new_session_has_none_role(self):
        s = get_session("brand-new-session-xyz")
        assert s["active_role"] is None

    def test_ttl_expiry_clears_stale_entry(self):
        import agent_invoker.core as _core
        stale_id = "stale-session"
        stale_data = {
            stale_id: {
                "active_role": "debugger",
                "prior_routes": [],
                "last_seen": time.time() - _LEDGER_TTL - 1,
            }
        }
        ledger = _core._LEDGER_PATH
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps(stale_data))
        get_session("trigger-cleanup")
        data = json.loads(ledger.read_text())
        assert stale_id not in data

    def test_prior_routes_capped_at_20(self):
        for i in range(25):
            update_session("sess-cap", f"role-{i}", "direct")
        s = get_session("sess-cap")
        assert len(s["prior_routes"]) <= 20
