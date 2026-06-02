from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_invoker import classifier
from agent_invoker.registry.loader import load_registry, Agent
from agent_invoker.domains import (
    _EXPLICIT_DOMAIN_ROLE,
    _count_domains,
    _collect_matches,
    _suggest_role,
    _complexity_score,
)
from agent_invoker.persona import _load_persona
from agent_invoker.decompose import DecomposeResult, _decompose_internal
from agent_invoker.sessions import (
    update_session,
)

_logger = logging.getLogger("invokerai.core")

LOG_PATH = Path.home() / ".invokerai" / "routing_log.jsonl"

PHASE2_MILESTONE = 200


@dataclass
class RoutingResult:
    routing: str
    role: str | None
    confidence: int
    tools: list[str]
    source: str = "regex"
    agent: Agent | None = field(default=None, repr=False)
    persona: dict = field(default_factory=dict)
    pattern: str | None = None
    steps: list[dict] = field(default_factory=list)
    spawn_count: int = 1
    candidates: list[dict] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def _regex_score(task: str, registry: dict[str, Agent]) -> dict:
    t = task.lower()
    direct_score = 0
    orchestrate_score = 0

    sentences = [s.strip() for s in re.split(r"[!?]|\.\s+", task) if s.strip()]
    if len(sentences) == 1:
        direct_score += 2
    elif len(sentences) >= 3:
        orchestrate_score += 1

    if re.match(r"^\s*(what|how|why|where|when|is|are|does|can|should)\b", t):
        direct_score += 2

    if re.search(r"\b(and then|after that|additionally|step \d|first.{0,5}then|once that)\b", t):
        orchestrate_score += 2

    imp_verbs = set(re.findall(
        r"\b(build|create|implement|deploy|test|review|refactor|migrate|audit|"
        r"integrate|add|fix|debug|analyze|design|update|remove|configure|write|generate)\b", t
    ))
    extra = max(0, len(imp_verbs) - 1)
    orchestrate_score += min(3, extra)

    domain_hits = _count_domains(t)
    if domain_hits >= 3:
        orchestrate_score += 4
    elif domain_hits == 2:
        orchestrate_score += 2
    elif domain_hits == 1:
        direct_score += 2
    else:
        direct_score += 1

    if re.search(r"[\w/\-]+\.\w{2,5}(?:\s|:|$|,)", task):
        direct_score += 2

    if re.search(r"\b(list|show|explain|read|check|view|describe|what is|how does|find|search)\b", t):
        direct_score += 2

    if re.search(r"\b(just|quick|simple|small|minor|single|only)\b", t):
        direct_score += 2

    if re.search(r"\b(thorough|complete|full|entire|comprehensive|end.to.end|all of)\b", t):
        orchestrate_score += 2

    if re.search(r"\b(then test|and review|plus document|also review|with tests|with docs|and deploy)\b", t):
        orchestrate_score += 2

    net = orchestrate_score - direct_score
    total = direct_score + orchestrate_score
    if net == 0:
        confidence = 50
    else:
        confidence = round(abs(net) / total * 100) if total > 0 else 0
    role = _suggest_role(t, imp_verbs, registry)

    return {
        "routing": "crew" if net > 0 else "solo",
        "suggested_role": role,
        "confidence": confidence,
        "source": "regex",
    }


def _log(task: str, result: RoutingResult) -> None:
    import sys
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps({
                "ts": int(time.time()),
                "task": task,
                "routing": result.routing,
                "role": result.role,
                "confidence": result.confidence,
                "source": result.source,
            }) + "\n")
        with LOG_PATH.open() as fh:
            count = sum(1 for _ in fh)
        if count == PHASE2_MILESTONE:
            print(
                f"\n[invokerai] {PHASE2_MILESTONE} routing decisions logged — ready for Phase 2.\n"
                f"  Phase 2 uses sentence embeddings and will improve accuracy on your actual workload.\n\n"
                f"    invoker train\n\n"
                f"  Log: {LOG_PATH}\n",
                file=sys.stderr,
            )
    except OSError:
        pass


def route(
    task: str,
    custom_registry: str | None = None,
    log: bool = True,
    domains: list[str] | None = None,
    session_id: str | None = None,
    complexity: str | None = None,
) -> RoutingResult:
    registry = load_registry(custom_registry)

    if complexity is None:
        complexity = _complexity_score(task)

    if domains:
        decomp = _decompose_internal(task, registry, explicit_domains=domains, complexity=complexity)
        execute_roles = [
            s["role"] for s in decomp.steps
            if s["role"] not in ("architect-reviewer", "code-reviewer", "cloud-architect")
        ]
        role = execute_roles[0] if execute_roles else _EXPLICIT_DOMAIN_ROLE.get(domains[0])
        confidence = 90
        source = "domains"
        routing = "crew"
        pattern = decomp.pattern
        steps = decomp.steps
        candidates = []
        reasoning = [f"explicit domains {domains} → {role}"]
    else:
        interim = _regex_score(task, registry)
        ml_determined_routing = False
        if interim["confidence"] < 70:
            ml = classifier.predict(task)
            if ml and ml["confidence"] > interim["confidence"]:
                ml_update = {k: v for k, v in ml.items() if k != "suggested_role" or v is not None}
                interim.update(ml_update)
                if interim.get("source") == "ml":
                    ml_determined_routing = True
        confidence = interim["confidence"]
        source = interim.get("source", "regex")

        matches = _collect_matches(task, registry)
        if matches:
            role = matches[0]["role"]
        else:
            role = interim.get("suggested_role")

        candidates = [{"role": m["role"]} for m in matches[1:3]]

        reasoning: list[str] = []
        if matches:
            m = matches[0]
            reasoning.append(f"trigger '{m['trigger']}' matched → {m['role']} ({m['category']})")
            if len(matches) > 1:
                runner_up_strs = [f"{x['role']} (trigger: '{x['trigger']}')" for x in matches[1:3]]
                reasoning.append(f"runner-ups: {', '.join(runner_up_strs)}")
        elif source == "ml-phase1" or source == "ml-phase2":
            reasoning.append(f"ML classifier ({source}) → {role} at {confidence}%")
        else:
            reasoning.append(f"regex fallback → {role}")
        reasoning.append(f"confidence: {confidence}% source: {source}")

        decomp = _decompose_internal(task, registry, complexity=complexity)
        pattern = decomp.pattern
        steps = decomp.steps

        if not ml_determined_routing:
            if len(matches) >= 2:
                categories = {m["category"] for m in matches}
                routing = "crew" if len(categories) >= 2 else "solo"
            else:
                routing = "solo"
        else:
            routing = interim.get("routing", "crew")

    agent = registry.get(role or "")
    tools = agent.tools if agent else []
    persona = _load_persona(role, task) if role else {}

    routing_result = RoutingResult(
        routing=routing,
        role=role,
        confidence=confidence,
        tools=tools,
        source=source,
        agent=agent,
        persona=persona,
        pattern=pattern,
        steps=steps,
        spawn_count=len(steps),
        candidates=candidates,
        reasoning=reasoning,
    )

    if log:
        _log(task, routing_result)
    if log and session_id:
        update_session(session_id, routing_result.role, routing_result.routing)

    return routing_result


def explain(task: str, custom_registry: str | None = None) -> dict:
    result = route(task, custom_registry=custom_registry, log=False)
    return {
        "role": result.role,
        "confidence": result.confidence,
        "source": result.source,
        "routing": result.routing,
        "reasoning": result.reasoning,
        "candidates": result.candidates,
        "pattern": result.pattern,
    }
