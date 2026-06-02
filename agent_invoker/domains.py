from __future__ import annotations

import re
from pathlib import Path

from agent_invoker.registry.loader import Agent

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

_nli_cache: dict = {}


def _get_nli_model():
    if "model" not in _nli_cache:
        from transformers import pipeline
        _nli_cache["model"] = pipeline("zero-shot-classification", model="cross-encoder/nli-deberta-v3-base")
    return _nli_cache["model"]


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
