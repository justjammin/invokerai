from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_invoker.registry.loader import load_registry, Agent
from agent_invoker import classifier

LOG_PATH = Path.home() / ".invokerai" / "routing_log.jsonl"
_AGENTS_DIR = Path.home() / ".claude" / "agents"


def _load_persona(role: str) -> dict:
    """Read persona from ~/.claude/agents/{role}.md — body after frontmatter is system_prompt_fragment."""
    agent_file = _AGENTS_DIR / f"{role}.md"
    if not agent_file.exists():
        return {"resource_uri": f"agent://{role}"}
    content = agent_file.read_text()
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            body = content[end + 4:].strip()
    return {
        "resource_uri": f"agent://{role}",
        "system_prompt_fragment": body[:2000],
    }


@dataclass
class RoutingResult:
    routing: str
    role: str | None
    confidence: int
    tools: list[str]
    source: str = "regex"
    agent: Agent | None = field(default=None, repr=False)
    persona: dict = field(default_factory=dict)


def route(
    task: str,
    custom_registry: str | None = None,
    log: bool = True,
) -> RoutingResult:
    registry = load_registry(custom_registry)

    result = _regex_score(task, registry)

    if result["confidence"] < 70:
        ml = classifier.predict(task)
        if ml and ml["confidence"] > result["confidence"]:
            result.update(ml)

    agent = registry.get(result.get("suggested_role") or "")
    tools = agent.tools if agent else []

    role = result.get("suggested_role")
    routing_result = RoutingResult(
        routing=result["routing"],
        role=role,
        confidence=result["confidence"],
        tools=tools,
        source=result.get("source", "regex"),
        agent=agent,
        persona=_load_persona(role) if role else {},
    )

    if log:
        _log(task, routing_result)

    return routing_result


def _regex_score(task: str, registry: dict[str, Agent]) -> dict:
    t = task.lower()
    direct_score = 0
    orchestrate_score = 0

    # Single vs multi-sentence
    sentences = [s.strip() for s in re.split(r"[!?]|\.\s+", task) if s.strip()]
    if len(sentences) == 1:
        direct_score += 2
    elif len(sentences) >= 3:
        orchestrate_score += 1

    # Question form → direct
    if re.match(r"^\s*(what|how|why|where|when|is|are|does|can|should)\b", t):
        direct_score += 2

    # Multi-step connectors → orchestrate
    if re.search(r"\b(and then|after that|additionally|step \d|first.{0,5}then|once that)\b", t):
        orchestrate_score += 2

    # Imperative verb count
    imp_verbs = set(re.findall(
        r"\b(build|create|implement|deploy|test|review|refactor|migrate|audit|"
        r"integrate|add|fix|debug|analyze|design|update|remove|configure|write|generate)\b", t
    ))
    extra = max(0, len(imp_verbs) - 1)
    orchestrate_score += min(3, extra)

    # Domain breadth
    domain_hits = _count_domains(t)
    if domain_hits >= 3:
        orchestrate_score += 4
    elif domain_hits == 2:
        orchestrate_score += 2
    elif domain_hits == 1:
        direct_score += 2
    else:
        direct_score += 1

    # File path = concrete = direct
    if re.search(r"[\w/\-]+\.\w{2,5}(?:\s|:|$|,)", task):
        direct_score += 2

    # Read-only intent
    if re.search(r"\b(list|show|explain|read|check|view|describe|what is|how does|find|search)\b", t):
        direct_score += 2

    # Quick modifier
    if re.search(r"\b(just|quick|simple|small|minor|single|only)\b", t):
        direct_score += 2

    # Thoroughness
    if re.search(r"\b(thorough|complete|full|entire|comprehensive|end.to.end|all of)\b", t):
        orchestrate_score += 2

    # Multi-role implied
    if re.search(r"\b(then test|and review|plus document|also review|with tests|with docs|and deploy)\b", t):
        orchestrate_score += 2

    net = orchestrate_score - direct_score
    total = direct_score + orchestrate_score
    confidence = round(abs(net) / total * 100) if total > 0 else 0

    routing = "orchestrate" if net >= 0 else "direct"
    role = _suggest_role(t, imp_verbs, registry) if routing == "direct" else None

    return {
        "routing": routing,
        "suggested_role": role,
        "confidence": confidence,
        "source": "regex",
    }


def _count_domains(t: str) -> int:
    patterns = {
        "frontend": r"\b(css|html|react|vue|angular|svelte|jsx|tsx|dom|browser|component)\b",
        "backend": r"\b(api|endpoint|service|server|controller|middleware|route|handler|rest|graphql)\b",
        "database": r"\b(sql|query|schema|migration|index|table|database|\bdb\b|orm|postgres|mysql|mongo)\b",
        "devops": r"\b(deploy|docker|kubernetes|k8s|\bci\b|\bcd\b|pipeline|infra|cloud|aws|gcp|terraform)\b",
        "security": r"\b(auth|oauth|jwt|permission|role|encrypt|credential|secret)\b",
        "ml": r"\b(model|training|inference|embedding|\bllm\b|fine.?tun|rag|vector|neural)\b",
    }
    return sum(1 for p in patterns.values() if re.search(p, t))


def _suggest_role(t: str, imp_verbs: set[str], registry: dict[str, Agent]) -> str:
    # Error signals — check first
    if re.search(r"\b(typeerror|valueerror|exception|traceback|500|undefined is not|cannot read)\b", t):
        if re.search(r"\b(correlate|across service|pattern|root cause.*multiple)\b", t):
            return "error-detective"
        return "debugger"

    if "debug" in imp_verbs or re.search(r"\b(bug|broken|not working|failing|error|crash)\b", t):
        return "debugger"

    if re.search(r"\b(security review|vulnerability|owasp|injection|xss|csrf)\b", t):
        return "code-reviewer"

    if re.search(r"\b(review|audit|code review|second opinion)\b", t):
        return "code-reviewer"

    if "refactor" in imp_verbs:
        return "refactoring-specialist"

    if re.search(r"\b(architect|system design|trade.?off|adr)\b", t):
        return "architect-reviewer"

    if "test" in imp_verbs or re.search(r"\b(spec|unit test|integration test|e2e|test coverage)\b", t):
        return "test-automator"

    if re.search(r"\b(model|training|inference|embedding|\bllm\b|rag|vector)\b", t):
        return "ml-engineer"

    if re.search(r"\b(postgres|mysql|mongo|redis|sql|query|schema|migration|index)\b", t):
        return "database-optimizer"

    if re.search(r"\b(deploy|docker|kubernetes|k8s|terraform|cloud|aws|gcp|azure)\b", t):
        return "cloud-architect"

    # Trigger matching against registry
    for agent in registry.values():
        if agent.orchestrate:
            continue
        for trigger in agent.triggers:
            if trigger in t:
                return agent.id

    if re.search(r"\b(css|html|react|vue|angular|component|frontend)\b", t):
        return "frontend-developer"

    if re.search(r"\b(api|endpoint|server|backend|service)\b", t):
        return "backend-developer"

    if re.search(r"\b(explain|analyze|why|how does|what is|describe)\b", t):
        return "architect-reviewer"

    if re.search(r"\b(document|docs|readme|guide|tutorial)\b", t):
        return "technical-writer"

    return "backend-developer"


PHASE2_MILESTONE = 200


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
        count = sum(1 for _ in LOG_PATH.open())
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