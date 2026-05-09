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

import json
import time
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.utilities.types import Image  # noqa: F401 — keep for future use

_SPAWN_TOKEN = Path.home() / ".invokerai" / "spawn_token"
_AGENTS_DIR = Path.home() / ".claude" / "agents"
_SESSION_LOG = Path.home() / ".claude" / "logs" / "invokerai-sessions.md"

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

# ── session ledger ────────────────────────────────────────────────────────────

_LEDGER: dict[str, dict] = {}
_LEDGER_TTL = 1800


def _get_session(session_id: str) -> dict:
    now = time.time()
    for k in [k for k, v in _LEDGER.items() if now - v["last_seen"] > _LEDGER_TTL]:
        del _LEDGER[k]
    if session_id not in _LEDGER:
        _LEDGER[session_id] = {"active_role": None, "prior_routes": [], "last_seen": now}
    _LEDGER[session_id]["last_seen"] = now
    return _LEDGER[session_id]


def _update_session(session_id: str, role: str | None, routing: str) -> None:
    s = _get_session(session_id)
    s["active_role"] = role
    s["prior_routes"].append({"role": role, "routing": routing, "ts": int(time.time())})
    if len(s["prior_routes"]) > 20:
        s["prior_routes"] = s["prior_routes"][-20:]


def _write_spawn_token(count: int) -> None:
    _SPAWN_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    _SPAWN_TOKEN.write_text(f"{count}:{int(time.time())}")


def _append_session_log(task: str, role: str | None, confidence: int, routing: str, domains: list[str] | None, duration: str = "") -> None:
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
        "Returns role, persona, tools, spawn_authorized, and steps for orchestrate routing."
    )
)
def spawn_specialist(
    task: str,
    domains: list[str] | None = None,
    custom_registry: str | None = None,
    session_id: str | None = None,
) -> dict:
    if not task or not task.strip():
        raise ValueError("task is required")
    start = time.time()
    from agent_invoker.core import route
    sid = session_id or "default"
    result = route(task, custom_registry=custom_registry, log=True, domains=domains)
    _update_session(sid, result.role, result.routing)
    _write_spawn_token(result.spawn_count)
    out = {
        "routing": "orchestrate",
        "role": result.role,
        "confidence": result.confidence,
        "tools": result.tools,
        "source": result.source,
        "session_id": sid,
        "spawn_authorized": True,
        "spawn_count": result.spawn_count,
    }
    if result.persona:
        out["persona"] = result.persona
    out["pattern"] = result.pattern
    out["steps"] = result.steps
    elapsed = time.time() - start
    _append_session_log(task, result.role, result.confidence, result.routing, domains, f"{elapsed:.1f}s")
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
    from agent_invoker.core import route
    sid = session_id or "default"
    result = route(task, custom_registry=custom_registry, log=True, domains=domains)
    _update_session(sid, result.role, result.routing)
    out = {
        "routing": "orchestrate",
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
    from agent_invoker.core import decompose
    result = decompose(task, custom_registry=custom_registry, domains=domains)
    return {
        "pattern": result.pattern,
        "steps": result.steps,
        "domain_roles": [{"domain": d, "role": r} for d, r in result.domain_roles],
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
        "Match by date + task prefix. Returns {ok: bool, error?: str}."
    )
)
def log_outcome(
    date: str,
    task_prefix: str,
    corrections: int,
    accepted: bool,
) -> dict:
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
