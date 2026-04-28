"""
InvokerAI MCP server — stdio JSON-RPC 2.0.

Exposes route_task as a native Claude Code / Cursor / Copilot tool.

Start:
    python -m agent_invoker.mcp_server
    invoker-mcp
"""
from __future__ import annotations

import json
import sys
from typing import Any


TOOL_SCHEMA = {
    "name": "route_task",
    "description": (
        "Route a task to the optimal specialist agent. "
        "Returns routing (direct/orchestrate), role, confidence, and tools list. "
        "Call this before spawning any agent."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task text to route",
            },
            "custom_registry": {
                "type": "string",
                "description": "Optional path to a custom agents JSON file or directory",
            },
        },
        "required": ["task"],
    },
}

SERVER_INFO = {
    "name": "invokerai",
    "version": "0.1.0",
}


def _respond(id: Any, result: Any) -> None:
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "result": result})
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def _error(id: Any, code: int, message: str) -> None:
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def _handle(req: dict) -> None:
    id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})

    if method == "initialize":
        _respond(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    elif method == "notifications/initialized":
        pass  # no response for notifications

    elif method == "tools/list":
        _respond(id, {"tools": [TOOL_SCHEMA]})

    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})

        if name != "route_task":
            _error(id, -32601, f"Unknown tool: {name}")
            return

        task = args.get("task", "")
        if not task:
            _error(id, -32602, "task is required")
            return

        try:
            from agent_invoker.core import route
            result = route(
                task,
                custom_registry=args.get("custom_registry"),
                log=True,
            )
            output = {
                "routing": result.routing,
                "role": result.role,
                "confidence": result.confidence,
                "tools": result.tools,
                "source": result.source,
            }
            _respond(id, {
                "content": [{"type": "text", "text": json.dumps(output, indent=2)}]
            })
        except Exception as e:
            _error(id, -32603, str(e))

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