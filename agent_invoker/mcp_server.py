"""
InvokerAI MCP server — stdio JSON-RPC 2.0.

Tools:
    route_task       — pure classifier, returns routing + persona bundle
    spawn_specialist — route + write spawn token (primary surface)
    confirm_route    — subagent self-correction on first turn
    list_agents      — discover available specialists

Resources:  agent://{role}  — full agent profile
Prompts:    route           — /route <task> shortcut

Start:
    python -m agent_invoker.mcp_server
    invoker-mcp
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_SPAWN_TOKEN = Path.home() / ".invokerai" / "spawn_token"
_AGENTS_DIR = Path.home() / ".claude" / "agents"

# ── session ledger ────────────────────────────────────────────────────────────

_LEDGER: dict[str, dict] = {}
_LEDGER_TTL = 1800  # 30 min


def _get_session(session_id: str) -> dict:
    now = time.time()
    stale = [k for k, v in _LEDGER.items() if now - v["last_seen"] > _LEDGER_TTL]
    for k in stale:
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


# ── agent resource helpers ────────────────────────────────────────────────────

def _agent_resources() -> list[dict]:
    if not _AGENTS_DIR.exists():
        return []
    return [
        {
            "uri": f"agent://{f.stem}",
            "name": f.stem,
            "mimeType": "text/markdown",
        }
        for f in sorted(_AGENTS_DIR.glob("*.md"))
    ]


def _read_agent_resource(uri: str) -> str:
    role = uri.removeprefix("agent://")
    agent_file = _AGENTS_DIR / f"{role}.md"
    if not agent_file.exists():
        return f"Agent profile not found: {role}"
    return agent_file.read_text()


# ── tool schemas ──────────────────────────────────────────────────────────────

_ROUTE_TASK_SCHEMA = {
    "name": "route_task",
    "description": (
        "Classify a task and return the optimal specialist agent with persona bundle. "
        "Pure read-only lookup — does not gate Agent spawning. "
        "Use spawn_specialist to route AND gate in one call."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Task text to route"},
            "custom_registry": {"type": "string", "description": "Optional path to custom agents JSON"},
            "session_id": {"type": "string", "description": "Session ID for multi-turn coherence (optional)"},
        },
        "required": ["task"],
    },
    "annotations": {"readOnlyHint": True, "idempotentHint": True},
}

_SPAWN_SPECIALIST_SCHEMA = {
    "name": "spawn_specialist",
    "description": (
        "PRIMARY SURFACE. Route task → write spawn token → return execution bundle. "
        "Always call this instead of the Agent tool directly. "
        "Returns role, system_prompt_fragment, tools, and spawn authorization."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Task text to route and authorize"},
            "custom_registry": {"type": "string", "description": "Optional path to custom agents JSON"},
            "session_id": {"type": "string", "description": "Session ID for multi-turn coherence (optional)"},
        },
        "required": ["task"],
    },
}

_CONFIRM_ROUTE_SCHEMA = {
    "name": "confirm_route",
    "description": (
        "Subagent self-correction. Call on your first turn as a subagent to verify you are the correct specialist. "
        "If routing says otherwise, adopt the corrected role."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The task you were spawned to handle"},
            "expected_role": {"type": "string", "description": "The role you were spawned as"},
            "session_id": {"type": "string", "description": "Session ID (optional)"},
        },
        "required": ["task", "expected_role"],
    },
    "annotations": {"readOnlyHint": True},
}

_LIST_AGENTS_SCHEMA = {
    "name": "list_agents",
    "description": "List all available specialist agents with their categories and descriptions.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Filter by category (optional)"},
        },
    },
    "annotations": {"readOnlyHint": True, "idempotentHint": True},
}

ALL_TOOLS = [_ROUTE_TASK_SCHEMA, _SPAWN_SPECIALIST_SCHEMA, _CONFIRM_ROUTE_SCHEMA, _LIST_AGENTS_SCHEMA]

SERVER_INFO = {"name": "invokerai", "version": "0.2.0"}

# ── response helpers ──────────────────────────────────────────────────────────


def _respond(id: Any, result: Any) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id, "result": result}) + "\n")
    sys.stdout.flush()


def _error(id: Any, code: int, message: str) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


def _route_output(result: Any, session_id: str, authorized: bool = False) -> dict:
    out: dict = {
        "routing": result.routing,
        "role": result.role,
        "confidence": result.confidence,
        "tools": result.tools,
        "source": result.source,
        "session_id": session_id,
    }
    if result.persona:
        out["persona"] = result.persona
    if authorized:
        out["spawn_authorized"] = True
    return out


# ── tool handlers ─────────────────────────────────────────────────────────────


def _handle_route_task(args: dict, id: Any) -> None:
    task = args.get("task", "").strip()
    if not task:
        _error(id, -32602, "task is required")
        return
    session_id = args.get("session_id") or "default"
    try:
        from agent_invoker.core import route
        result = route(task, custom_registry=args.get("custom_registry"), log=True)
        _update_session(session_id, result.role, result.routing)
        _respond(id, {"content": [{"type": "text", "text": json.dumps(_route_output(result, session_id), indent=2)}]})
    except Exception as e:
        _error(id, -32603, str(e))


def _handle_spawn_specialist(args: dict, id: Any) -> None:
    task = args.get("task", "").strip()
    if not task:
        _error(id, -32602, "task is required")
        return
    session_id = args.get("session_id") or "default"
    try:
        from agent_invoker.core import route
        result = route(task, custom_registry=args.get("custom_registry"), log=True)
        _update_session(session_id, result.role, result.routing)
        # Write spawn token — PreToolUse[Agent] hook consumes this to allow the next Agent call
        _SPAWN_TOKEN.parent.mkdir(parents=True, exist_ok=True)
        _SPAWN_TOKEN.write_text(str(int(time.time())))
        _respond(id, {"content": [{"type": "text", "text": json.dumps(_route_output(result, session_id, authorized=True), indent=2)}]})
    except Exception as e:
        _error(id, -32603, str(e))


def _handle_confirm_route(args: dict, id: Any) -> None:
    task = args.get("task", "").strip()
    expected = args.get("expected_role", "").strip()
    if not task or not expected:
        _error(id, -32602, "task and expected_role are required")
        return
    session_id = args.get("session_id") or "default"
    try:
        from agent_invoker.core import route
        result = route(task, log=False)
        ok = result.role == expected or result.confidence < 50
        out: dict = {
            "ok": ok,
            "expected_role": expected,
            "confirmed_role": result.role if not ok else expected,
            "confidence": result.confidence,
            "session_id": session_id,
        }
        if not ok and result.persona:
            out["corrected_persona"] = result.persona
        _respond(id, {"content": [{"type": "text", "text": json.dumps(out, indent=2)}]})
    except Exception as e:
        _error(id, -32603, str(e))


def _handle_list_agents(args: dict, id: Any) -> None:
    try:
        from agent_invoker.registry.loader import load_registry
        registry = load_registry()
        category_filter = (args.get("category") or "").lower()
        agents = [
            {
                "id": a.id,
                "category": a.category,
                "description": a.description,
                "orchestrate": a.orchestrate,
            }
            for a in registry.values()
            if not category_filter or a.category.lower() == category_filter
        ]
        agents.sort(key=lambda a: (a["category"], a["id"]))
        _respond(id, {"content": [{"type": "text", "text": json.dumps({"agents": agents}, indent=2)}]})
    except Exception as e:
        _error(id, -32603, str(e))


# ── request dispatcher ────────────────────────────────────────────────────────


def _handle(req: dict) -> None:
    id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})

    if method == "initialize":
        _respond(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": SERVER_INFO,
        })

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        _respond(id, {"tools": ALL_TOOLS})

    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "route_task":
            _handle_route_task(args, id)
        elif name == "spawn_specialist":
            _handle_spawn_specialist(args, id)
        elif name == "confirm_route":
            _handle_confirm_route(args, id)
        elif name == "list_agents":
            _handle_list_agents(args, id)
        else:
            _error(id, -32601, f"Unknown tool: {name}")

    elif method == "resources/list":
        _respond(id, {"resources": _agent_resources()})

    elif method == "resources/read":
        uri = params.get("uri", "")
        if not uri.startswith("agent://"):
            _error(id, -32602, f"Unknown resource URI: {uri}")
            return
        _respond(id, {
            "contents": [{"uri": uri, "mimeType": "text/markdown", "text": _read_agent_resource(uri)}]
        })

    elif method == "prompts/list":
        _respond(id, {"prompts": [{
            "name": "route",
            "description": "Route a task to the optimal specialist agent",
            "arguments": [{"name": "task", "description": "Task to route", "required": True}],
        }]})

    elif method == "prompts/get":
        name = params.get("name")
        if name != "route":
            _error(id, -32601, f"Unknown prompt: {name}")
            return
        task = (params.get("arguments") or {}).get("task", "")
        _respond(id, {
            "description": "Route task to optimal specialist",
            "messages": [{
                "role": "user",
                "content": {"type": "text", "text": f"Call mcp__invokerai__spawn_specialist with task: {task}"},
            }],
        })

    elif method == "ping":
        _respond(id, {})

    else:
        if id is not None:
            _error(id, -32601, f"Method not found: {method}")


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _error(None, -32700, "Parse error")
            continue
        _handle(req)


if __name__ == "__main__":
    serve()
