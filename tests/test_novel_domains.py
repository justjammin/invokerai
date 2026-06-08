"""Tests for open-domain routing — novel domains not in the fixed-15 set.

All tests use fixture agent-maps; no live ~/.invoker map is read.

Coverage:
- resolve_plan solo: novel domain WITH map bucket → routes to that agent, no gap.
- resolve_plan solo: novel domain WITHOUT map bucket → fallback + gap.
- resolve_plan crew: novel domain WITH map bucket → routes to that agent, no gap.
- resolve_plan crew: novel domain WITHOUT map bucket → fallback + gap.
- Regression: fixed-15 domain ('backend') resolves identically to before.
- Multi-domain mixing fixed + novel: both resolve to real agents.
- Keystone: every emitted agent name is present in the fixture map or == fallback.
- orchestrate end-to-end: novel domain selects that bucket's agent, no legal gap.
"""
from __future__ import annotations

import pytest

from agent_invoker.agent_select import resolve_plan, _FALLBACK_AGENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(name: str, description: str) -> dict:
    return {"name": name, "description": description, "tools": ["Read"], "model": "sonnet", "source": "name"}


def _map_with_legal() -> dict:
    """Fixture map: 'legal' bucket + 'backend' bucket + 'code-review' bucket."""
    return {
        "version": 1,
        "domains": {
            "legal": [_entry("contract-reviewer", "reviews legal contracts and NDAs")],
            "backend": [_entry("backend-developer", "builds server-side APIs and microservices")],
            "code-review": [_entry("code-reviewer", "reviews code quality and security")],
        },
    }


def _map_without_legal() -> dict:
    """Fixture map with only 'backend' — no 'legal' bucket."""
    return {
        "version": 1,
        "domains": {
            "backend": [_entry("backend-developer", "builds server-side APIs and microservices")],
            "code-review": [_entry("code-reviewer", "reviews code quality and security")],
        },
    }


def _map_multi() -> dict:
    """Fixture map covering backend + legal + code-review for mixed-domain tests."""
    return {
        "version": 1,
        "domains": {
            "backend": [_entry("backend-developer", "builds server-side APIs and microservices")],
            "legal": [_entry("contract-reviewer", "reviews legal contracts and NDAs")],
            "devrel": [_entry("devrel-engineer", "developer relations and community")],
            "code-review": [_entry("code-reviewer", "reviews code quality and security")],
            "architecture": [_entry("architect-reviewer", "reviews system architecture")],
        },
    }


def _all_map_names(agent_map: dict) -> set[str]:
    return {
        e["name"]
        for bucket in agent_map.get("domains", {}).values()
        for e in bucket
    }


# ---------------------------------------------------------------------------
# resolve_plan SOLO — novel domain WITH bucket
# ---------------------------------------------------------------------------

class TestSoloNovelDomainWithBucket:
    """Novel domain present in map bucket → route to that agent, no coverage gap."""

    def _plan(self, role: str) -> dict:
        return {"routing": "solo", "role": role, "steps": [], "pattern": "pipeline", "domains": [role]}

    def test_legal_routes_to_contract_reviewer(self):
        resolved = resolve_plan("draft an NDA", self._plan("legal"), _map_with_legal())
        assert resolved["agent"] == "contract-reviewer", (
            f"Expected contract-reviewer, got {resolved['agent']}"
        )

    def test_legal_has_no_coverage_gap(self):
        resolved = resolve_plan("draft an NDA", self._plan("legal"), _map_with_legal())
        legal_gaps = [g for g in resolved["coverage_gaps"] if g.get("domain") == "legal"]
        assert legal_gaps == [], f"Unexpected coverage gap for 'legal': {legal_gaps}"

    def test_legal_not_general_purpose(self):
        resolved = resolve_plan("draft an NDA", self._plan("legal"), _map_with_legal())
        assert resolved["agent"] != _FALLBACK_AGENT

    def test_devrel_routes_to_devrel_engineer(self):
        resolved = resolve_plan("run a community hackathon", self._plan("devrel"), _map_multi())
        assert resolved["agent"] == "devrel-engineer"
        devrel_gaps = [g for g in resolved["coverage_gaps"] if g.get("domain") == "devrel"]
        assert devrel_gaps == []


# ---------------------------------------------------------------------------
# resolve_plan SOLO — novel domain WITHOUT bucket
# ---------------------------------------------------------------------------

class TestSoloNovelDomainWithoutBucket:
    """Novel domain NOT in map → general-purpose fallback + coverage gap (unchanged behavior)."""

    def _plan(self, role: str) -> dict:
        return {"routing": "solo", "role": role, "steps": [], "pattern": "pipeline", "domains": [role]}

    def test_legal_without_bucket_gets_fallback(self):
        resolved = resolve_plan("draft an NDA", self._plan("legal"), _map_without_legal())
        assert resolved["agent"] == _FALLBACK_AGENT

    def test_legal_without_bucket_has_gap(self):
        resolved = resolve_plan("draft an NDA", self._plan("legal"), _map_without_legal())
        assert len(resolved["coverage_gaps"]) >= 1

    def test_legal_gap_references_legal_domain(self):
        resolved = resolve_plan("draft an NDA", self._plan("legal"), _map_without_legal())
        gap_domains = [g["domain"] for g in resolved["coverage_gaps"]]
        assert "legal" in gap_domains, f"Expected 'legal' in gaps, got {gap_domains}"


# ---------------------------------------------------------------------------
# resolve_plan CREW — novel domain WITH bucket
# ---------------------------------------------------------------------------

class TestCrewNovelDomainWithBucket:
    def _crew_plan(self, roles: list[str]) -> dict:
        return {
            "routing": "crew",
            "steps": [
                {"step": i + 1, "role": role, "action": f"handle {role}", "parallel": False}
                for i, role in enumerate(roles)
            ],
            "pattern": "pipeline",
            "domains": roles,
        }

    def test_legal_step_routes_to_contract_reviewer(self):
        plan = self._crew_plan(["legal"])
        resolved = resolve_plan("review NDA for clauses", plan, _map_with_legal())
        step = resolved["steps"][0]
        assert step["agent"] == "contract-reviewer"

    def test_legal_crew_step_has_no_gap(self):
        plan = self._crew_plan(["legal"])
        resolved = resolve_plan("review NDA for clauses", plan, _map_with_legal())
        legal_gaps = [g for g in resolved["coverage_gaps"] if g.get("domain") == "legal"]
        assert legal_gaps == []

    def test_legal_crew_step_not_general_purpose(self):
        plan = self._crew_plan(["legal"])
        resolved = resolve_plan("review NDA for clauses", plan, _map_with_legal())
        assert resolved["steps"][0]["agent"] != _FALLBACK_AGENT


# ---------------------------------------------------------------------------
# resolve_plan CREW — novel domain WITHOUT bucket
# ---------------------------------------------------------------------------

class TestCrewNovelDomainWithoutBucket:
    def _crew_plan(self, roles: list[str]) -> dict:
        return {
            "routing": "crew",
            "steps": [
                {"step": i + 1, "role": role, "action": f"handle {role}", "parallel": False}
                for i, role in enumerate(roles)
            ],
            "pattern": "pipeline",
            "domains": roles,
        }

    def test_legal_without_bucket_gets_fallback(self):
        plan = self._crew_plan(["legal"])
        resolved = resolve_plan("review NDA", plan, _map_without_legal())
        assert resolved["steps"][0]["agent"] == _FALLBACK_AGENT

    def test_legal_without_bucket_has_gap(self):
        plan = self._crew_plan(["legal"])
        resolved = resolve_plan("review NDA", plan, _map_without_legal())
        assert len(resolved["coverage_gaps"]) >= 1


# ---------------------------------------------------------------------------
# REGRESSION — fixed-15 domain 'backend' resolves identically
# ---------------------------------------------------------------------------

class TestRegressionFixedDomains:
    """Fixed-15 domains must resolve exactly as before."""

    def _solo_plan(self, role: str) -> dict:
        return {"routing": "solo", "role": role, "steps": [], "pattern": "pipeline", "domains": []}

    def _crew_plan(self, roles: list[str]) -> dict:
        return {
            "routing": "crew",
            "steps": [
                {"step": i + 1, "role": role, "action": f"Implement {role}", "parallel": False}
                for i, role in enumerate(roles)
            ],
            "pattern": "pipeline",
            "domains": [],
        }

    def test_backend_developer_solo_still_resolves(self):
        """role='backend-developer' (the actual fixed role) must still resolve via _ROLE_DOMAIN."""
        resolved = resolve_plan("build a REST API", self._solo_plan("backend-developer"), _map_with_legal())
        assert resolved["agent"] == "backend-developer"
        assert resolved["coverage_gaps"] == []

    def test_backend_developer_crew_still_resolves(self):
        resolved = resolve_plan(
            "build and review a REST API",
            self._crew_plan(["backend-developer"]),
            _map_with_legal(),
        )
        backend_step = resolved["steps"][0]
        assert backend_step["agent"] == "backend-developer"

    def test_multi_fixed_domain_crew(self):
        """backend + code-review crew resolves both agents from map."""
        plan = self._crew_plan(["backend-developer", "code-reviewer"])
        resolved = resolve_plan("build and review an API", plan, _map_with_legal())
        agents = {s["agent"] for s in resolved["steps"]}
        assert "backend-developer" in agents
        assert "code-reviewer" in agents
        assert _FALLBACK_AGENT not in agents


# ---------------------------------------------------------------------------
# Multi-domain mixing fixed + novel
# ---------------------------------------------------------------------------

class TestMixedFixedAndNovelDomains:
    """domains=['backend','legal'] with both buckets → both resolve to real agents."""

    def _crew_plan(self, roles: list[str]) -> dict:
        return {
            "routing": "crew",
            "steps": [
                {"step": i + 1, "role": role, "action": f"handle {role}", "parallel": False}
                for i, role in enumerate(roles)
            ],
            "pattern": "pipeline",
            "domains": roles,
        }

    def test_backend_and_legal_both_resolve(self):
        plan = self._crew_plan(["backend-developer", "legal"])
        resolved = resolve_plan("build a contract API", plan, _map_multi())
        by_role = {s["role"]: s["agent"] for s in resolved["steps"]}
        assert by_role["backend-developer"] == "backend-developer"
        assert by_role["legal"] == "contract-reviewer"

    def test_no_legal_gap_in_mixed(self):
        plan = self._crew_plan(["backend-developer", "legal"])
        resolved = resolve_plan("build a contract API", plan, _map_multi())
        legal_gaps = [g for g in resolved["coverage_gaps"] if g.get("domain") == "legal"]
        assert legal_gaps == []

    def test_no_fallback_in_mixed_when_all_buckets_present(self):
        plan = self._crew_plan(["backend-developer", "legal"])
        resolved = resolve_plan("build a contract API", plan, _map_multi())
        agents = {s["agent"] for s in resolved["steps"]}
        assert _FALLBACK_AGENT not in agents


# ---------------------------------------------------------------------------
# Keystone: every emitted agent is in the fixture map or == fallback
# ---------------------------------------------------------------------------

class TestKeystoneNovelDomains:
    def test_solo_novel_agent_in_map(self):
        plan = {"routing": "solo", "role": "legal", "steps": [], "pattern": "pipeline", "domains": ["legal"]}
        resolved = resolve_plan("draft NDA", plan, _map_with_legal())
        name = resolved["agent"]
        assert name in _all_map_names(_map_with_legal()) or name == _FALLBACK_AGENT

    def test_crew_novel_agent_in_map(self):
        plan = {
            "routing": "crew",
            "steps": [
                {"step": 1, "role": "backend-developer", "action": "build API", "parallel": False},
                {"step": 2, "role": "legal", "action": "review contracts", "parallel": False},
                {"step": 3, "role": "devrel", "action": "community outreach", "parallel": False},
            ],
            "pattern": "pipeline",
            "domains": ["backend-developer", "legal", "devrel"],
        }
        resolved = resolve_plan("build a contract API with devrel", plan, _map_multi())
        all_names = _all_map_names(_map_multi())
        for step in resolved["steps"]:
            name = step["agent"]
            assert name in all_names or name == _FALLBACK_AGENT, (
                f"Step {step['step']} emitted '{name}' not in map and not fallback"
            )


# ---------------------------------------------------------------------------
# orchestrate() end-to-end with novel domain
# ---------------------------------------------------------------------------

class TestOrchestrateNovelDomain:
    """orchestrate('task', domains=['legal']) routes to the legal bucket agent."""

    def _legal_map(self) -> dict:
        """Map with legal + code-review buckets (code-review needed for the review step)."""
        return {
            "version": 1,
            "domains": {
                "legal": [_entry("contract-reviewer", "reviews legal contracts and NDAs")],
                "code-review": [_entry("code-reviewer", "reviews code quality and security")],
            },
        }

    def test_legal_domain_selects_contract_reviewer(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate("draft an NDA", domains=["legal"], agent_map=self._legal_map())
        all_agents = [node["agent"] for level in result["levels"] for node in level]
        assert "contract-reviewer" in all_agents, (
            f"Expected contract-reviewer in orchestrate output, got agents: {all_agents}"
        )

    def test_no_legal_coverage_gap(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate("draft an NDA", domains=["legal"], agent_map=self._legal_map())
        legal_gaps = [g for g in result["coverage_gaps"] if g.get("domain") == "legal"]
        assert legal_gaps == [], f"Unexpected coverage gap for 'legal': {legal_gaps}"

    def test_legal_agent_not_general_purpose(self):
        from agent_invoker.sdk import orchestrate
        result = orchestrate("draft an NDA", domains=["legal"], agent_map=self._legal_map())
        # The legal-domain step must NOT be general-purpose
        all_agents = [node["agent"] for level in result["levels"] for node in level]
        # At least one agent must be contract-reviewer (the legal step)
        assert any(a == "contract-reviewer" for a in all_agents)

    def test_orchestrate_legal_without_bucket_does_not_crash(self):
        from agent_invoker.sdk import orchestrate
        no_legal = {"version": 1, "domains": {"code-review": [_entry("code-reviewer", "reviews code")]}}
        result = orchestrate("draft an NDA", domains=["legal"], agent_map=no_legal)
        assert isinstance(result, dict)
        assert "levels" in result
        # With no bucket, there should be a legal coverage gap
        legal_gaps = [g for g in result["coverage_gaps"] if g.get("domain") == "legal"]
        assert len(legal_gaps) >= 1

    def test_keystone_all_agents_in_map_or_fallback(self):
        from agent_invoker.sdk import orchestrate
        agent_map = self._legal_map()
        result = orchestrate("draft an NDA", domains=["legal"], agent_map=agent_map)
        all_names = _all_map_names(agent_map)
        for level in result["levels"]:
            for node in level:
                name = node["agent"]
                assert name in all_names or name == _FALLBACK_AGENT, (
                    f"orchestrate emitted '{name}' not in map and not fallback"
                )
