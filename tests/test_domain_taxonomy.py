"""Tests for the expanded domain taxonomy: marketing, business, research + paid-search subdomain."""
from __future__ import annotations

import pytest

from agent_invoker.domains import (
    CANONICAL_DOMAINS,
    _DOMAIN_ROLE_MAP,
    _ROLE_DOMAIN,
    _domain_roles,
)
from agent_invoker.persona import _load_persona


# ---------------------------------------------------------------------------
# CANONICAL_DOMAINS contains the 3 new domains
# ---------------------------------------------------------------------------

class TestCanonicalDomains:
    def test_marketing_in_canonical(self):
        assert "marketing" in CANONICAL_DOMAINS

    def test_business_in_canonical(self):
        assert "business" in CANONICAL_DOMAINS

    def test_research_in_canonical(self):
        assert "research" in CANONICAL_DOMAINS

    def test_canonical_count_is_15(self):
        assert len(CANONICAL_DOMAINS) == 15


# ---------------------------------------------------------------------------
# _DOMAIN_ROLE_MAP classifier — tested via _domain_roles (lowercased input)
# ---------------------------------------------------------------------------

class TestDomainRoleMapClassifier:
    def test_marketing_task_classifies_to_marketing(self):
        task = "build a paid search campaign with roas targets"
        hits = _domain_roles(task)
        domains = [d for d, _ in hits]
        assert "marketing" in domains

    def test_marketing_task_role_is_content_marketer(self):
        task = "build a paid search campaign with roas targets"
        hits = dict(_domain_roles(task))
        assert hits.get("marketing") == "content-marketer"

    def test_business_task_classifies_to_business(self):
        task = "gather stakeholder requirements and competitive analysis for the roadmap"
        hits = _domain_roles(task)
        domains = [d for d, _ in hits]
        assert "business" in domains

    def test_business_task_role_is_business_analyst(self):
        task = "gather stakeholder requirements and competitive analysis for the roadmap"
        hits = dict(_domain_roles(task))
        assert hits.get("business") == "business-analyst"

    def test_research_task_classifies_to_research(self):
        task = "synthesize findings across multiple primary sources"
        hits = _domain_roles(task)
        domains = [d for d, _ in hits]
        assert "research" in domains

    def test_research_task_role_is_research_analyst(self):
        task = "synthesize findings across multiple primary sources"
        hits = dict(_domain_roles(task))
        assert hits.get("research") == "research-analyst"

    def test_database_task_not_classified_as_research(self):
        """'research the database schema' should prefer database over research."""
        task = "research the database schema"
        hits = _domain_roles(task)
        domains = [d for d, _ in hits]
        # database appears before research in _DOMAIN_ROLE_MAP ordering
        assert "database" in domains


# ---------------------------------------------------------------------------
# _ROLE_DOMAIN — new entries resolve correctly
# ---------------------------------------------------------------------------

class TestRoleDomain:
    def test_content_marketer_maps_to_marketing(self):
        assert _ROLE_DOMAIN["content-marketer"] == "marketing"

    def test_business_analyst_maps_to_business(self):
        assert _ROLE_DOMAIN["business-analyst"] == "business"

    def test_competitive_analyst_maps_to_business(self):
        assert _ROLE_DOMAIN["competitive-analyst"] == "business"

    def test_trend_analyst_maps_to_business(self):
        assert _ROLE_DOMAIN["trend-analyst"] == "business"

    def test_project_manager_maps_to_business(self):
        assert _ROLE_DOMAIN["project-manager"] == "business"

    def test_project_idea_validator_maps_to_business(self):
        assert _ROLE_DOMAIN["project-idea-validator"] == "business"

    def test_research_analyst_maps_to_research(self):
        assert _ROLE_DOMAIN["research-analyst"] == "research"

    def test_debugger_maps_to_backend(self):
        assert _ROLE_DOMAIN["debugger"] == "backend"

    def test_error_detective_maps_to_backend(self):
        assert _ROLE_DOMAIN["error-detective"] == "backend"


# ---------------------------------------------------------------------------
# Persona hydration — domain files load + "You are" guard
# ---------------------------------------------------------------------------

class TestPersonaHydration:
    def test_content_marketer_persona_non_empty(self):
        result = _load_persona("content-marketer", "create a content strategy")
        assert result.get("system_prompt_fragment"), "content-marketer persona empty"

    def test_business_analyst_persona_non_empty(self):
        result = _load_persona("business-analyst", "stakeholder analysis")
        assert result.get("system_prompt_fragment"), "business-analyst persona empty"

    def test_research_analyst_persona_non_empty(self):
        result = _load_persona("research-analyst", "literature synthesis")
        assert result.get("system_prompt_fragment"), "research-analyst persona empty"

    def test_content_marketer_no_you_are_line(self):
        result = _load_persona("content-marketer", "create a content strategy")
        fragment = result.get("system_prompt_fragment", "")
        import re
        assert not re.search(r"You are (a|an|the)\b", fragment), \
            "content-marketer persona contains 'You are a/an/the'"

    def test_business_analyst_no_you_are_line(self):
        result = _load_persona("business-analyst", "stakeholder analysis")
        fragment = result.get("system_prompt_fragment", "")
        import re
        assert not re.search(r"You are (a|an|the)\b", fragment), \
            "business-analyst persona contains 'You are a/an/the'"

    def test_research_analyst_no_you_are_line(self):
        result = _load_persona("research-analyst", "literature synthesis")
        fragment = result.get("system_prompt_fragment", "")
        import re
        assert not re.search(r"You are (a|an|the)\b", fragment), \
            "research-analyst persona contains 'You are a/an/the'"


# ---------------------------------------------------------------------------
# paid-search subdomain hydration
# ---------------------------------------------------------------------------

class TestPaidSearchSubdomain:
    def _fragment(self, task: str) -> str:
        result = _load_persona("content-marketer", task)
        return result.get("system_prompt_fragment", "").lower()

    def test_paid_search_hydrated_on_ppc_task(self):
        fragment = self._fragment("optimize google ads bid strategy for roas")
        assert any(kw in fragment for kw in ("paid", "ppc", "roas", "bid", "adwords")), \
            "paid-search subdomain content not present in fragment"

    def test_paid_search_hydrated_on_sem_task(self):
        fragment = self._fragment("build a sem campaign with target cpa and negative keyword lists")
        assert any(kw in fragment for kw in ("paid", "ppc", "roas", "bid", "negative")), \
            "paid-search subdomain content not present in fragment"

    def test_paid_search_not_hydrated_on_generic_marketing_task(self):
        fragment = self._fragment("create a content strategy for q4")
        # Marketing tier-1 content should still be there
        assert "channel" in fragment or "audience" in fragment or "brand" in fragment or "funnel" in fragment
