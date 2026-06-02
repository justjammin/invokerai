from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_invoker.registry.loader import Agent

from agent_invoker.domains import (
    PATTERN_PIPELINE,
    PATTERN_PARALLEL,
    PATTERN_SUPERVISOR,
    PATTERN_FEEDBACK_LOOP,
    PATTERN_HIERARCHICAL,
    PATTERN_PLAN_THEN_EXECUTE,
    _EXPLICIT_DOMAIN_ROLE,
    _ROLE_LABELS,
    _is_code_review_only,
    _domain_roles,
    _detect_pattern,
    _count_domains,
    _collect_matches,
    _suggest_role,
    _complexity_score,
)
from agent_invoker.registry.loader import load_registry


@dataclass
class DecomposeResult:
    pattern: str
    steps: list[dict]
    domain_roles: list[tuple[str, str]]
    bead_graph: dict = field(default_factory=dict)


def _to_bead_graph(steps: list[dict], pattern: str, task: str) -> dict:
    """Derive a bead DAG from steps[].

    Dep rules:
    - First step has no deps (deps=[]).
    - Parallel steps all depend on the most recent non-parallel step before them
      (or [] if none exists yet).
    - The first non-parallel step after a parallel block depends on ALL steps in
      that parallel block.
    - Non-parallel after non-parallel depends on the single prior non-parallel step.

    Annotation rules (Phase-1, informational only):
    - feedback_loop pattern → first code-reviewer node gets annotation="loop"
    - supervisor or hierarchical pattern → first architect-reviewer node gets
      annotation="expand"
    - All others → annotation=null
    """
    nodes = []
    last_np: str | None = None
    pending_parallel: list[str] = []

    for step in steps:
        sid = f"s{step['step']}"
        if step.get("parallel"):
            deps = [last_np] if last_np else []
            pending_parallel.append(sid)
        else:
            if pending_parallel:
                deps = pending_parallel[:]
            elif last_np:
                deps = [last_np]
            else:
                deps = []
            pending_parallel = []
            last_np = sid

        nodes.append({
            "id": sid,
            "role": step["role"],
            "action": step["action"],
            "deps": deps,
            "annotation": None,
        })

    # Apply annotations.
    if pattern == PATTERN_FEEDBACK_LOOP:
        for node in nodes:
            if node["role"] == "code-reviewer":
                node["annotation"] = "loop"
                break
    elif pattern in (PATTERN_SUPERVISOR, PATTERN_HIERARCHICAL):
        for node in nodes:
            if node["role"] == "architect-reviewer":
                node["annotation"] = "expand"
                break

    return {
        "root": {"title": task[:80], "type": "epic"},
        "nodes": nodes,
    }


def _generate_steps(
    t: str,
    pattern: str,
    domain_roles: list[tuple[str, str]],
    primary_role: str,
    complexity: str = "medium",
) -> list[dict]:
    fallback = domain_roles if domain_roles else [(None, primary_role)]

    if primary_role in ("debugger", "error-detective") and domain_roles:
        steps = [
            {"step": 1, "role": primary_role, "action": "Diagnose root cause", "parallel": False},
        ]
        for i, (domain, role) in enumerate(domain_roles[:3], start=2):
            steps.append({"step": i, "role": role, "action": f"Inspect {domain} layer", "parallel": True})
        steps.append({
            "step": len(domain_roles[:3]) + 2,
            "role": primary_role,
            "action": "Validate and apply fix",
            "parallel": False,
        })
        return steps

    if pattern == PATTERN_FEEDBACK_LOOP:
        return [
            {"step": 1, "role": "code-reviewer", "action": "Audit: quality, security, correctness", "parallel": False},
            {"step": 2, "role": "code-simplifier", "action": "Apply fixes and polish", "parallel": False},
        ]

    if pattern == PATTERN_PLAN_THEN_EXECUTE:
        steps = [{"step": 1, "role": "architect-reviewer", "action": "Create implementation plan", "parallel": False}]
        for i, (domain, role) in enumerate(fallback[:4], start=2):
            label = _ROLE_LABELS.get(role, domain or "task")
            steps.append({"step": i, "role": role, "action": f"Implement {label} per plan", "parallel": False})
        return steps

    if pattern == PATTERN_PARALLEL:
        steps = []
        for i, (domain, role) in enumerate(fallback[:4], start=1):
            label = _ROLE_LABELS.get(role, domain or "task")
            steps.append({"step": i, "role": role, "action": f"Implement {label}", "parallel": True})
        if complexity == "high":
            steps.append({"step": len(steps) + 1, "role": "integration-engineer", "action": "Wire parallel outputs: resolve interface mismatches, produce integration glue", "parallel": False})
        return steps

    if pattern == PATTERN_SUPERVISOR:
        workers = [r for _, r in domain_roles[:3]] or [primary_role]
        steps = [{"step": 1, "role": "architect-reviewer", "action": "Decompose and assign work", "parallel": False}]
        for i, role in enumerate(workers, start=2):
            steps.append({"step": i, "role": role, "action": "Execute assigned subtask", "parallel": False})
        steps.append({"step": len(steps) + 1, "role": "architect-reviewer", "action": "Review and integrate", "parallel": False})
        return steps

    if pattern == PATTERN_HIERARCHICAL:
        steps = [{"step": 1, "role": "architect-reviewer", "action": "Top-level decomposition", "parallel": False}]
        for i, (domain, role) in enumerate(fallback[:3], start=2):
            label = _ROLE_LABELS.get(role, domain or "domain")
            steps.append({"step": i, "role": role, "action": f"Lead {label} cluster", "parallel": i > 2})
        steps.append({"step": len(steps) + 1, "role": "architect-reviewer", "action": "Final integration review", "parallel": False})
        return steps

    steps = []
    for i, (domain, role) in enumerate(fallback[:5], start=1):
        label = _ROLE_LABELS.get(role, domain or "task")
        steps.append({"step": i, "role": role, "action": f"Implement {label}", "parallel": False})
    return steps


def _generate_steps_v2(domains: list[str], task: str, complexity: str = "medium") -> list[dict]:
    """Universal MAS structure: PLAN → EXECUTE → REVIEW → DEPLOY(optional)."""
    step_num = 1
    steps: list[dict] = []
    code_review_only = _is_code_review_only(domains)

    if code_review_only:
        steps.append({"step": step_num, "role": "code-reviewer", "action": "Review code quality and issues", "parallel": False})
        step_num += 1
        steps.append({"step": step_num, "role": "code-simplifier", "action": "Apply fixes and polish", "parallel": False})
        return steps

    # Step 1: PLAN — only if architecture domain explicitly requested
    if "architecture" in domains:
        steps.append({"step": step_num, "role": "architect-reviewer", "action": "Create implementation plan", "parallel": False})
        step_num += 1

    # Step 2+: EXECUTE (exclude architecture/code-review/devops — handled separately)
    execute_domains = [d for d in domains if d not in ("architecture", "code-review", "devops")]

    # CONTRACT NEGOTIATION: inject api-designer before execute when backend meets
    # frontend/mobile and no architecture step already covers interface design.
    needs_contract = (
        "backend" in execute_domains
        and any(d in execute_domains for d in ("frontend", "mobile"))
        and "architecture" not in domains
    )
    if needs_contract:
        steps.append({
            "step": step_num,
            "role": "api-designer",
            "action": "Define API contract: endpoints, request/response shapes, auth scheme",
            "parallel": False,
        })
        step_num += 1

    # ML ordering: data before ml
    ordered: list[str] = []
    if "ml" in execute_domains and "data" in execute_domains:
        ordered = [d for d in execute_domains if d not in ("ml", "data")] + ["data", "ml"]
    else:
        ordered = execute_domains

    is_parallel = len(ordered) >= 3
    for domain in ordered:
        role = _EXPLICIT_DOMAIN_ROLE.get(domain, "backend-developer")
        label = _ROLE_LABELS.get(role, domain)
        steps.append({"step": step_num, "role": role, "action": f"Implement {label}", "parallel": is_parallel})
        step_num += 1

    if is_parallel and complexity == "high":
        steps.append({"step": step_num, "role": "integration-engineer", "action": "Wire parallel outputs: resolve interface mismatches, produce integration glue", "parallel": False})
        step_num += 1

    # Step N: REVIEW
    reviewer = "architect-reviewer" if "architecture" in domains else "code-reviewer"
    steps.append({"step": step_num, "role": reviewer, "action": "Review output", "parallel": False})
    step_num += 1

    if "code-review" in domains:
        steps.append({"step": step_num, "role": "code-reviewer", "action": "Review code quality and issues", "parallel": False})
        step_num += 1
        steps.append({"step": step_num, "role": "code-simplifier", "action": "Apply fixes and polish", "parallel": False})
        step_num += 1

    # DEPLOY PLAN (only if devops)
    if "devops" in domains:
        steps.append({"step": step_num, "role": "cloud-architect", "action": "Write deployment plan", "parallel": False})

    return steps


def _decompose_internal(task: str, registry: dict[str, Agent], explicit_domains: list[str] | None = None, complexity: str = "medium") -> "DecomposeResult":
    t = task.lower()

    if explicit_domains:
        steps = _generate_steps_v2(explicit_domains, task, complexity=complexity)
        if _is_code_review_only(explicit_domains):
            pattern = PATTERN_FEEDBACK_LOOP
        elif len([d for d in explicit_domains if d not in ("architecture", "code-review", "devops")]) >= 3:
            pattern = PATTERN_PARALLEL
        else:
            pattern = PATTERN_PIPELINE
        dr = _domain_roles(t, explicit=explicit_domains)
        return DecomposeResult(
            pattern=pattern,
            steps=steps,
            domain_roles=dr,
            bead_graph=_to_bead_graph(steps, pattern, task),
        )

    imp_verbs = set(re.findall(
        r"\b(build|create|implement|deploy|test|review|refactor|migrate|audit|"
        r"integrate|add|fix|debug|analyze|design|update|remove|configure|write|generate)\b", t
    ))
    domain_hits = _count_domains(t)
    pattern = _detect_pattern(t, domain_hits)
    dr = _domain_roles(t)
    primary_role = _suggest_role(t, imp_verbs, registry)
    steps = _generate_steps(t, pattern, dr, primary_role, complexity=complexity)
    return DecomposeResult(
        pattern=pattern,
        steps=steps,
        domain_roles=dr,
        bead_graph=_to_bead_graph(steps, pattern, task),
    )


def decompose(task: str, custom_registry: str | None = None, domains: list[str] | None = None, complexity: str | None = None) -> "DecomposeResult":
    """Detect orchestration pattern and generate skeleton steps for a multi-agent task."""
    registry = load_registry(custom_registry)
    if complexity is None:
        complexity = _complexity_score(task)
    return _decompose_internal(task, registry, explicit_domains=domains, complexity=complexity)
