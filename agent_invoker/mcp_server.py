"""
InvokerAI MCP server — FastMCP 3.x.

Tools:
    spawn_specialist — route + write spawn token (primary surface)
    route_task       — pure classifier, returns routing + persona bundle
    confirm_route    — subagent self-correction on first turn
    decompose_task   — detect MAS pattern + skeleton steps
    list_agents      — discover available specialists

Resources:  agent://{role}  — full agent profile
Prompts:    route           — /route <task> shortcut

Start:
    python -m agent_invoker.mcp_server
    invoker-mcp
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.utilities.types import Image  # noqa: F401 — keep for future use

from agent_invoker.gc_client import gc_client, _sweep_tmp_personas, GcError

INVOKERAI_GASCITY = os.environ.get("INVOKERAI_GASCITY", "off")

# Sweep stale persona temp files at server startup.
_sweep_tmp_personas()

_gc_auto_warned: bool = False

MAX_TASK_LEN = 4096


def _gc_effective() -> "GcClient | None":  # type: ignore[name-defined]  # noqa: F821
    """Return GcClient only when gc is available AND INVOKERAI_GASCITY enables it.

    INVOKERAI_GASCITY=off  → always None (disabled)
    INVOKERAI_GASCITY=on   → use gc if binary found
    INVOKERAI_GASCITY=auto → use gc if found; log a one-time warning on first detection
    """
    global _gc_auto_warned
    if INVOKERAI_GASCITY == "off":
        return None
    client = gc_client()
    if client is None:
        return None
    if INVOKERAI_GASCITY == "auto" and not _gc_auto_warned:
        _gc_auto_warned = True
        _logger.warning(
            "Gas City detected (INVOKERAI_GASCITY=auto). "
            "Crew routing will use gc supervisor. "
            "Set INVOKERAI_GASCITY=off to disable."
        )
    return client

_SPAWN_TOKEN = Path.home() / ".invokerai" / "spawn_token"
_AGENTS_DIR = Path.home() / ".claude" / "agents"
_logger = logging.getLogger("invokerai")

_ALLOWED_REGISTRY_ROOTS = [
    Path.home() / ".invokerai",
    Path.cwd(),
]


def _validate_registry_path(p: str | None) -> None:
    """Reject custom_registry paths outside allowed roots (zero-trust MCP)."""
    if p is None:
        return
    try:
        resolved = Path(p).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("custom_registry path could not be resolved") from exc
    if not any(resolved.is_relative_to(root.resolve()) for root in _ALLOWED_REGISTRY_ROOTS):
        raise ValueError("custom_registry path not in allowed roots")

_BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ⚡  I N V O K E R A I   —   Agent Router                  ║
║                                                              ║
║   spawn_specialist → route → persona → steps → execute      ║
║                                                              ║
║   Domains: architecture · backend · frontend · database      ║
║            devops · security · ml · testing · mobile        ║
║            documentation · data · code-review               ║
║                                                              ║
║   PRIMARY SURFACE: mcp__invokerai__spawn_specialist()        ║
║   Never call Agent directly. Never code — only orchestrate.  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

mcp = FastMCP("invokerai", version="0.2.0", instructions=_BANNER.strip())

from agent_invoker.core import append_session_log, get_session, update_session, patch_session_log_outcome, record_accepted_routing, read_handoff, write_handoff, get_project_memory, update_project_memory, _is_valid_role


def _write_spawn_token(count: int) -> None:
    _SPAWN_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    _SPAWN_TOKEN.write_text(f"{count}:{int(time.time())}")


# ── agent resource helpers ────────────────────────────────────────────────────

def _read_agent_file(role: str) -> str:
    agent_file = _AGENTS_DIR / f"{role}.md"
    try:
        if not agent_file.resolve().is_relative_to(_AGENTS_DIR.resolve()):
            return "Access denied"
    except ValueError:
        return "Access denied"
    if not agent_file.exists():
        return f"Agent profile not found: {role}"
    return agent_file.read_text(encoding="utf-8")


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "PRIMARY SURFACE. Route task → write spawn token → return execution bundle. "
        "Always call this instead of the Agent tool directly. "
        "Pass domains[] from your analysis to get accurate MAS step generation. "
        "Canonical domains: architecture|backend|frontend|database|devops|security|"
        "ml|testing|documentation|mobile|data|code-review. "
        "Returns role, persona, tools, spawn_authorized, and steps for orchestrate routing. "
        "If response contains `confidence_warning`, surface it to the user before proceeding. "
        "If response contains `clarification_needed: true`, do NOT spawn — show `candidates` to user and ask them to confirm the correct role, then call again with corrected domains. "
        "Pass dry_run=true to preview the routing decision (role, persona, steps) without committing the spawn."
    )
)
def spawn_specialist(
    task: str,
    domains: list[str] | None = None,
    custom_registry: str | None = None,
    session_id: str | None = None,
    complexity: str | None = None,
    dry_run: Annotated[bool, "Preview routing without writing spawn token or updating session"] = False,
    project_id: Annotated[str | None, "Project identifier for cross-session memory (e.g. repo name)"] = None,
) -> dict:
    if not task or not task.strip():
        raise ValueError("task is required")
    task = task[:MAX_TASK_LEN]
    _validate_registry_path(custom_registry)
    start = time.time()
    from agent_invoker.core import route
    sid = session_id or "default"
    result = route(task, custom_registry=custom_registry, log=not dry_run, domains=domains, complexity=complexity, session_id=sid)

    HIGH_CONF = 70
    MED_CONF = 50

    if result.confidence >= MED_CONF and not dry_run:
        _write_spawn_token(result.spawn_count)

    if not dry_run:
        update_session(sid, result.role, result.routing)

    out = {
        "routing": result.routing,
        "role": result.role,
        "confidence": result.confidence,
        "tools": result.tools,
        "source": result.source,
        "session_id": sid,
        "spawn_authorized": result.confidence >= MED_CONF and not dry_run,
        "spawn_count": result.spawn_count,
    }
    if result.persona:
        out["persona"] = result.persona
    if result.persona_file:
        out["persona_file"] = result.persona_file
    out["pattern"] = result.pattern
    out["steps"] = result.steps
    if result.reasoning:
        out["reasoning"] = result.reasoning
    prior = read_handoff(sid)
    if prior:
        out["prior_handoff"] = prior

    if MED_CONF <= result.confidence < HIGH_CONF:
        out["confidence_warning"] = (
            f"Routed to {result.role} at {result.confidence}% confidence. "
            "If wrong, call spawn_specialist again with corrected domains."
        )
        if result.candidates:
            out["runner_up"] = result.candidates[0]
    elif result.confidence < MED_CONF:
        out["clarification_needed"] = True
        out["candidates"] = result.candidates

    if dry_run:
        out["dry_run"] = True
    else:
        elapsed = time.time() - start
        append_session_log(task, result.role, result.confidence, result.routing, domains, f"{elapsed:.1f}s")
        if project_id and result.role:
            update_project_memory(project_id, result.role, domains)
            mem = get_project_memory(project_id)
            if mem:
                out["project_context"] = {
                    "project_id": project_id,
                    "frequent_roles": sorted(mem.get("role_counts", {}).items(), key=lambda x: -x[1])[:3],
                    "last_domains": mem.get("last_domains", []),
                }
    return out


@mcp.tool(
    description=(
        "Classify a task and return the optimal specialist agent with persona bundle. "
        "Pure read-only lookup — does not gate Agent spawning. "
        "Use spawn_specialist to route AND gate in one call."
    )
)
def route_task(
    task: str,
    domains: list[str] | None = None,
    custom_registry: str | None = None,
    session_id: str | None = None,
) -> dict:
    if not task or not task.strip():
        raise ValueError("task is required")
    task = task[:MAX_TASK_LEN]
    _validate_registry_path(custom_registry)
    from agent_invoker.core import route
    sid = session_id or "default"
    result = route(task, custom_registry=custom_registry, log=True, domains=domains, session_id=sid)
    update_session(sid, result.role, result.routing)
    out = {
        "routing": result.routing,
        "role": result.role,
        "confidence": result.confidence,
        "tools": result.tools,
        "source": result.source,
        "session_id": sid,
    }
    if result.persona:
        out["persona"] = result.persona
    out["pattern"] = result.pattern
    out["steps"] = result.steps
    if result.reasoning:
        out["reasoning"] = result.reasoning
    return out


@mcp.tool(
    description=(
        "Subagent self-correction. Call on your first turn as a subagent to verify "
        "you are the correct specialist. If routing says otherwise, adopt the corrected role."
    )
)
def confirm_route(
    task: str,
    expected_role: str,
    session_id: str | None = None,
) -> dict:
    if not task or not task.strip():
        raise ValueError("task is required")
    if not expected_role or not expected_role.strip():
        raise ValueError("expected_role is required")
    task = task[:MAX_TASK_LEN]
    from agent_invoker.core import route
    sid = session_id or "default"
    result = route(task, log=False)
    ok = result.role == expected_role or result.confidence < 50
    out = {
        "ok": ok,
        "expected_role": expected_role,
        "confirmed_role": result.role if not ok else expected_role,
        "confidence": result.confidence,
        "session_id": sid,
    }
    if not ok and result.persona:
        out["corrected_persona"] = result.persona
    if ok and result.role == expected_role:
        session = get_session(sid)
        prior = session.get("prior_routes", [])
        routing = prior[-1]["routing"] if prior else "solo"
        record_accepted_routing(task, expected_role, routing)
    return out


@mcp.tool(
    description=(
        "Detect the MAS orchestration pattern for a multi-agent task and return skeleton "
        "steps with role assignments. Accepts explicit domains[] for precise step generation."
    )
)
def decompose_task(
    task: str,
    domains: list[str] | None = None,
    custom_registry: str | None = None,
) -> dict:
    task = (task or "")[:MAX_TASK_LEN]
    _validate_registry_path(custom_registry)
    from agent_invoker.core import decompose
    result = decompose(task, custom_registry=custom_registry, domains=domains)
    return {
        "pattern": result.pattern,
        "steps": result.steps,
        "domain_roles": [{"domain": d, "role": r} for d, r in result.domain_roles],
    }


_STATUS_MAP = {
    "open": "pending",
    "in_progress": "running",
    "claimed": "running",
    "closed": "done",
    "discarded": "failed",
}


@mcp.tool(
    description=(
        "Get status of a running Gas City crew. "
        "Returns step-level status for each agent in the crew."
    )
)
def get_crew_status(crew_root_bead_id: str) -> dict:
    crew_root_bead_id = (crew_root_bead_id or "")[:MAX_TASK_LEN]
    client = _gc_effective()
    if client is None:
        return {"error": "Gas City not available", "crew_root_bead_id": crew_root_bead_id}

    try:
        root_bead = client.run(["bd", "show", crew_root_bead_id, "--json"])
        root_status = _STATUS_MAP.get(root_bead.get("status", ""), root_bead.get("status", "unknown"))
    except GcError:
        return {"error": "Gas City not available", "crew_root_bead_id": crew_root_bead_id}

    try:
        step_beads_result = client.run([
            "bd", "list",
            "--parent", crew_root_bead_id,
            "--json",
            "--limit", "50",
        ])
        if isinstance(step_beads_result, list):
            step_beads = step_beads_result
        else:
            step_beads = step_beads_result.get("items", [])
    except GcError:
        step_beads = []

    steps = []
    for i, bead in enumerate(step_beads, start=1):
        raw_status = bead.get("status", "")
        steps.append({
            "step": i,
            "role": bead.get("title") or "unknown",
            "status": _STATUS_MAP.get(raw_status, raw_status or "unknown"),
            "started_at": bead.get("claimed_at"),
            "completed_at": bead.get("closed_at"),
        })

    return {
        "crew_id": crew_root_bead_id,
        "crew_status": root_status,
        "steps": steps,
    }


@mcp.tool(
    description="List all available specialist agents with their categories and descriptions."
)
def list_agents(category: str | None = None) -> dict:
    from agent_invoker.registry.loader import load_registry
    try:
        registry = load_registry()
    except Exception:
        registry = {}
    cat = (category or "").lower()
    agents = [
        {"id": a.id, "category": a.category, "description": a.description, "orchestrate": a.orchestrate}
        for a in registry.values()
        if not cat or a.category.lower() == cat
    ]
    agents.sort(key=lambda a: (a["category"], a["id"]))
    return {"agents": agents}


@mcp.tool(
    description=(
        "Append outcome metrics (correction cycles + first-pass acceptance) to an "
        "existing session log entry in ~/.claude/logs/invokerai-sessions.md. "
        "Match by date + task prefix. "
        "When accepted=True and corrections=0, pass task/role/routing to feed the routing feedback loop — "
        "confirmed routings auto-train the classifier at every 50 examples. "
        "Returns {ok: bool, error?: str}."
    )
)
def log_outcome(
    date: str,
    task_prefix: str,
    corrections: int,
    accepted: bool,
    task: Annotated[str | None, "Full task text for feedback loop"] = None,
    role: Annotated[str | None, "Role that was used for feedback loop"] = None,
    routing: Annotated[str | None, "Routing type (solo/crew) for feedback loop"] = None,
) -> dict:
    result = patch_session_log_outcome(date, task_prefix, corrections, accepted)
    if accepted and corrections == 0 and task and role and routing:
        if not _is_valid_role(role):
            _logger.warning("log_outcome: rejected unknown role (training-poisoning guard)")
            return result
        record_accepted_routing(task, role, routing)
    return result


@mcp.tool(
    description=(
        "Read the handoff artifact for a session — context left by previous agents "
        "(steps completed, decisions made, open questions, files touched). "
        "Call at the start of a crew step to pick up where the last agent left off."
    )
)
def get_handoff(session_id: str) -> dict:
    return read_handoff(session_id) or {"session_id": session_id, "steps_completed": [], "decisions": [], "open_questions": [], "files_touched": []}


@mcp.tool(
    description=(
        "Write to the handoff artifact after completing a crew step. "
        "Pass decisions made, open questions for the next agent, and files touched. "
        "Next agent in the crew will receive this context automatically via spawn_specialist."
    )
)
def put_handoff(
    session_id: str,
    role: str,
    task: str,
    decisions: list[str] | None = None,
    open_questions: list[str] | None = None,
    files_touched: list[str] | None = None,
) -> dict:
    return write_handoff(session_id, role, task, decisions, open_questions, files_touched)


@mcp.tool(
    description=(
        "Retrieve cross-session project memory — which specialists have been used most "
        "in this project, and what domains were last active. "
        "Useful for giving agents project-specific context before they start."
    )
)
def get_project_context(project_id: str) -> dict:
    mem = get_project_memory(project_id)
    if not mem:
        return {"project_id": project_id, "frequent_roles": [], "last_domains": []}
    return {
        "project_id": project_id,
        "frequent_roles": sorted(mem.get("role_counts", {}).items(), key=lambda x: -x[1])[:5],
        "last_domains": mem.get("last_domains", []),
        "last_updated": mem.get("last_updated"),
    }


# ── resources ─────────────────────────────────────────────────────────────────

@mcp.resource("agent://{role}")
def agent_profile(role: str) -> str:
    return _read_agent_file(role)


# ── prompts ───────────────────────────────────────────────────────────────────

@mcp.prompt()
def route(task: str) -> str:
    return f"Call mcp__invokerai__spawn_specialist with task: {task}"


# ── compat exports (used by tests + external tooling) ─────────────────────────

def _agent_resources() -> list[dict]:
    if not _AGENTS_DIR.exists():
        return []
    return [
        {"uri": f"agent://{f.stem}", "name": f.stem, "mimeType": "text/markdown"}
        for f in sorted(_AGENTS_DIR.glob("*.md"))
    ]


def _read_agent_resource(uri: str) -> str:
    role = uri.removeprefix("agent://")
    return _read_agent_file(role)


SERVER_INFO = {"name": "invokerai", "version": "0.2.0"}


# ── entry point ───────────────────────────────────────────────────────────────

def serve() -> None:
    mcp.run()


if __name__ == "__main__":
    serve()
