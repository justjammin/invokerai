from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_invoker.registry.loader import load_registry, Agent
from agent_invoker import classifier

LOG_PATH = Path.home() / ".invokerai" / "routing_log.jsonl"
_SESSION_LOG = Path.home() / ".claude" / "logs" / "invokerai-sessions.md"
_LEDGER_PATH = Path.home() / ".invokerai" / "ledger.json"
_LEDGER_TTL = 1800

_nli_cache: dict = {}


def _get_nli_model():
    if "model" not in _nli_cache:
        from transformers import pipeline
        _nli_cache["model"] = pipeline("zero-shot-classification", model="cross-encoder/nli-deberta-v3-base")
    return _nli_cache["model"]


_AGENTS_DIR = Path.home() / ".claude" / "agents"
_REPO_AGENTS_DIR = Path(__file__).parent.parent / "agents"

_CAVEMAN_PREFIX = (
    "# Style: caveman ultra\n"
    "Prose/chat: drop articles, filler, hedging. Fragments OK. "
    "Abbreviate (DB/auth/config/req/res/fn). X→Y for causality. "
    "Technical terms and identifiers exact. "
    "Code, commits, PR bodies: normal English. "
    "Break character for security warnings and irreversible ops.\n\n"
    "---\n\n"
)

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
    "agent-organizer": "orchestration",
    "context-manager": "orchestration",
    "workflow-orchestrator": "orchestration",
    "task-distributor": "orchestration",
    "multi-agent-coordinator": "orchestration",
    "accessibility-tester": "testing",
    "cli-developer": "backend",
    "mlops-engineer": "ml",
    "penetration-tester": "security",
    "qa-expert": "testing",
    "quant-analyst": "data",
    "blockchain-security-auditor": "security",
    "codebase-onboarding-engineer": "architecture",
    "compliance-auditor": "security",
    "incident-response-commander": "devops",
    "software-architect": "architecture",
    "sre": "devops",
    "code-simplifier": "code-review",
    "integration-engineer": "architecture",
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


def _normalize_role(role: str) -> str:
    """Strip plugin namespace from role (e.g. 'plugin:agent-name' → 'agent-name')."""
    return role.split(":")[-1]


def _load_persona(role: str, task: str = "") -> dict:
    normalized = _normalize_role(role)
    domain = _ROLE_DOMAIN.get(normalized)
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
            "system_prompt_fragment": _CAVEMAN_PREFIX + composed[:8000],
        }

    # Flat-file fallback (old naming convention)
    flat_file = _resolve_agent_file(f"{normalized}.md")
    if flat_file:
        return {
            "resource_uri": f"agent://{role}",
            "system_prompt_fragment": _CAVEMAN_PREFIX + _read_agent_body(flat_file)[:8000],
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


def append_session_log(task: str, role: str | None, confidence: int, routing: str, domains: list[str] | None, duration: str = "") -> None:
    try:
        date = time.strftime("%Y-%m-%d")
        short_task = (task[:77] + "...") if len(task) > 80 else task
        short_task = short_task.replace("\n", " ").strip()
        domains_str = ", ".join(domains) if domains else "—"
        entry = (
            f"\n### {date} — {short_task}\n"
            f"- **Role selected:** {role or 'unknown'}\n"
            f"- **Confidence:** {confidence}\n"
            f"- **Routing:** {routing}\n"
            f"- **Domains passed:** {domains_str}\n"
            f"- **Wall-clock:** {duration}\n"
        )
        _SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _SESSION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception:
        pass


def get_session(session_id: str) -> dict:
    now = time.time()
    try:
        data: dict = json.loads(_LEDGER_PATH.read_text()) if _LEDGER_PATH.exists() else {}
    except Exception:
        data = {}
    stale = [k for k, v in data.items() if now - v.get("last_seen", 0) > _LEDGER_TTL]
    for k in stale:
        del data[k]
    if session_id not in data:
        data[session_id] = {"active_role": None, "prior_routes": [], "last_seen": now}
    data[session_id]["last_seen"] = now
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_PATH.write_text(json.dumps(data))
    except Exception:
        pass
    return data[session_id]


def update_session(session_id: str, role: str | None, routing: str) -> None:
    s = get_session(session_id)
    s["active_role"] = role
    s["prior_routes"].append({"role": role, "routing": routing, "ts": int(time.time())})
    if len(s["prior_routes"]) > 20:
        s["prior_routes"] = s["prior_routes"][-20:]
    try:
        data: dict = json.loads(_LEDGER_PATH.read_text()) if _LEDGER_PATH.exists() else {}
    except Exception:
        data = {}
    data[session_id] = s
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_PATH.write_text(json.dumps(data))
    except Exception:
        pass


def _complexity_score(task: str) -> str:
    t = task.lower()
    if re.search(r'\b(just|quick|simple|minor|fix|typo|rename)\b', t):
        return "low"
    if re.search(r'\b(redesign|migrate|refactor|comprehensive|platform|entire|system|end.to.end)\b', t):
        return "high"
    words = len(task.split())
    if words > 80:
        return "high"
    if words > 30:
        return "medium"
    return "low"


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

    routing_result = RoutingResult(
        routing=routing,
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
    if log and session_id:
        update_session(session_id, routing_result.role, routing_result.routing)

    return routing_result


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


def _count_domains(t: str) -> int:
    patterns = {
        "frontend": r"\b(css|html|react|vue|angular|svelte|jsx|tsx|dom|browser|component)\b",
        "backend": r"\b(api|endpoint|service|server|controller|middleware|route|handler|rest|graphql)\b",
        "database": r"\b(sql|query|schema|migration|index|table|database|\bdb\b|orm|postgres|mysql|mongo)\b",
        "devops": r"\b(deploy|docker|kubernetes|k8s|\bci\b|\bcd\b|pipeline|infra|cloud|aws|gcp|terraform)\b",
        "security": r"\b(auth|oauth|jwt|permission|role|encrypt|credential|secret)\b",
        "ml": r"\b(model|training|inference|embedding|\bllm\b|fine.?tun|rag|vector|neural)\b",
    }
    regex_count = sum(1 for p in patterns.values() if re.search(p, t))

    if regex_count <= 1:
        try:
            nli = _get_nli_model()
            _nli_labels = ["frontend", "backend", "database", "devops", "security", "ml"]
            result = nli(t, candidate_labels=_nli_labels, multi_label=True)
            nli_count = sum(1 for score in result["scores"] if score > 0.5)
            return max(regex_count, nli_count)
        except ImportError:
            pass

    return regex_count


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
    "code-simplifier": "code polish",
    "integration-engineer": "integration layer",
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


def _decompose_internal(task: str, registry: dict, explicit_domains: list[str] | None = None, complexity: str = "medium") -> "DecomposeResult":
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
        return DecomposeResult(pattern=pattern, steps=steps, domain_roles=dr)

    imp_verbs = set(re.findall(
        r"\b(build|create|implement|deploy|test|review|refactor|migrate|audit|"
        r"integrate|add|fix|debug|analyze|design|update|remove|configure|write|generate)\b", t
    ))
    domain_hits = _count_domains(t)
    pattern = _detect_pattern(t, domain_hits)
    dr = _domain_roles(t)
    primary_role = _suggest_role(t, imp_verbs, registry)
    steps = _generate_steps(t, pattern, dr, primary_role, complexity=complexity)
    return DecomposeResult(pattern=pattern, steps=steps, domain_roles=dr)


def decompose(task: str, custom_registry: str | None = None, domains: list[str] | None = None, complexity: str | None = None) -> "DecomposeResult":
    """Detect orchestration pattern and generate skeleton steps for a multi-agent task."""
    registry = load_registry(custom_registry)
    if complexity is None:
        complexity = _complexity_score(task)
    return _decompose_internal(task, registry, explicit_domains=domains, complexity=complexity)


_CATEGORY_PRIORITY = {
    "security": 0,
    "testing": 1,
    "ml": 2,
    "debugging": 3,
    "code-review": 4,
    "coding": 5,
    "architecture": 6,
    "data": 7,
    "documentation": 8,
    "research": 9,
    "orchestration": 10,
    "implementation": 11,
}


def _collect_matches(task: str, registry: dict[str, Agent]) -> list[dict]:
    t = task.lower()
    matches = []
    for agent in registry.values():
        if agent.orchestrate:
            continue
        for trigger in agent.triggers:
            if re.search(r"\b" + re.escape(trigger) + r"\b", t):
                priority = _CATEGORY_PRIORITY.get(agent.category, 99)
                matches.append({
                    "role": agent.id,
                    "category": agent.category,
                    "trigger": trigger,
                    "priority": priority,
                })
                break
    matches.sort(key=lambda m: m["priority"])
    return matches


def _suggest_role(t: str, imp_verbs: set[str], registry: dict[str, Agent]) -> str:
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

    if re.search(r"\b(slo|error.?budget|sli|sre|chaos.?engineer|reliability.?engineer|toil)\b", t):
        return "sre"

    if re.search(r"\b(incident|post.?mortem|runbook|on.?call|sev1|sev2|sev3|pagerduty|opsgenie)\b", t):
        return "incident-response-commander"

    if re.search(r"\b(soc.?2|hipaa|pci.?dss|iso.?27001|compliance.?audit|audit.?readiness)\b", t):
        return "compliance-auditor"

    if re.search(r"\b(smart.?contract|solidity|reentrancy|defi|evm|web3|slither)\b", t):
        return "blockchain-security-auditor"

    if re.search(r"\b(onboard|codebase.?tour|orient.*code)\b", t):
        return "codebase-onboarding-engineer"

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


def patch_session_log_outcome(date: str, task_prefix: str, corrections: int, accepted: bool) -> dict:
    """Append correction/acceptance metrics to an existing session log entry.

    Matches the first entry whose header starts with ``### {date} — {task_prefix}``
    and inserts two outcome bullet points immediately after it.  Returns
    ``{"ok": True}`` on success or ``{"ok": False, "error": "..."}`` on failure.
    """
    try:
        if not _SESSION_LOG.exists():
            return {"ok": False, "error": "entry not found"}
        text = _SESSION_LOG.read_text(encoding="utf-8")
        header_prefix = f"### {date} — {task_prefix}"
        lines = text.split("\n")
        header_idx = next(
            (i for i, ln in enumerate(lines) if ln.startswith(header_prefix)),
            -1,
        )
        if header_idx == -1:
            return {"ok": False, "error": "entry not found"}
        insert_idx = len(lines)
        for j in range(header_idx + 1, len(lines)):
            if lines[j].startswith("### ") or lines[j].strip() == "":
                insert_idx = j
                break
        outcome_lines = [
            f"- **Correction cycles:** {corrections}",
            f"- **First-pass accepted:** {'yes' if accepted else 'no'}",
        ]
        lines[insert_idx:insert_idx] = outcome_lines
        _SESSION_LOG.write_text("\n".join(lines), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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