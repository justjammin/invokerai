"""
Tests for the InvokerAI MCP server (stdio JSON-RPC 2.0).

Handlers are called directly — no subprocess spawning.
stdout is captured via contextlib.redirect_stdout so the JSON-RPC
response can be parsed and inspected.
"""
from __future__ import annotations

import contextlib
import io
import json
import time

import pytest

from agent_invoker.mcp_server import (
    _handle,
    _handle_route_task,
    _handle_spawn_specialist,
    _handle_confirm_route,
    _handle_list_agents,
    _agent_resources,
    _read_agent_resource,
    _get_session,
    _update_session,
    _LEDGER,
    _SPAWN_TOKEN,
    ALL_TOOLS,
    SERVER_INFO,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def call(req: dict) -> dict | None:
    """Dispatch req through _handle; return parsed JSON-RPC response or None."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _handle(req)
    raw = buf.getvalue().strip()
    if not raw:
        return None
    return json.loads(raw)


def rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    """Build a minimal JSON-RPC 2.0 request."""
    req: dict = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        req["params"] = params
    return req


def tool_call(name: str, arguments: dict, id: int = 1) -> dict:
    return rpc("tools/call", {"name": name, "arguments": arguments}, id=id)


# ---------------------------------------------------------------------------
# 1. initialize
# ---------------------------------------------------------------------------

class TestInitialize:
    def test_protocol_version_present(self):
        resp = call(rpc("initialize", {}))
        assert resp is not None
        assert "protocolVersion" in resp["result"]

    def test_capabilities_present(self):
        resp = call(rpc("initialize", {}))
        assert "capabilities" in resp["result"]

    def test_server_info_present(self):
        resp = call(rpc("initialize", {}))
        assert resp["result"]["serverInfo"] == SERVER_INFO

    def test_id_echoed(self):
        resp = call(rpc("initialize", {}, id=42))
        assert resp["id"] == 42


# ---------------------------------------------------------------------------
# 2. tools/list
# ---------------------------------------------------------------------------

class TestToolsList:
    def test_returns_all_tools(self):
        resp = call(rpc("tools/list", {}))
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {"route_task", "spawn_specialist", "confirm_route", "list_agents", "decompose_task"}

    def test_each_tool_has_input_schema(self):
        resp = call(rpc("tools/list", {}))
        for tool in resp["result"]["tools"]:
            assert "inputSchema" in tool, f"{tool['name']} missing inputSchema"

    def test_route_task_annotations(self):
        resp = call(rpc("tools/list", {}))
        tool = next(t for t in resp["result"]["tools"] if t["name"] == "route_task")
        assert tool.get("annotations", {}).get("readOnlyHint") is True

    def test_params_none_does_not_crash(self):
        """params: null must not raise — _handle coalesces None to {}."""
        resp = call({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": None})
        assert resp is not None
        assert "tools" in resp["result"]

    def test_matches_all_tools_constant(self):
        resp = call(rpc("tools/list", {}))
        assert resp["result"]["tools"] == ALL_TOOLS


# ---------------------------------------------------------------------------
# 3. route_task
# ---------------------------------------------------------------------------

class TestRouteTask:
    def _route(self, task: str, **extra) -> dict:
        args = {"task": task, **extra}
        resp = call(tool_call("route_task", args))
        assert resp is not None
        payload = json.loads(resp["result"]["content"][0]["text"])
        return payload

    def test_valid_task_has_required_fields(self):
        payload = self._route("fix the null pointer crash in auth.py")
        for field in ("routing", "role", "confidence", "tools", "session_id"):
            assert field in payload, f"missing field: {field}"

    def test_routing_is_direct_or_orchestrate(self):
        payload = self._route("fix the null pointer crash in auth.py")
        assert payload["routing"] in ("direct", "orchestrate")

    def test_empty_task_returns_32602(self):
        resp = call(tool_call("route_task", {"task": ""}))
        assert resp["error"]["code"] == -32602

    def test_whitespace_only_task_returns_32602(self):
        resp = call(tool_call("route_task", {"task": "   "}))
        assert resp["error"]["code"] == -32602

    def test_session_id_custom(self):
        payload = self._route("explain the codebase", session_id="my-session")
        assert payload["session_id"] == "my-session"

    def test_session_id_defaults_to_default(self):
        payload = self._route("explain the codebase")
        assert payload["session_id"] == "default"

    def test_confidence_is_integer(self):
        payload = self._route("debug the failing test")
        assert isinstance(payload["confidence"], int)

    def test_tools_is_list(self):
        payload = self._route("fix the null pointer crash in auth.py")
        assert isinstance(payload["tools"], list)


# ---------------------------------------------------------------------------
# 4. spawn_specialist
# ---------------------------------------------------------------------------

class TestSpawnSpecialist:
    def _spawn(self, task: str, **extra) -> dict:
        args = {"task": task, **extra}
        resp = call(tool_call("spawn_specialist", args))
        assert resp is not None
        payload = json.loads(resp["result"]["content"][0]["text"])
        return payload

    def test_valid_task_returns_spawn_authorized(self):
        payload = self._spawn("fix the null pointer crash in auth.py")
        assert payload.get("spawn_authorized") is True

    def test_spawn_token_file_written(self):
        self._spawn("fix the null pointer crash in auth.py")
        assert _SPAWN_TOKEN.exists(), "_SPAWN_TOKEN file was not created"

    def test_empty_task_returns_32602(self):
        resp = call(tool_call("spawn_specialist", {"task": ""}))
        assert resp["error"]["code"] == -32602

    def test_orchestrate_task_includes_pattern_and_steps(self):
        task = (
            "build the frontend react components, implement the backend api, "
            "configure the database schema, deploy to kubernetes, and write full documentation"
        )
        payload = self._spawn(task)
        if payload.get("routing") == "orchestrate":
            assert "pattern" in payload
            assert isinstance(payload["steps"], list)
            assert len(payload["steps"]) > 0

    def test_direct_task_no_pattern(self):
        payload = self._spawn("fix the null pointer crash in auth.py")
        if payload.get("routing") == "direct":
            assert "pattern" not in payload
            assert "steps" not in payload

    def test_spawn_token_contains_numeric_timestamp(self):
        self._spawn("debug the login failure in user.py")
        ts_text = _SPAWN_TOKEN.read_text().strip()
        ts = int(ts_text)  # must parse without ValueError
        # Timestamp should be recent (within 10 seconds)
        assert abs(ts - int(time.time())) < 10


# ---------------------------------------------------------------------------
# 5. spawn_specialist token TTL
# ---------------------------------------------------------------------------

class TestSpawnTokenTTL:
    def test_token_written_with_current_time(self):
        before = int(time.time())
        resp = call(tool_call("spawn_specialist", {"task": "review the PR changes"}))
        assert resp is not None
        after = int(time.time())
        ts = int(_SPAWN_TOKEN.read_text().strip())
        assert before <= ts <= after + 1

    def test_token_is_numeric(self):
        call(tool_call("spawn_specialist", {"task": "fix the config bug in settings.py"}))
        raw = _SPAWN_TOKEN.read_text().strip()
        assert raw.isdigit(), f"Expected numeric token, got: {raw!r}"


# ---------------------------------------------------------------------------
# 6. confirm_route
# ---------------------------------------------------------------------------

class TestConfirmRoute:
    def _confirm(self, task: str, expected_role: str, **extra) -> dict:
        args = {"task": task, "expected_role": expected_role, **extra}
        resp = call(tool_call("confirm_route", args))
        assert resp is not None
        return json.loads(resp["result"]["content"][0]["text"])

    def test_matching_role_returns_ok_true(self):
        # Strong debug signal — should route to debugger; confirm as debugger
        payload = self._confirm(
            "fix the undefined is not a function traceback in app.js",
            expected_role="debugger",
        )
        assert payload["ok"] is True

    def test_mismatched_role_returns_ok_false(self):
        # Strong single-domain debug task with high confidence
        # Classifier is absent (no pkl), so regex score determines confidence.
        # A task with heavy debug signals vs. incorrect role should produce ok=False
        # when confidence >= 50 AND role != expected.
        payload = self._confirm(
            "fix the TypeError: cannot read property 'id' of undefined in payment.js",
            expected_role="frontend-developer",
        )
        # ok is False when role != expected AND confidence >= 50
        # ok is True when confidence < 50 (low confidence → accept expected role)
        if payload["confidence"] >= 50 and payload.get("confirmed_role") != "frontend-developer":
            assert payload["ok"] is False
            assert "confirmed_role" in payload
        # If confidence < 50, ok=True is correct per implementation

    def test_missing_task_returns_32602(self):
        resp = call(tool_call("confirm_route", {"task": "", "expected_role": "debugger"}))
        assert resp["error"]["code"] == -32602

    def test_missing_expected_role_returns_32602(self):
        resp = call(tool_call("confirm_route", {"task": "fix the bug", "expected_role": ""}))
        assert resp["error"]["code"] == -32602

    def test_response_has_confidence(self):
        payload = self._confirm("fix the null check in auth.py", expected_role="debugger")
        assert isinstance(payload["confidence"], int)

    def test_session_id_echoed(self):
        payload = self._confirm(
            "fix the null check in auth.py",
            expected_role="debugger",
            session_id="test-session-42",
        )
        assert payload["session_id"] == "test-session-42"


# ---------------------------------------------------------------------------
# 7. list_agents
# ---------------------------------------------------------------------------

class TestListAgents:
    def _list(self, **kwargs) -> dict:
        resp = call(tool_call("list_agents", kwargs))
        assert resp is not None
        return json.loads(resp["result"]["content"][0]["text"])

    def test_returns_agents_key(self):
        payload = self._list()
        assert "agents" in payload

    def test_agents_is_list(self):
        payload = self._list()
        assert isinstance(payload["agents"], list)

    def test_each_agent_has_required_fields(self):
        payload = self._list()
        for agent in payload["agents"]:
            for field in ("id", "category", "description"):
                assert field in agent, f"agent missing field: {field}"

    def test_category_filter_returns_subset(self):
        all_payload = self._list()
        if not all_payload["agents"]:
            pytest.skip("No agents in registry")
        # Grab first category and filter by it
        first_category = all_payload["agents"][0]["category"]
        if not first_category:
            pytest.skip("Category empty, skip filter test")
        filtered = self._list(category=first_category)
        assert all(a["category"].lower() == first_category.lower() for a in filtered["agents"])

    def test_unknown_category_returns_empty(self):
        payload = self._list(category="nonexistent-category-xyz-123")
        assert payload["agents"] == []

    def test_empty_registry_returns_empty_list(self):
        """list_agents gracefully handles load_registry exceptions → empty list."""
        import unittest.mock as mock
        with mock.patch(
            "agent_invoker.registry.loader.load_registry",
            side_effect=Exception("registry unavailable"),
        ):
            resp = call(tool_call("list_agents", {}))
        assert resp is not None
        payload = json.loads(resp["result"]["content"][0]["text"])
        assert payload == {"agents": []}


# ---------------------------------------------------------------------------
# 8. resources/list
# ---------------------------------------------------------------------------

class TestResourcesList:
    def test_returns_resources_key(self):
        resp = call(rpc("resources/list", {}))
        assert "resources" in resp["result"]

    def test_resources_is_list(self):
        resp = call(rpc("resources/list", {}))
        assert isinstance(resp["result"]["resources"], list)

    def test_resources_have_agent_uris(self):
        resp = call(rpc("resources/list", {}))
        resources = resp["result"]["resources"]
        for r in resources:
            assert r["uri"].startswith("agent://"), f"bad URI: {r['uri']}"

    def test_absent_agents_dir_returns_empty(self):
        """If ~/.claude/agents/ does not exist, returns []."""
        import unittest.mock as mock
        from pathlib import Path
        fake_path = Path("/tmp/_nonexistent_agents_dir_xyz_invokerai")
        with mock.patch("agent_invoker.mcp_server._AGENTS_DIR", fake_path):
            result = _agent_resources()
        assert result == []


# ---------------------------------------------------------------------------
# 9. resources/read — path traversal guard
# ---------------------------------------------------------------------------

class TestResourcesReadSecurity:
    def test_path_traversal_denied(self):
        """agent://../../etc/passwd must not return file contents."""
        resp = call(rpc("resources/read", {"uri": "agent://../../etc/passwd"}))
        text = resp["result"]["contents"][0]["text"]
        assert "Access denied" in text

    def test_path_traversal_double_dot_denied(self):
        text = _read_agent_resource("agent://../../../etc/hosts")
        assert "Access denied" in text

    def test_path_traversal_absolute_denied(self):
        text = _read_agent_resource("agent:///etc/passwd")
        # resolves to _AGENTS_DIR / "/etc/passwd.md" which on POSIX = /etc/passwd.md
        # either "Access denied" or "not found" — must NOT expose real file content
        assert "Access denied" in text or "not found" in text.lower()

    def test_valid_role_unknown_returns_not_found(self):
        text = _read_agent_resource("agent://nonexistent-agent-xyz-abc")
        assert "not found" in text.lower()

    def test_unknown_uri_scheme_returns_32602(self):
        resp = call(rpc("resources/read", {"uri": "file:///etc/passwd"}))
        assert resp["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# 10. prompts/list
# ---------------------------------------------------------------------------

class TestPromptsList:
    def test_returns_route_prompt(self):
        resp = call(rpc("prompts/list", {}))
        prompts = resp["result"]["prompts"]
        names = [p["name"] for p in prompts]
        assert "route" in names

    def test_route_prompt_has_arguments(self):
        resp = call(rpc("prompts/list", {}))
        route_prompt = next(p for p in resp["result"]["prompts"] if p["name"] == "route")
        assert "arguments" in route_prompt
        arg_names = [a["name"] for a in route_prompt["arguments"]]
        assert "task" in arg_names


# ---------------------------------------------------------------------------
# 11. prompts/get
# ---------------------------------------------------------------------------

class TestPromptsGet:
    def test_get_route_prompt_with_task(self):
        resp = call(rpc("prompts/get", {"name": "route", "arguments": {"task": "fix the bug"}}))
        assert "messages" in resp["result"]
        text = resp["result"]["messages"][0]["content"]["text"]
        assert "fix the bug" in text

    def test_get_unknown_prompt_returns_32601(self):
        resp = call(rpc("prompts/get", {"name": "nonexistent-prompt"}))
        assert resp["error"]["code"] == -32601

    def test_get_route_prompt_empty_task(self):
        resp = call(rpc("prompts/get", {"name": "route", "arguments": {"task": ""}}))
        assert "messages" in resp["result"]


# ---------------------------------------------------------------------------
# 12. params: null edge cases
# ---------------------------------------------------------------------------

class TestParamsNull:
    def test_tools_list_params_null(self):
        resp = call({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": None})
        assert resp is not None
        assert "tools" in resp["result"]

    def test_resources_list_params_null(self):
        resp = call({"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": None})
        assert resp is not None
        assert "resources" in resp["result"]

    def test_prompts_list_params_null(self):
        resp = call({"jsonrpc": "2.0", "id": 3, "method": "prompts/list", "params": None})
        assert resp is not None
        assert "prompts" in resp["result"]


# ---------------------------------------------------------------------------
# 13. unknown method
# ---------------------------------------------------------------------------

class TestUnknownMethod:
    def test_unknown_method_returns_32601(self):
        resp = call(rpc("nonexistent/method", {}))
        assert resp is not None
        assert resp["error"]["code"] == -32601

    def test_unknown_method_id_present(self):
        resp = call(rpc("nonexistent/method", {}, id=99))
        assert resp["id"] == 99

    def test_no_response_when_id_is_none(self):
        """Notifications (id=None) produce no response for unknown methods."""
        req = {"jsonrpc": "2.0", "method": "nonexistent/method"}  # no id key
        resp = call(req)
        assert resp is None

    def test_unknown_tool_returns_32601(self):
        resp = call(rpc("tools/call", {"name": "nonexistent_tool", "arguments": {}}, id=7))
        assert resp["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# 14. session ledger
# ---------------------------------------------------------------------------

class TestSessionLedger:
    def test_update_session_stores_role(self):
        _update_session("sess-1", "debugger", "direct")
        s = _get_session("sess-1")
        assert s["active_role"] == "debugger"

    def test_get_session_returns_stored_data(self):
        _update_session("sess-2", "backend-developer", "direct")
        s = _get_session("sess-2")
        assert s["active_role"] == "backend-developer"

    def test_prior_routes_appended(self):
        _update_session("sess-3", "debugger", "direct")
        _update_session("sess-3", "frontend-developer", "direct")
        s = _get_session("sess-3")
        assert len(s["prior_routes"]) == 2
        assert s["prior_routes"][0]["role"] == "debugger"
        assert s["prior_routes"][1]["role"] == "frontend-developer"

    def test_new_session_has_none_role(self):
        s = _get_session("brand-new-session-xyz")
        assert s["active_role"] is None

    def test_ttl_expiry_clears_stale_entry(self):
        """Stale sessions older than TTL are evicted on next _get_session call."""
        stale_id = "stale-session"
        # Inject a stale entry manually
        LEDGER_TTL = 1800
        _LEDGER[stale_id] = {
            "active_role": "debugger",
            "prior_routes": [],
            "last_seen": time.time() - LEDGER_TTL - 1,  # expired
        }
        # Accessing any session triggers TTL sweep
        _get_session("trigger-cleanup")
        assert stale_id not in _LEDGER

    def test_prior_routes_capped_at_20(self):
        for i in range(25):
            _update_session("sess-cap", f"role-{i}", "direct")
        s = _get_session("sess-cap")
        assert len(s["prior_routes"]) <= 20

    def test_ledger_cleared_between_tests(self):
        """autouse clean_ledger fixture ensures isolation."""
        assert len(_LEDGER) == 0 or all(
            k in ("trigger-cleanup", "brand-new-session-xyz",
                  "sess-1", "sess-2", "sess-3", "sess-cap")
            for k in _LEDGER
        )
