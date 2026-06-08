"""agent_select.py — Stage 2 routing: map domain → installed agent from agent-map.json.

Resolves plan role/domain slots to real installed agent names, ensuring every
emitted name is a key present in the user's agent-map.json.

Public API:
    select_agent(domain, task_text, agent_map) -> dict | None
    resolve_plan(task_text, plan, agent_map) -> dict
    load_agent_map(map_path) -> dict
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DEFAULT_MAP_PATH = Path.home() / ".invoker" / "agent-map.json"

# Guaranteed-present fallback name — used when a domain has no installed agents.
_FALLBACK_AGENT = "general-purpose"


# ---------------------------------------------------------------------------
# Bucket lookup — find the map key for a domain, with fuzzy fallback
# ---------------------------------------------------------------------------

def _find_bucket(domain: str, agent_map: dict) -> str | None:
    """Return the agent-map bucket key for a domain.

    Priority:
      1. Exact match (fastest path, handles any naming convention)
      2. Map key contains domain as substring ("backend" in "engineering-backend")
      3. Domain contains map key as substring ("engineering-backend" contains "backend")

    Returns None if no match found.
    """
    domains = agent_map.get("domains", {})
    if domain in domains:
        return domain
    for key in domains:
        if domain in key or key in domain:
            return key
    return None


# ---------------------------------------------------------------------------
# Scoring — term-overlap between task_text and candidate description
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens, length >= 3, stripped of punctuation."""
    return {w for w in re.findall(r"[a-z]{3,}", text.lower())}


def _score_candidate(task_tokens: set[str], description: str) -> int:
    """Return overlap count between task tokens and description tokens.

    Also adds a bonus for each task token that appears as a substring of the
    description (catches partial matches like 'competitor' inside 'competitors').
    """
    desc_tokens = _tokenize(description)
    desc_lower = description.lower()

    exact = len(task_tokens & desc_tokens)
    # Substring bonus: task token appears anywhere in description (e.g. 'milestone' in description)
    substring = sum(1 for t in task_tokens if t in desc_lower and t not in desc_tokens)
    return exact + substring


# ---------------------------------------------------------------------------
# Public: select_agent
# ---------------------------------------------------------------------------

def select_agent(
    domain: str,
    task: str,
    agent_map: dict,
    task_text: str | None = None,
) -> dict | None:
    """Select the best installed agent for a domain given a task description.

    Parameters
    ----------
    domain:     The routing domain (e.g. "backend", "business").
    task:       Kept for signature compatibility; scoring uses task_text.
    agent_map:  The parsed agent-map dict ({"domains": {...}, ...}).
    task_text:  The actual task string to score against candidate descriptions.
                Falls back to `task` if None.

    Returns
    -------
    The matching candidate dict {name, description, tools, model, source} or
    None if the domain has no candidates.
    """
    scoring_text = task_text if task_text is not None else task
    bucket_key = _find_bucket(domain, agent_map)
    candidates: list[dict] = agent_map.get("domains", {}).get(bucket_key, []) if bucket_key else []

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Score all candidates, pick the highest.  Tiebreak: alphabetical by name
    # (deterministic, no implicit ordering dependency on map file order).
    task_tokens = _tokenize(scoring_text)
    scored = [
        (_score_candidate(task_tokens, c.get("description", "")), c["name"], c)
        for c in candidates
    ]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][2]


# ---------------------------------------------------------------------------
# Public: resolve_plan
# ---------------------------------------------------------------------------

def resolve_plan(
    task_text: str,
    plan: dict,
    agent_map: dict,
) -> dict:
    """Resolve stage-1 routing plan to installed agent names.

    Parameters
    ----------
    task_text:  The original task string (drives within-domain scoring).
    plan:       Dict with at minimum {"routing": "solo"|"crew", ...} and the
                stage-1 fields: role (solo), steps (crew), pattern, domains.
    agent_map:  Parsed agent-map JSON dict.

    Returns
    -------
    Lean resolved plan:
        {
            routing: "solo"|"crew",
            agent: <name>          # solo only
            steps: [{...}]         # crew only — each step has "agent" key added
            pattern: <str>,
            domains: [...],
            coverage_gaps: [...],  # non-empty when fallback was used
        }
    """
    from agent_invoker.domains import _ROLE_DOMAIN

    routing = plan.get("routing", "solo")
    coverage_gaps: list[dict] = []

    def _resolve_domain(domain: str) -> str:
        """Resolve a domain to an installed agent name, using fallback if needed."""
        candidate = select_agent(domain, task_text, agent_map, task_text=task_text)
        if candidate is None:
            coverage_gaps.append({"domain": domain, "fallback": _FALLBACK_AGENT})
            return _FALLBACK_AGENT
        return candidate["name"]

    def _domain_for_role(role: str) -> str | None:
        """Map a built-in registry role hint to its domain."""
        return _ROLE_DOMAIN.get(role)

    if routing == "solo":
        stage1_role = plan.get("role")
        resolved_bucket = None
        agent_name = None

        if stage1_role:
            # 1. Map-direct: agent-map is source of truth
            resolved_bucket = _find_bucket(stage1_role, agent_map)
            if resolved_bucket:
                agent_name = _resolve_domain(resolved_bucket)
            else:
                # 2. _ROLE_DOMAIN bridge: legacy role-name → short domain → map bucket
                legacy_domain = _domain_for_role(stage1_role)
                if legacy_domain:
                    resolved_bucket = legacy_domain
                    agent_name = _resolve_domain(legacy_domain)

        if agent_name is None:
            coverage_gaps.append({"domain": stage1_role or "unknown", "fallback": _FALLBACK_AGENT})
            agent_name = _FALLBACK_AGENT

        return {
            "routing": "solo",
            "agent": agent_name,
            "pattern": plan.get("pattern"),
            "domains": plan.get("domains", [resolved_bucket] if resolved_bucket else []),
            "coverage_gaps": coverage_gaps,
        }

    # crew
    raw_steps: list[dict] = plan.get("steps", [])
    resolved_steps = []
    seen_domains: list[str] = []
    map_names: set[str] = {
        e["name"]
        for bucket in agent_map.get("domains", {}).values()
        for e in bucket
        if isinstance(e, dict) and "name" in e
    }

    for step in raw_steps:
        step_role = step.get("role", "")
        resolved_bucket = None

        # 1. Map-direct: agent-map is source of truth
        direct = _find_bucket(step_role, agent_map)
        if direct:
            resolved_bucket = direct
            if resolved_bucket not in seen_domains:
                seen_domains.append(resolved_bucket)
            agent_name = _resolve_domain(resolved_bucket)
        else:
            # 2. _ROLE_DOMAIN bridge: legacy role-name → short domain → map bucket
            legacy_domain = _domain_for_role(step_role)
            if legacy_domain:
                resolved_bucket = legacy_domain
                if legacy_domain not in seen_domains:
                    seen_domains.append(legacy_domain)
                agent_name = _resolve_domain(legacy_domain)
            elif step_role in map_names:
                # 3. Direct agent name in map
                agent_name = step_role
            else:
                # 4. Fallback
                coverage_gaps.append({"domain": step_role, "fallback": _FALLBACK_AGENT})
                agent_name = _FALLBACK_AGENT

        resolved_steps.append({
            **step,
            "domain": resolved_bucket or step_role,
            "agent": agent_name,
        })

    return {
        "routing": "crew",
        "steps": resolved_steps,
        "pattern": plan.get("pattern"),
        "domains": plan.get("domains", seen_domains),
        "coverage_gaps": coverage_gaps,
    }


# ---------------------------------------------------------------------------
# Public: load_agent_map
# ---------------------------------------------------------------------------

def load_agent_map(map_path: Path | None = None) -> dict | None:
    """Load agent-map.json from disk.

    Returns the parsed dict, or None if the file is missing/corrupt.
    Caller should treat None as "run invoker setup first".
    """
    import json

    path = map_path or _DEFAULT_MAP_PATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        data.setdefault("domains", {})
        return data
    except (json.JSONDecodeError, OSError):
        return None
