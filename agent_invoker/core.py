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
_REPO_AGENTS_DIR = Path(__file__).parent.parent / "agents"

_ROLE_DOMAIN: dict[str, str] = {
    "backend-developer": "backend",
    "fullstack-developer": "backend",
    "fastapi-developer": "backend",
    "django-developer": "backend",
    "laravel-specialist": "backend",
    "symfony-specialist": "backend",
    "python-pro": "backend",
    "php-pro": "backend",
    "golang-pro": "backend",
    "javascript-pro": "backend",
    "typescript-pro": "backend",
    "mcp-developer": "backend",
    "frontend-developer": "frontend",
    "react-specialist": "frontend",
    "ui-designer": "frontend",
    "database-optimizer": "database",
    "database-administrator": "database",
    "postgres-pro": "database",
    "data-engineer": "data",
    "data-analyst": "data",
    "cloud-architect": "devops",
    "kubernetes-specialist": "devops",
    "git-workflow-manager": "devops",
    "dx-optimizer": "devops",
    "code-reviewer": "code-review",
    "refactoring-specialist": "code-review",
    "legacy-modernizer": "code-review",
    "ml-engineer": "ml",
    "machine-learning-engineer": "ml",
    "llm-architect": "ml",
    "data-scientist": "ml",
    "test-automator": "testing",
    "technical-writer": "documentation",
    "documentation-engineer": "documentation",
    "readme-generator": "documentation",
    "mobile-developer": "mobile",
    "mobile-app-developer": "mobile",
    "expo-react-native-expert": "mobile",
    "swift-expert": "mobile",
    "architect-reviewer": "architecture",
    "microservices-architect": "architecture",
    "api-designer": "architecture",
}

_SUBDOMAIN_TRIGGERS: list[tuple[str, str, list[str]]] = [
    ("backend", "python", ["python", "fastapi", "django", "flask", "asyncio", "pydantic", ".py"]),
    ("backend", "php", ["php", "laravel", "symfony", "composer", "artisan", "eloquent"]),
    ("backend", "go", ["golang", " go ", "goroutine", "gin framework", "fiber framework"]),
    ("backend", "node", ["node.js", "nodejs", "express", "koa", "hapi"]),
    ("backend", "typescript", ["typescript", " ts ", ".ts ", "tsconfig"]),
    ("frontend", "react", ["react", "jsx", "tsx", "hooks", "zustand", "redux"]),
    ("frontend", "typescript", ["typescript", " ts ", ".tsx", "tsconfig"]),
    ("database", "postgres", ["postgres", "postgresql", "pg_", "pgbouncer", "vacuum"]),
    ("devops", "kubernetes", ["kubernetes", "k8s", "helm", "kubectl", "pod ", "deployment yaml"]),
    ("devops", "git", ["git ", "branch", "rebase", "merge strategy", "git flow", "trunk"]),
    ("mobile", "react-native", ["react native", "react-native", "expo", "rn "]),
    ("mobile", "swift", ["swift", "swiftui", "uikit", "xcode", "ios ", "macos app"]),
    ("ml", "llm", ["llm", "rag", "prompt", "embedding", "langchain", "langgraph", "openai", "anthropic"]),
    ("ml", "training", ["pytorch", "tensorflow", "sklearn", "model training", "fine-tun", "checkpoint"]),
]

_TIER3_TRIGGERS: list[tuple[str, str, str, list[str]]] = [
    ("backend", "python", "fastapi", ["fastapi", "asgi", "uvicorn", "starlette"]),
    ("backend", "python", "django", ["django", "drf", "django rest", "django orm"]),
    ("backend", "php", "laravel", ["laravel", "eloquent", "artisan", "livewire", "blade"]),
    ("backend", "php", "symfony", ["symfony", "doctrine", "twig", "messenger", "api platform"]),
    ("mobile", "react-native", "expo", ["expo", "eas build", "eas ", "expo-updates", "expo-modules"]),
]


def _read_agent_body(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            return content[end + 4:].strip()
    return content


def _resolve_agent_file(relative: str) -> "Path | None":
    for base in (_AGENTS_DIR, _REPO_AGENTS_DIR):
        candidate = base / relative
        if candidate.exists():
            return candidate
    return None


def _load_persona(role: str, task: str = "") -> dict:
    domain = _ROLE_DOMAIN.get(role)
    t = task.lower()
    tiers: list[str] = []

    if domain:
        tier1_file = _resolve_agent_file(f"{domain}.md")
        if tier1_file:
            tiers.append(_read_agent_body(tier1_file))

            subdomain: str | None = None
            for d, sub, keywords in _SUBDOMAIN_TRIGGERS:
                if d == domain and any(kw in t for kw in keywords):
                    subdomain = sub
                    break

            if subdomain:
                tier2_file = _resolve_agent_file(f"{domain}/{subdomain}.md")
                if tier2_file:
                    tiers.append(_read_agent_body(tier2_file))

                    for d, sub, specialist, keywords in _TIER3_TRIGGERS:
                        if d == domain and sub == subdomain and any(kw in t for kw in keywords):
                            tier3_file = _resolve_agent_file(f"{domain}/{subdomain}/{specialist}.md")
                            if tier3_file:
                                tiers.append(_read_agent_body(tier3_file))
                            break

    if tiers:
        composed = "\n\n---\n\n".join(tiers)
        return {
            "resource_uri": f"agent://{role}",
            "system_prompt_fragment": composed[:6000],
        }

    # Flat-file fallback (old naming convention)
    flat_file = _resolve_agent_file(f"{role}.md")
    if flat_file:
        return {
            "resource_uri": f"agent://{role}",
            "system_prompt_fragment": _read_agent_body(flat_file)[:6000],
        }

    return {"resource_uri": f"agent://{role}"}


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


@dataclass
class DecomposeResult:
    pattern: str
    steps: list[dict]
    domain_roles: list[tuple[str, str]]


def route(
    task: str,
    custom_registry: str | None = None,
    log: bool = True,
    domains: list[str] | None = None,
) -> RoutingResult:
    registry = load_registry(custom_registry)

    if domains:
        decomp = _decompose_internal(task, registry, explicit_domains=domains)
        execute_roles = [
            s["role"] for s in decomp.steps
            if s["role"] not in ("architect-reviewer", "code-reviewer", "cloud-architect")
        ]
        role = execute_roles[0] if execute_roles else _EXPLICIT_DOMAIN_ROLE.get(domains[0])
        confidence = 90
        source = "domains"
        pattern = decomp.pattern
        steps = decomp.steps
    else:
        interim = _regex_score(task, registry)
        if interim["confidence"] < 70:
            ml = classifier.predict(task)
            if ml and ml["confidence"] > interim["confidence"]:
                interim.update(ml)
        confidence = interim["confidence"]
        source = interim.get("source", "regex")
        role = interim.get("suggested_role")
        decomp = _decompose_internal(task, registry)
        pattern = decomp.pattern
        steps = decomp.steps

    agent = registry.get(role or "")
    tools = agent.tools if agent else []

    routing_result = RoutingResult(
        routing="orchestrate",
        role=role,
        confidence=confidence,
        tools=tools,
        source=source,
        agent=agent,
        persona=_load_persona(role, task) if role else {},
        pattern=pattern,
        steps=steps,
        spawn_count=len(steps),
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
    if net == 0:
        confidence = 50
    else:
        confidence = round(abs(net) / total * 100) if total > 0 else 0
    role = _suggest_role(t, imp_verbs, registry)

    return {
        "routing": "orchestrate",
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


# ── MAS orchestration patterns ────────────────────────────────────────────────

PATTERN_PIPELINE = "pipeline"
PATTERN_PARALLEL = "parallel"
PATTERN_SUPERVISOR = "supervisor"
PATTERN_FEEDBACK_LOOP = "feedback_loop"
PATTERN_HIERARCHICAL = "hierarchical"
PATTERN_PLAN_THEN_EXECUTE = "plan_then_execute"

# Canonical domain → role mapping (explicit domains from agent)
_EXPLICIT_DOMAIN_ROLE: dict[str, str] = {
    "architecture": "architect-reviewer",
    "backend": "backend-developer",
    "frontend": "frontend-developer",
    "database": "database-optimizer",
    "devops": "cloud-architect",
    "security": "code-reviewer",
    "ml": "ml-engineer",
    "testing": "test-automator",
    "documentation": "technical-writer",
    "mobile": "mobile-developer",
    "data": "data-engineer",
    "code-review": "code-reviewer",
}

CANONICAL_DOMAINS = list(_EXPLICIT_DOMAIN_ROLE.keys())

_DOMAIN_ROLE_MAP: list[tuple[str, str, str]] = [
    ("frontend", r"\b(css|html|react|vue|angular|svelte|jsx|tsx|dom|browser|component)\b", "frontend-developer"),
    ("backend", r"\b(api|endpoint|service|server|controller|middleware|route|handler|rest|graphql)\b", "backend-developer"),
    ("database", r"\b(sql|query|schema|migration|index|table|database|\bdb\b|orm|postgres|mysql|mongo)\b", "database-optimizer"),
    ("devops", r"\b(deploy|docker|kubernetes|k8s|\bci\b|\bcd\b|pipeline|infra|cloud|aws|gcp|terraform)\b", "cloud-architect"),
    ("security", r"\b(auth|oauth|jwt|permission|role|encrypt|credential|secret)\b", "code-reviewer"),
    ("ml", r"\b(model|training|inference|embedding|\bllm\b|fine.?tun|rag|vector|neural)\b", "ml-engineer"),
    ("testing", r"\b(test|spec|coverage|e2e)\b", "test-automator"),
    ("docs", r"\b(document|docs|readme|guide|tutorial)\b", "technical-writer"),
]

_ROLE_LABELS: dict[str, str] = {
    "frontend-developer": "UI layer",
    "backend-developer": "API layer",
    "database-optimizer": "data layer",
    "cloud-architect": "infrastructure",
    "code-reviewer": "security/quality",
    "ml-engineer": "ML pipeline",
    "test-automator": "test suite",
    "technical-writer": "documentation",
    "architect-reviewer": "architecture",
    "fullstack-developer": "integration",
    "mobile-developer": "mobile layer",
    "data-engineer": "data pipeline",
}


def _is_code_review_only(domains: list[str]) -> bool:
    return domains == ["code-review"] or set(domains) == {"code-review"}


def _domain_roles(t: str, explicit: list[str] | None = None) -> list[tuple[str, str]]:
    if explicit:
        return [(d, _EXPLICIT_DOMAIN_ROLE[d]) for d in explicit if d in _EXPLICIT_DOMAIN_ROLE]
    return [(domain, role) for domain, pattern, role in _DOMAIN_ROLE_MAP if re.search(pattern, t)]


def _detect_pattern(t: str, domain_hits: int) -> str:
    if (
        re.search(r"\bfeedback.{0,10}loop\b", t)
        or re.search(r"\biterate.{0,20}until\b", t)
        or re.search(r"\bcritic.{0,15}revise\b", t)
        or (re.search(r"\breview\b", t) and re.search(r"\brevise?\b", t))
    ):
        return PATTERN_FEEDBACK_LOOP
    if re.search(r"\b(plan.{0,10}then|design.{0,30}first|research.{0,20}(then|before)|spec.{0,10}then)\b", t):
        return PATTERN_PLAN_THEN_EXECUTE
    if re.search(r"\b(in parallel|simultaneously|at the same time|concurrently)\b", t):
        return PATTERN_PARALLEL
    if domain_hits >= 3 and re.search(r"\b(full.?stack|entire|end.to.end|enterprise|platform|system)\b", t):
        return PATTERN_HIERARCHICAL
    if re.search(r"\b(manage|coordinate|oversee).{0,20}(agent|team|specialist|worker)\b", t):
        return PATTERN_SUPERVISOR
    return PATTERN_PIPELINE


def _generate_steps(
    t: str,
    pattern: str,
    domain_roles: list[tuple[str, str]],
    primary_role: str,
) -> list[dict]:
    fallback = domain_roles if domain_roles else [(None, primary_role)]

    if pattern == PATTERN_FEEDBACK_LOOP:
        generator = primary_role
        return [
            {"step": 1, "role": generator, "action": "Initial implementation", "parallel": False},
            {"step": 2, "role": "code-reviewer", "action": "Review and critique", "parallel": False},
            {"step": 3, "role": generator, "action": "Revise per feedback", "parallel": False},
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
        steps.append({"step": len(steps) + 1, "role": "fullstack-developer", "action": "Integration and wiring", "parallel": False})
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

    # PIPELINE (default) — ordered sequential
    steps = []
    for i, (domain, role) in enumerate(fallback[:5], start=1):
        label = _ROLE_LABELS.get(role, domain or "task")
        steps.append({"step": i, "role": role, "action": f"Implement {label}", "parallel": False})
    return steps


def _generate_steps_v2(domains: list[str], task: str) -> list[dict]:
    """Universal MAS structure: PLAN → EXECUTE → REVIEW → DEPLOY(optional)."""
    step_num = 1
    steps: list[dict] = []
    code_review_only = _is_code_review_only(domains)

    if code_review_only:
        # feedback loop: review → assess — no plan step
        steps.append({"step": step_num, "role": "code-reviewer", "action": "Review code quality and issues", "parallel": False})
        step_num += 1
        steps.append({"step": step_num, "role": "architect-reviewer", "action": "Architectural assessment", "parallel": False})
        return steps

    # Step 1: PLAN
    steps.append({"step": step_num, "role": "architect-reviewer", "action": "Create implementation plan", "parallel": False})
    step_num += 1

    # Step 2+: EXECUTE (exclude architecture/code-review/devops — handled separately)
    execute_domains = [d for d in domains if d not in ("architecture", "code-review", "devops")]

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

    if is_parallel:
        steps.append({"step": step_num, "role": "fullstack-developer", "action": "Integration and wiring", "parallel": False})
        step_num += 1

    # Step N: REVIEW
    reviewer = "architect-reviewer" if "architecture" in domains else "code-reviewer"
    steps.append({"step": step_num, "role": reviewer, "action": "Review output", "parallel": False})
    step_num += 1

    # Step N+1: DEPLOY PLAN (only if devops)
    if "devops" in domains:
        steps.append({"step": step_num, "role": "cloud-architect", "action": "Write deployment plan", "parallel": False})

    return steps


def _decompose_internal(task: str, registry: dict, explicit_domains: list[str] | None = None) -> "DecomposeResult":
    t = task.lower()

    if explicit_domains:
        steps = _generate_steps_v2(explicit_domains, task)
        if _is_code_review_only(explicit_domains):
            pattern = PATTERN_FEEDBACK_LOOP
        elif len([d for d in explicit_domains if d not in ("architecture", "code-review", "devops")]) >= 3:
            pattern = PATTERN_PARALLEL
        else:
            pattern = PATTERN_PIPELINE
        dr = _domain_roles(t, explicit=explicit_domains)
        return DecomposeResult(pattern=pattern, steps=steps, domain_roles=dr)

    imp_verbs = set(re.findall(
        r"\b(build|create|implement|deploy|test|review|refactor|migrate|audit|"
        r"integrate|add|fix|debug|analyze|design|update|remove|configure|write|generate)\b", t
    ))
    domain_hits = _count_domains(t)
    pattern = _detect_pattern(t, domain_hits)
    dr = _domain_roles(t)
    primary_role = _suggest_role(t, imp_verbs, registry)
    steps = _generate_steps(t, pattern, dr, primary_role)
    return DecomposeResult(pattern=pattern, steps=steps, domain_roles=dr)


def decompose(task: str, custom_registry: str | None = None, domains: list[str] | None = None) -> "DecomposeResult":
    """Detect orchestration pattern and generate skeleton steps for a multi-agent task."""
    registry = load_registry(custom_registry)
    return _decompose_internal(task, registry, explicit_domains=domains)


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