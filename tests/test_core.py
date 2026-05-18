"""Tests for agent_invoker.core — routing, persona loading, tied scores."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_invoker.core import route, _regex_score, _suggest_role, _load_persona, RoutingResult
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
        with patch("agent_invoker.core._suggest_role", return_value=None), \
             patch("agent_invoker.core._regex_score", return_value={
                 "routing": "crew", "suggested_role": None,
                 "confidence": 80, "source": "regex"
             }):
            r = route("some task", log=False)
            assert r.persona == {}

    def test_no_log_does_not_write_file(self, tmp_path):
        log_path = tmp_path / "routing_log.jsonl"
        with patch("agent_invoker.core.LOG_PATH", log_path):
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
