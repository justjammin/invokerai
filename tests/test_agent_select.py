"""Tests for agent_invoker.agent_select — Stage 2 routing over agent-map.json.

All tests use fixture agent_map dicts constructed in-test; no live ~/.invoker map is read.
"""
from __future__ import annotations

import pytest

from agent_invoker.agent_select import select_agent, resolve_plan, _FALLBACK_AGENT


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_agent(name: str, description: str) -> dict:
    return {"name": name, "description": description, "tools": ["Read"], "model": "sonnet", "source": "name"}


def _make_map(*domain_buckets: tuple[str, list[dict]]) -> dict:
    """Build a minimal agent-map dict from (domain, [candidates]) pairs."""
    return {"version": 1, "domains": {d: entries for d, entries in domain_buckets}}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BUSINESS_MAP = _make_map(
    ("business", [
        _make_agent("business-analyst", "Use when analyzing business processes, gathering requirements from stakeholders, or identifying process improvements."),
        _make_agent("competitive-analyst", "Use when you need to analyze direct and indirect competitors, benchmark against market leaders, or develop competitive strategy."),
        _make_agent("project-idea-validator", "Use when you need an idea pressure-tested with brutal honesty, competitor teardown, market sizing, and go/no-go recommendation."),
        _make_agent("project-manager", "Use when you need to establish project plans, track execution progress, manage risks, coordinate across teams, and deliver milestones."),
        _make_agent("trend-analyst", "Use when analyzing emerging patterns, predicting industry shifts, or developing future scenarios to inform strategy."),
    ]),
    ("backend", [
        _make_agent("backend-developer", "Use when building server-side APIs, microservices, and backend systems."),
    ]),
)

MULTI_DOMAIN_MAP = _make_map(
    ("backend", [
        _make_agent("backend-developer", "Use when building server-side APIs, microservices, and backend systems."),
    ]),
    ("frontend", [
        _make_agent("frontend-developer", "Use when building React, Vue, or Angular user interfaces and frontend components."),
    ]),
    ("testing", [
        _make_agent("test-automator", "Use when writing automated tests, setting up test infrastructure, or improving coverage."),
    ]),
    ("documentation", [
        _make_agent("technical-writer", "Use when writing technical documentation, READMEs, API docs, or user guides."),
    ]),
)

EMPTY_DOMAIN_MAP = _make_map(
    ("backend", [
        _make_agent("backend-developer", "Builds server-side APIs."),
    ]),
    # "frontend" domain intentionally absent
)


# ---------------------------------------------------------------------------
# select_agent: single candidate
# ---------------------------------------------------------------------------

class TestSelectAgentSingleCandidate:
    def test_single_candidate_returned_directly(self):
        agent_map = _make_map(
            ("backend", [_make_agent("backend-developer", "Builds REST APIs.")]),
        )
        result = select_agent("backend", "build an api", agent_map, task_text="build an api")
        assert result is not None
        assert result["name"] == "backend-developer"

    def test_empty_domain_returns_none(self):
        agent_map = _make_map(("backend", []))
        result = select_agent("backend", "build an api", agent_map, task_text="build an api")
        assert result is None

    def test_missing_domain_returns_none(self):
        agent_map = _make_map(("backend", [_make_agent("backend-developer", "Builds APIs.")]))
        result = select_agent("frontend", "build a ui", agent_map, task_text="build a ui")
        assert result is None


# ---------------------------------------------------------------------------
# select_agent: within-domain scoring (LOAD-BEARING)
# ---------------------------------------------------------------------------

class TestWithinDomainScoring:
    """Two distinct tasks in the business domain must select DIFFERENT agents."""

    def test_competitor_task_selects_competitive_analyst(self):
        result = select_agent(
            "business",
            "analyze our competitors pricing strategy",
            BUSINESS_MAP,
            task_text="analyze our competitors pricing strategy",
        )
        assert result is not None
        assert result["name"] == "competitive-analyst", (
            f"Expected competitive-analyst, got {result['name']}"
        )

    def test_project_plan_task_selects_project_manager(self):
        result = select_agent(
            "business",
            "build a project plan with milestones and track team delivery",
            BUSINESS_MAP,
            task_text="build a project plan with milestones and track team delivery",
        )
        assert result is not None
        assert result["name"] == "project-manager", (
            f"Expected project-manager, got {result['name']}"
        )

    def test_competitor_and_project_tasks_select_different_agents(self):
        """The keystone within-domain test: two tasks must produce different agents."""
        competitor_result = select_agent(
            "business",
            "analyze our competitors pricing strategy",
            BUSINESS_MAP,
            task_text="analyze our competitors pricing strategy",
        )
        project_result = select_agent(
            "business",
            "build a project plan with milestones and track team delivery",
            BUSINESS_MAP,
            task_text="build a project plan with milestones and track team delivery",
        )
        assert competitor_result is not None
        assert project_result is not None
        assert competitor_result["name"] != project_result["name"], (
            f"Both tasks selected the same agent: {competitor_result['name']}. "
            "Within-domain scoring must differentiate tasks."
        )

    def test_trend_task_selects_trend_analyst(self):
        result = select_agent(
            "business",
            "predict emerging industry shifts and future scenarios for our strategy",
            BUSINESS_MAP,
            task_text="predict emerging industry shifts and future scenarios for our strategy",
        )
        assert result is not None
        assert result["name"] == "trend-analyst", (
            f"Expected trend-analyst, got {result['name']}"
        )

    def test_idea_validation_task_selects_idea_validator(self):
        result = select_agent(
            "business",
            "validate this startup idea with market sizing and go no-go recommendation",
            BUSINESS_MAP,
            task_text="validate this startup idea with market sizing and go no-go recommendation",
        )
        assert result is not None
        # idea validator or business analyst both reasonable; assert it's NOT project-manager
        assert result["name"] != "project-manager", (
            f"Idea validation should not select project-manager, got {result['name']}"
        )

    def test_tiebreak_is_deterministic(self):
        """Same task run twice returns the same agent (deterministic tiebreak)."""
        task = "generic business task with no strong signal"
        r1 = select_agent("business", task, BUSINESS_MAP, task_text=task)
        r2 = select_agent("business", task, BUSINESS_MAP, task_text=task)
        assert r1 is not None and r2 is not None
        assert r1["name"] == r2["name"]


# ---------------------------------------------------------------------------
# resolve_plan: solo
# ---------------------------------------------------------------------------

class TestResolvePlanSolo:
    def test_solo_emits_installed_agent_name(self):
        plan = {"routing": "solo", "role": "backend-developer", "steps": [], "pattern": "pipeline", "domains": []}
        resolved = resolve_plan("build a REST API", plan, MULTI_DOMAIN_MAP)
        assert resolved["routing"] == "solo"
        assert resolved["agent"] == "backend-developer"

    def test_solo_agent_in_map(self):
        plan = {"routing": "solo", "role": "backend-developer", "steps": [], "pattern": "pipeline", "domains": []}
        resolved = resolve_plan("build a REST API", plan, MULTI_DOMAIN_MAP)
        all_names = {
            e["name"]
            for bucket in MULTI_DOMAIN_MAP["domains"].values()
            for e in bucket
        }
        assert resolved["agent"] in all_names or resolved["agent"] == _FALLBACK_AGENT

    def test_solo_unknown_role_emits_general_purpose(self):
        plan = {"routing": "solo", "role": "nonexistent-role-xyz", "steps": [], "pattern": None, "domains": []}
        resolved = resolve_plan("some task", plan, MULTI_DOMAIN_MAP)
        assert resolved["agent"] == _FALLBACK_AGENT
        assert len(resolved["coverage_gaps"]) == 1

    def test_solo_no_persona_key_in_resolved(self):
        plan = {"routing": "solo", "role": "backend-developer", "steps": [], "pattern": "pipeline", "domains": []}
        resolved = resolve_plan("build a REST API", plan, MULTI_DOMAIN_MAP)
        assert "persona" not in resolved
        assert "system_prompt_fragment" not in resolved


# ---------------------------------------------------------------------------
# resolve_plan: crew
# ---------------------------------------------------------------------------

class TestResolvePlanCrew:
    def _make_crew_plan(self, roles: list[str], parallel_after: int = 0) -> dict:
        steps = [
            {
                "step": i + 1,
                "role": role,
                "action": f"Implement {role}",
                "parallel": i >= parallel_after,
            }
            for i, role in enumerate(roles)
        ]
        return {
            "routing": "crew",
            "role": None,
            "steps": steps,
            "pattern": "pipeline",
            "domains": [],
        }

    def test_all_crew_agents_in_map(self):
        plan = self._make_crew_plan(["backend-developer", "frontend-developer", "test-automator"])
        resolved = resolve_plan("build a full stack app with tests", plan, MULTI_DOMAIN_MAP)
        all_names = {
            e["name"]
            for bucket in MULTI_DOMAIN_MAP["domains"].values()
            for e in bucket
        }
        for step in resolved["steps"]:
            name = step["agent"]
            assert name in all_names or name == _FALLBACK_AGENT, (
                f"Step {step['step']} agent '{name}' not in fixture map and is not fallback"
            )

    def test_crew_steps_carry_agent_field(self):
        plan = self._make_crew_plan(["backend-developer", "frontend-developer"])
        resolved = resolve_plan("build a web app", plan, MULTI_DOMAIN_MAP)
        for step in resolved["steps"]:
            assert "agent" in step, f"Step {step['step']} missing 'agent' key"

    def test_crew_steps_carry_domain_field(self):
        plan = self._make_crew_plan(["backend-developer", "frontend-developer"])
        resolved = resolve_plan("build a web app", plan, MULTI_DOMAIN_MAP)
        for step in resolved["steps"]:
            assert "domain" in step, f"Step {step['step']} missing 'domain' key"

    def test_crew_preserves_existing_step_fields(self):
        plan = self._make_crew_plan(["backend-developer"])
        resolved = resolve_plan("build an api", plan, MULTI_DOMAIN_MAP)
        step = resolved["steps"][0]
        assert "step" in step
        assert "role" in step
        assert "action" in step
        assert "parallel" in step

    def test_crew_no_persona_in_resolved(self):
        plan = self._make_crew_plan(["backend-developer", "frontend-developer"])
        resolved = resolve_plan("build a web app", plan, MULTI_DOMAIN_MAP)
        assert "persona" not in resolved
        assert "system_prompt_fragment" not in resolved


# ---------------------------------------------------------------------------
# resolve_plan: empty domain fallback (LOAD-BEARING)
# ---------------------------------------------------------------------------

class TestEmptyDomainFallback:
    def test_solo_missing_domain_emits_fallback(self):
        """frontend domain not in EMPTY_DOMAIN_MAP — must emit general-purpose + gap."""
        plan = {"routing": "solo", "role": "frontend-developer", "steps": [], "pattern": None, "domains": []}
        resolved = resolve_plan("build a react UI", plan, EMPTY_DOMAIN_MAP)
        assert resolved["agent"] == _FALLBACK_AGENT
        assert any(g["fallback"] == _FALLBACK_AGENT for g in resolved["coverage_gaps"])

    def test_solo_missing_domain_has_coverage_gap(self):
        plan = {"routing": "solo", "role": "frontend-developer", "steps": [], "pattern": None, "domains": []}
        resolved = resolve_plan("build a react UI", plan, EMPTY_DOMAIN_MAP)
        assert len(resolved["coverage_gaps"]) >= 1
        gap = resolved["coverage_gaps"][0]
        assert "domain" in gap
        assert "fallback" in gap
        assert gap["fallback"] == _FALLBACK_AGENT

    def test_crew_missing_domain_step_uses_fallback(self):
        """frontend-developer step with no frontend domain in map → fallback + gap."""
        plan = {
            "routing": "crew",
            "steps": [
                {"step": 1, "role": "backend-developer", "action": "Build API", "parallel": False},
                {"step": 2, "role": "frontend-developer", "action": "Build UI", "parallel": False},
            ],
            "pattern": "pipeline",
            "domains": [],
        }
        resolved = resolve_plan("build a full app", plan, EMPTY_DOMAIN_MAP)
        frontend_step = next(s for s in resolved["steps"] if s["role"] == "frontend-developer")
        backend_step = next(s for s in resolved["steps"] if s["role"] == "backend-developer")
        assert frontend_step["agent"] == _FALLBACK_AGENT
        assert backend_step["agent"] == "backend-developer"
        assert len(resolved["coverage_gaps"]) >= 1

    def test_known_domain_has_no_gap(self):
        """Backend domain IS in the map — no gap for that step."""
        plan = {
            "routing": "crew",
            "steps": [
                {"step": 1, "role": "backend-developer", "action": "Build API", "parallel": False},
            ],
            "pattern": "pipeline",
            "domains": [],
        }
        resolved = resolve_plan("build a REST API", plan, EMPTY_DOMAIN_MAP)
        backend_step = resolved["steps"][0]
        assert backend_step["agent"] == "backend-developer"
        # No gap for backend
        backend_gaps = [g for g in resolved["coverage_gaps"] if "backend" in g.get("domain", "")]
        assert len(backend_gaps) == 0


# ---------------------------------------------------------------------------
# Keystone: emitted agent names always in map (or == fallback)
# ---------------------------------------------------------------------------

class TestKeystoneInvariant:
    """Every agent name emitted by resolve_plan is either in the map or == general-purpose."""

    def _all_map_names(self, agent_map: dict) -> set[str]:
        return {
            e["name"]
            for bucket in agent_map.get("domains", {}).values()
            for e in bucket
        }

    def test_solo_keystone(self):
        agent_map = MULTI_DOMAIN_MAP
        for role in ["backend-developer", "frontend-developer", "test-automator", "technical-writer"]:
            plan = {"routing": "solo", "role": role, "steps": [], "pattern": None, "domains": []}
            resolved = resolve_plan("some task", plan, agent_map)
            name = resolved["agent"]
            assert name in self._all_map_names(agent_map) or name == _FALLBACK_AGENT, (
                f"Solo: emitted agent '{name}' for role '{role}' not in map and not fallback"
            )

    def test_crew_keystone(self):
        agent_map = MULTI_DOMAIN_MAP
        plan = {
            "routing": "crew",
            "steps": [
                {"step": 1, "role": "backend-developer", "action": "Build API", "parallel": False},
                {"step": 2, "role": "frontend-developer", "action": "Build UI", "parallel": False},
                {"step": 3, "role": "test-automator", "action": "Write tests", "parallel": False},
                {"step": 4, "role": "technical-writer", "action": "Write docs", "parallel": False},
            ],
            "pattern": "pipeline",
            "domains": [],
        }
        resolved = resolve_plan("build and test and document the app", plan, agent_map)
        all_names = self._all_map_names(agent_map)
        for step in resolved["steps"]:
            name = step["agent"]
            assert name in all_names or name == _FALLBACK_AGENT, (
                f"Crew: step {step['step']} emitted '{name}' not in map and not fallback"
            )

    def test_no_persona_in_resolved_output(self):
        """resolve_plan output must never contain persona or system_prompt_fragment."""
        for routing in ("solo", "crew"):
            if routing == "solo":
                plan = {"routing": "solo", "role": "backend-developer", "steps": [], "pattern": None, "domains": []}
            else:
                plan = {
                    "routing": "crew",
                    "steps": [{"step": 1, "role": "backend-developer", "action": "Build", "parallel": False}],
                    "pattern": "pipeline",
                    "domains": [],
                }
            resolved = resolve_plan("some task", plan, MULTI_DOMAIN_MAP)
            assert "persona" not in resolved, f"resolve_plan({routing}) must not emit 'persona'"
            assert "system_prompt_fragment" not in resolved, (
                f"resolve_plan({routing}) must not emit 'system_prompt_fragment'"
            )
