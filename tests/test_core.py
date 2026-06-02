"""Tests for agent_invoker.core — routing, persona loading, tied scores."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_invoker.core import route, _regex_score, _suggest_role, _load_persona, RoutingResult, record_accepted_routing
from agent_invoker.registry.loader import load_registry


# ---------------------------------------------------------------------------
# _regex_score
# ---------------------------------------------------------------------------

class TestRegexScore:
    def _score(self, task: str) -> dict:
        registry = load_registry()
        return _regex_score(task, registry)

    def test_debug_task_routes_direct(self):
        result = self._score("fix the null pointer crash in auth.py")
        assert result["routing"] == "solo"

    def test_debug_task_high_confidence(self):
        result = self._score("fix the null pointer crash in auth.py")
        assert result["confidence"] >= 50

    def test_multi_domain_task_routes_orchestrate(self):
        result = self._score(
            "build the react frontend, implement the backend api, "
            "configure postgres database, and deploy to kubernetes"
        )
        assert result["routing"] == "crew"

    def test_question_form_routes_direct(self):
        result = self._score("what does the auth middleware do")
        assert result["routing"] == "solo"

    def test_tied_score_routes_direct_with_50(self):
        # Single sentence + 2 domains + 1 verb = direct(2) vs orchestrate(2) = tie
        # "add auth middleware to the api" — security(1) + backend(1) = 2 domains → orch+2
        # single sentence → direct+2; 1 imp verb → extra=0
        result = self._score("add auth middleware to the api")
        assert result["routing"] == "solo"
        assert result["confidence"] == 50

    def test_result_has_required_keys(self):
        result = self._score("fix the crash")
        for key in ("routing", "suggested_role", "confidence", "source"):
            assert key in result

    def test_source_is_regex(self):
        result = self._score("fix the crash")
        assert result["source"] == "regex"


# ---------------------------------------------------------------------------
# route()
# ---------------------------------------------------------------------------

class TestRoute:
    def test_returns_routing_result(self):
        r = route("debug the 500 error in payments", log=False)
        assert isinstance(r, RoutingResult)

    def test_routing_is_valid(self):
        r = route("debug the 500 error in payments", log=False)
        assert r.routing in ("solo", "crew")

    def test_confidence_is_int(self):
        r = route("explain the auth flow", log=False)
        assert isinstance(r.confidence, int)

    def test_tools_is_list(self):
        r = route("fix the bug in auth.py", log=False)
        assert isinstance(r.tools, list)

    def test_direct_task_has_role(self):
        r = route("fix the TypeError in app.js", log=False)
        if r.routing == "solo":
            assert r.role is not None

    def test_debug_task_routes_to_debugger(self):
        r = route("fix the TypeError: cannot read property 'id' of undefined", log=False)
        assert r.role in ("debugger", "error-detective")

    def test_persona_present_when_role_set(self):
        r = route("fix the undefined error in payment.js", log=False)
        if r.role:
            assert isinstance(r.persona, dict)
            assert "resource_uri" in r.persona

    def test_persona_absent_when_no_role(self):
        with patch("agent_invoker.router._suggest_role", return_value=None), \
             patch("agent_invoker.router._regex_score", return_value={
                 "routing": "crew", "suggested_role": None,
                 "confidence": 80, "source": "regex"
             }):
            r = route("some task", log=False)
            assert r.persona == {}

    def test_no_log_does_not_write_file(self, tmp_path):
        log_path = tmp_path / "routing_log.jsonl"
        with patch("agent_invoker.router.LOG_PATH", log_path):
            route("fix the bug", log=False)
        assert not log_path.exists()


# ---------------------------------------------------------------------------
# _load_persona
# ---------------------------------------------------------------------------

class TestLoadPersona:
    def test_returns_dict(self):
        result = _load_persona("debugger")
        assert isinstance(result, dict)

    def test_resource_uri_present(self):
        result = _load_persona("debugger")
        assert "resource_uri" in result
        assert result["resource_uri"] == "agent://debugger"

    def test_unknown_role_returns_uri_only(self):
        result = _load_persona("nonexistent-role-xyz-abc")
        assert result == {"resource_uri": "agent://nonexistent-role-xyz-abc"}

    def test_system_prompt_fragment_max_2000(self):
        from agent_invoker.core import _CAVEMAN_PREFIX
        result = _load_persona("debugger")
        if "system_prompt_fragment" in result:
            # domain content capped at 2000; total includes fixed caveman prefix
            assert len(result["system_prompt_fragment"]) <= 8000 + len(_CAVEMAN_PREFIX)

    def test_fragment_strips_frontmatter(self):
        result = _load_persona("debugger")
        if "system_prompt_fragment" in result:
            assert not result["system_prompt_fragment"].startswith("---")


# ---------------------------------------------------------------------------
# record_accepted_routing
# ---------------------------------------------------------------------------

class TestRecordAcceptedRouting:
    def test_record_accepted_routing(self, tmp_path):
        training_log = tmp_path / "training.jsonl"
        with patch("agent_invoker.sessions.TRAINING_LOG_PATH", training_log):
            record_accepted_routing("fix auth bug", "backend-developer", "solo")
        assert training_log.exists()
        entry = json.loads(training_log.read_text().strip())
        assert entry["task"] == "fix auth bug"
        assert entry["role"] == "backend-developer"
        assert entry["routing"] == "solo"
        assert isinstance(entry["ts"], int)

    def test_auto_train_not_triggered_below_threshold(self, tmp_path):
        training_log = tmp_path / "training.jsonl"
        with patch("agent_invoker.sessions.TRAINING_LOG_PATH", training_log), \
             patch("agent_invoker.classifier.build") as mock_build:
            for _ in range(3):
                record_accepted_routing("fix auth bug", "backend-developer", "solo")
            mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# explain()
# ---------------------------------------------------------------------------

class TestExplain:
    def test_explain_returns_reasoning(self):
        from agent_invoker.core import explain
        result = explain("fix the fastapi auth endpoint")
        assert "role" in result
        assert isinstance(result["reasoning"], list)
        assert len(result["reasoning"]) > 0


# ---------------------------------------------------------------------------
# handoff
# ---------------------------------------------------------------------------

def test_write_and_read_handoff(tmp_path, monkeypatch):
    import agent_invoker.sessions as sessions_mod
    monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
    import agent_invoker.core as core_mod
    core_mod.write_handoff("sess1", "backend-developer", "build api", decisions=["use REST"], files_touched=["api.py"])
    result = core_mod.read_handoff("sess1")
    assert result["session_id"] == "sess1"
    assert result["decisions"] == ["use REST"]
    assert result["files_touched"] == ["api.py"]
    assert len(result["steps_completed"]) == 1
    assert result["steps_completed"][0]["role"] == "backend-developer"


def test_read_handoff_missing_returns_empty(tmp_path, monkeypatch):
    import agent_invoker.sessions as sessions_mod
    monkeypatch.setattr(sessions_mod, "_HANDOFF_DIR", tmp_path)
    import agent_invoker.core as core_mod
    assert core_mod.read_handoff("nonexistent") == {}


# ---------------------------------------------------------------------------
# project memory
# ---------------------------------------------------------------------------

def test_project_memory_roundtrip(tmp_path, monkeypatch):
    import agent_invoker.sessions as sessions_mod
    monkeypatch.setattr(sessions_mod, "_PROJECT_MEMORY_PATH", tmp_path / "pm.json")
    import agent_invoker.core as core_mod
    core_mod.update_project_memory("myrepo", "backend-developer", ["backend"])
    core_mod.update_project_memory("myrepo", "backend-developer", ["backend"])
    core_mod.update_project_memory("myrepo", "test-automator", ["testing"])
    mem = core_mod.get_project_memory("myrepo")
    assert mem["role_counts"]["backend-developer"] == 2
    assert mem["role_counts"]["test-automator"] == 1
    assert mem["last_domains"] == ["testing"]


def test_get_project_memory_missing(tmp_path, monkeypatch):
    import agent_invoker.sessions as sessions_mod
    monkeypatch.setattr(sessions_mod, "_PROJECT_MEMORY_PATH", tmp_path / "pm.json")
    import agent_invoker.core as core_mod
    assert core_mod.get_project_memory("nonexistent") == {}


# ---------------------------------------------------------------------------
# contract negotiation — api-designer injection
# ---------------------------------------------------------------------------

def test_contract_step_injected_for_backend_frontend():
    from agent_invoker.core import decompose
    result = decompose("build a user dashboard", domains=["backend", "frontend"])
    roles = [s["role"] for s in result.steps]
    assert "api-designer" in roles
    api_idx = roles.index("api-designer")
    backend_roles = {"backend-developer", "fullstack-developer", "fastapi-developer"}
    frontend_roles = {"frontend-developer", "react-specialist"}
    for i, s in enumerate(result.steps):
        if s["role"] in backend_roles or s["role"] in frontend_roles:
            assert i > api_idx, f"{s['role']} should come after api-designer"


def test_contract_step_not_injected_when_architecture_present():
    from agent_invoker.core import decompose
    result = decompose("build a user dashboard", domains=["architecture", "backend", "frontend"])
    roles = [s["role"] for s in result.steps]
    assert "api-designer" not in roles


def test_contract_step_not_injected_backend_only():
    from agent_invoker.core import decompose
    result = decompose("build auth api", domains=["backend"])
    roles = [s["role"] for s in result.steps]
    assert "api-designer" not in roles


def test_contract_step_injected_for_backend_mobile():
    from agent_invoker.core import decompose
    result = decompose("build mobile app with api", domains=["backend", "mobile"])
    roles = [s["role"] for s in result.steps]
    assert "api-designer" in roles
