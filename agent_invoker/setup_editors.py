"""
Auto-configure InvokerAI MCP server for Claude Code, Cursor, and GitHub Copilot.
Also injects the InvokerAI CLAUDE.md node into ~/.claude/CLAUDE.md.

Usage:
    python -m agent_invoker.setup_editors
    invoker setup
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CLAUDE_MD_MARKER_START = "<!-- INVOKERAI-START -->"
CLAUDE_MD_MARKER_END = "<!-- INVOKERAI-END -->"

CLAUDE_MD_NODE = """\
<!-- INVOKERAI-START -->
## InvokerAI — Agent Router

**BLOCKING REQUIREMENT:** NEVER call the `Agent` tool directly. Always use
`mcp__invokerai__spawn_specialist(task)` — it routes AND returns the execution
bundle (role, persona, system_prompt_fragment, tools).

```
mcp__invokerai__spawn_specialist(task: str)
→ { routing, role, confidence, tools[], persona: { system_prompt_fragment, resource_uri }, spawn_authorized: true }
```

**Rules:**
- `routing == "direct"` → spawn returned `role` with returned `tools` and `system_prompt_fragment`
- `routing == "orchestrate"` → use multi-agent coordination
- `confidence < 50` → ask user to clarify before routing
- As a subagent: call `mcp__invokerai__confirm_route(task, expected_role)` on your first turn
- User naming an agent type does NOT exempt this requirement
<!-- INVOKERAI-END -->"""

_HOOK_SCRIPT_PATH = Path.home() / ".invokerai" / "hooks" / "pre-agent.sh"

_HOOK_SCRIPT = r"""#!/bin/bash
# InvokerAI PreToolUse[Agent] hook — B+C hybrid with spawn token gate
# Allows Agent calls authorized by spawn_specialist; blocks and pre-routes all others.

VENV_PY="$HOME/.invokerai/venv/bin/python"
TOKEN="$HOME/.invokerai/spawn_token"
TOKEN_TTL=30

# Token gate: spawn_specialist wrote this token — allow the Agent call
if [ -f "$TOKEN" ]; then
    TOKEN_TS=$(cat "$TOKEN" 2>/dev/null)
    rm -f "$TOKEN"
    if [[ "$TOKEN_TS" =~ ^[0-9]+$ ]]; then
        TOKEN_AGE=$(( $(date +%s) - TOKEN_TS ))
        if [ "$TOKEN_AGE" -lt "$TOKEN_TTL" ]; then
            exit 0
        fi
    fi
fi

# No valid token — block. Pre-resolve route if CLI available (Option B).
TASK=$(echo "${CLAUDE_TOOL_INPUT:-{}}" | "$VENV_PY" -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('description') or d.get('task') or d.get('prompt') or '')
except Exception:
    print('')
" 2>/dev/null)

if [ -n "$TASK" ] && [ -x "$VENV_PY" ]; then
    ROUTE_JSON=$("$VENV_PY" -m agent_invoker.cli --no-log "$TASK" 2>/dev/null)
    ROLE=$(echo "$ROUTE_JSON" | "$VENV_PY" -c "import sys,json; print(json.load(sys.stdin).get('role','unknown'))" 2>/dev/null)
    CONF=$(echo "$ROUTE_JSON" | "$VENV_PY" -c "import sys,json; print(json.load(sys.stdin).get('confidence',0))" 2>/dev/null)
    printf '{"hookSpecificOutput":{"additionalContext":"InvokerAI pre-resolved: role=%s confidence=%s%%. Call mcp__invokerai__spawn_specialist(task) to get persona bundle + spawn authorization.","permissionDecision":"deny","permissionDecisionReason":"Call mcp__invokerai__spawn_specialist(task) first — already routed above."}}\n' "$ROLE" "$CONF"
else
    echo '{"hookSpecificOutput":{"additionalContext":"InvokerAI: call mcp__invokerai__spawn_specialist(task) — routes and returns role, persona, and tools.","permissionDecision":"deny","permissionDecisionReason":"Call mcp__invokerai__spawn_specialist(task) first."}}'
fi
exit 1
"""


def _homebrew_bin() -> Path | None:
    """Find invoker-mcp installed via Homebrew (absolute path, immune to PATH changes)."""
    for prefix in ["/opt/homebrew", "/usr/local", "/home/linuxbrew/.linuxbrew"]:
        p = Path(prefix) / "bin" / "invoker-mcp"
        if p.exists():
            return p
    try:
        result = subprocess.run(
            ["brew", "--prefix"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            p = Path(result.stdout.strip()) / "bin" / "invoker-mcp"
            if p.exists():
                return p
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _npm_bin() -> Path | None:
    """Find invoker-mcp across nvm / fnm / volta / system npm global bins."""
    # nvm — search all installed node versions, newest first
    nvm_dir = Path(os.environ.get("NVM_DIR", Path.home() / ".nvm"))
    if nvm_dir.exists():
        node_versions = sorted(
            (nvm_dir / "versions" / "node").glob("v*"), reverse=True
        )
        for node_dir in node_versions:
            candidate = node_dir / "bin" / "invoker-mcp"
            if candidate.exists():
                return candidate

    # fnm
    fnm_dir = Path.home() / ".fnm" / "node-versions"
    if fnm_dir.exists():
        for node_dir in sorted(fnm_dir.glob("v*"), reverse=True):
            candidate = node_dir / "installation" / "bin" / "invoker-mcp"
            if candidate.exists():
                return candidate

    # volta
    volta_bin = Path.home() / ".volta" / "bin" / "invoker-mcp"
    if volta_bin.exists():
        return volta_bin

    # system npm global
    try:
        result = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            candidate = Path(result.stdout.strip()).parent / "bin" / "invoker-mcp"
            if candidate.exists():
                return candidate
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def _venv_python() -> Path | None:
    """~/.invokerai/venv/bin/python — always has agent_invoker installed."""
    IS_WIN = sys.platform == "win32"
    p = Path.home() / ".invokerai" / "venv" / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")
    return p if p.exists() else None


def _mcp_entry(pkg_dir: Path) -> dict:
    # 1. Managed venv — always stable, always has agent_invoker, immune to PATH/version issues
    venv_py = _venv_python()
    if venv_py:
        return {"command": str(venv_py), "args": ["-m", "agent_invoker.mcp_server"]}

    # 2. Homebrew — absolute binary path
    brew_bin = _homebrew_bin()
    if brew_bin:
        return {"command": str(brew_bin)}

    # 3. npm (nvm / fnm / volta / system) — absolute path
    npm_bin = _npm_bin()
    if npm_bin:
        return {"command": str(npm_bin)}

    # 4. sys.executable last resort — may be wrong interpreter, print warning
    py = sys.executable
    print(f"  Warning: ~/.invokerai/venv not found. Using {py} — run installer to fix.")
    try:
        subprocess.run([py, "-c", "import agent_invoker"], check=True, capture_output=True)
        return {"command": py, "args": ["-m", "agent_invoker.mcp_server"]}
    except subprocess.CalledProcessError:
        return {"command": py, "args": [str(pkg_dir / "agent_invoker" / "mcp_server.py")]}


def _clear_pycache(pkg_dir: Path) -> None:
    import os
    for root, dirs, files in os.walk(pkg_dir / "agent_invoker"):
        if "__pycache__" in dirs:
            cache = Path(root) / "__pycache__"
            for f in cache.glob("*.pyc"):
                f.unlink(missing_ok=True)


_AGENT_HOOK_COMMAND = f'bash "{_HOOK_SCRIPT_PATH}"'
_AGENT_HOOK_MATCHER = "Agent"
_AGENT_HOOK_MARKER = str(_HOOK_SCRIPT_PATH)

_SUBAGENT_HOOK_COMMAND = (
    "echo '{\"hookSpecificOutput\":{\"additionalContext\":"
    "\"InvokerAI: call mcp__invokerai__confirm_route(task, expected_role) on your first turn to verify correct specialist.\"}}'"
)
_SUBAGENT_HOOK_MARKER = "confirm_route"

_PROMPT_HOOK_COMMAND = (
    "echo '{\"hookSpecificOutput\":{\"additionalContext\":"
    "\"InvokerAI: use mcp__invokerai__spawn_specialist(task) to route agent tasks. Returns role + persona + tools.\"}}'"
)
_PROMPT_HOOK_MARKER = "spawn_specialist"


def _install_hook_script() -> bool:
    _HOOK_SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HOOK_SCRIPT_PATH.write_text(_HOOK_SCRIPT)
    _HOOK_SCRIPT_PATH.chmod(0o755)
    print(f"  Hook script: installed → {_HOOK_SCRIPT_PATH}")
    return True


def _inject_agent_hook(settings: dict) -> bool:
    """Add PreToolUse[Agent] hook — B+C hybrid with spawn token gate."""
    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])

    for entry in pre:
        if entry.get("matcher") == _AGENT_HOOK_MATCHER:
            for h in entry.get("hooks", []):
                if _AGENT_HOOK_MARKER in h.get("command", ""):
                    return False  # already present

    pre.append({
        "matcher": _AGENT_HOOK_MATCHER,
        "hooks": [{"type": "command", "command": _AGENT_HOOK_COMMAND}],
    })
    return True


def _inject_subagent_hook(settings: dict) -> bool:
    """Add SubagentStart hook — fires inside the spawned agent's own context."""
    hooks = settings.setdefault("hooks", {})
    subagent = hooks.setdefault("SubagentStart", [])

    for entry in subagent:
        for h in entry.get("hooks", []):
            if _SUBAGENT_HOOK_MARKER in h.get("command", ""):
                return False  # already present

    subagent.append({
        "hooks": [{"type": "command", "command": _SUBAGENT_HOOK_COMMAND}],
    })
    return True


def _inject_prompt_hook(settings: dict) -> bool:
    """Add UserPromptSubmit hook — stdout is injected into context, nudges MCP routing."""
    hooks = settings.setdefault("hooks", {})
    submit = hooks.setdefault("UserPromptSubmit", [])

    for entry in submit:
        for h in entry.get("hooks", []):
            if _PROMPT_HOOK_MARKER in h.get("command", ""):
                return False  # already present

    submit.append({
        "hooks": [{"type": "command", "command": _PROMPT_HOOK_COMMAND}],
    })
    return True


def setup_claude_code(pkg_dir: Path) -> bool:
    # MCP servers → ~/.claude.json (Claude Code's primary config)
    # Hooks → ~/.claude/settings.json (user settings layer)
    claude_json_path = Path.home() / ".claude.json"
    settings_path = Path.home() / ".claude" / "settings.json"

    if not settings_path.parent.exists():
        print("  Claude Code: not installed, skipping")
        return False

    # Register MCP in ~/.claude.json
    claude_json: dict = {}
    if claude_json_path.exists():
        try:
            claude_json = json.loads(claude_json_path.read_text())
        except json.JSONDecodeError:
            claude_json = {}

    mcp_changed = False
    claude_json.setdefault("mcpServers", {})
    new_entry = _mcp_entry(pkg_dir)
    if claude_json["mcpServers"].get("invokerai") == new_entry:
        print("  Claude Code: MCP already up to date (skipped)")
    else:
        claude_json["mcpServers"]["invokerai"] = new_entry
        mcp_changed = True
        print("  Claude Code: MCP registered → ~/.claude.json")

    if mcp_changed:
        claude_json_path.write_text(json.dumps(claude_json, indent=2) + "\n")

    # Register hooks in ~/.claude/settings.json
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    hooks_changed = False

    if _inject_agent_hook(settings):
        hooks_changed = True
        print("  Claude Code: Agent hook registered → ~/.claude/settings.json")
    else:
        print("  Claude Code: Agent hook already registered (skipped)")

    if _inject_subagent_hook(settings):
        hooks_changed = True
        print("  Claude Code: SubagentStart hook registered → ~/.claude/settings.json")
    else:
        print("  Claude Code: SubagentStart hook already registered (skipped)")

    if _inject_prompt_hook(settings):
        hooks_changed = True
        print("  Claude Code: UserPromptSubmit hook registered → ~/.claude/settings.json")
    else:
        print("  Claude Code: UserPromptSubmit hook already registered (skipped)")

    if hooks_changed:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    return True


def setup_cursor(pkg_dir: Path) -> bool:
    cursor_mcp = Path.home() / ".cursor" / "mcp.json"
    if not cursor_mcp.parent.exists():
        print("  Cursor: not installed, skipping")
        return False

    config: dict = {"mcpServers": {}}
    if cursor_mcp.exists():
        try:
            config = json.loads(cursor_mcp.read_text())
        except json.JSONDecodeError:
            config = {"mcpServers": {}}

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    if "invokerai" in config["mcpServers"]:
        print("  Cursor: MCP already registered (skipped)")
    else:
        config["mcpServers"]["invokerai"] = _mcp_entry(pkg_dir)
        cursor_mcp.write_text(json.dumps(config, indent=2) + "\n")
        print("  Cursor: MCP registered → ~/.cursor/mcp.json")

    return True


def setup_kiro(pkg_dir: Path) -> bool:
    kiro_agents_dir = Path.home() / ".kiro" / "agents"
    if not kiro_agents_dir.parent.exists():
        print("  Kiro: not installed, skipping")
        return False

    kiro_agents_dir.mkdir(parents=True, exist_ok=True)
    agent_file = kiro_agents_dir / "invokerai.json"

    entry = _mcp_entry(pkg_dir)
    config: dict = {
        "name": "invokerai",
        "description": "Agent routing brain — route tasks to optimal specialist via MCP",
        "mcpServers": {},
        "hooks": {},
    }
    if agent_file.exists():
        try:
            config = json.loads(agent_file.read_text())
        except json.JSONDecodeError:
            pass

    changed = False

    config.setdefault("mcpServers", {})
    if "invokerai" in config["mcpServers"]:
        print("  Kiro: MCP already registered (skipped)")
    else:
        config["mcpServers"]["invokerai"] = entry
        changed = True
        print("  Kiro: MCP registered → ~/.kiro/agents/invokerai.json")

    config.setdefault("hooks", {})
    hooks = config["hooks"]

    kiro_agent_hook = f'bash "{_HOOK_SCRIPT_PATH}"'
    if hooks.get("agentSpawn", {}).get("command") != kiro_agent_hook:
        hooks["agentSpawn"] = {"command": kiro_agent_hook}
        changed = True
        print("  Kiro: agentSpawn hook registered → ~/.kiro/agents/invokerai.json")
    else:
        print("  Kiro: agentSpawn hook already registered (skipped)")

    if _PROMPT_HOOK_MARKER not in hooks.get("userPromptSubmit", {}).get("command", ""):
        hooks["userPromptSubmit"] = {"command": _PROMPT_HOOK_COMMAND}
        changed = True
        print("  Kiro: userPromptSubmit hook registered → ~/.kiro/agents/invokerai.json")
    else:
        print("  Kiro: userPromptSubmit hook already registered (skipped)")

    if changed:
        agent_file.write_text(json.dumps(config, indent=2) + "\n")

    return True


def setup_copilot(pkg_dir: Path) -> bool:
    # Project-local — only if a workspace root exists
    cwd_mcp = Path.cwd() / ".github" / "copilot" / "mcp.json"
    if not (Path.cwd() / ".github").exists():
        print("  GitHub Copilot: no .github/ in cwd, skipping")
        return False

    cwd_mcp.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {"servers": {}}
    if cwd_mcp.exists():
        try:
            config = json.loads(cwd_mcp.read_text())
        except json.JSONDecodeError:
            config = {"servers": {}}

    if "servers" not in config:
        config["servers"] = {}

    if "invokerai" in config["servers"]:
        print("  GitHub Copilot: MCP already registered (skipped)")
    else:
        entry = _mcp_entry(pkg_dir)
        server_entry: dict = {"command": entry["command"], "type": "stdio"}
        args = entry.get("args", [])
        if args:
            server_entry["args"] = args
        config["servers"]["invokerai"] = server_entry
        cwd_mcp.write_text(json.dumps(config, indent=2) + "\n")
        print(f"  GitHub Copilot: MCP registered → {cwd_mcp}")

    return True


def inject_claude_md() -> bool:
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if not claude_md.parent.exists():
        print("  CLAUDE.md: ~/.claude not found, skipping")
        return False

    if not claude_md.exists():
        claude_md.write_text(CLAUDE_MD_NODE + "\n")
        print("  CLAUDE.md: node created → ~/.claude/CLAUDE.md")
        return True

    content = claude_md.read_text()
    if CLAUDE_MD_MARKER_START in content:
        # Replace existing node.  Use a lambda replacement so re.sub never
        # interprets backslash sequences in CLAUDE_MD_NODE (e.g. \n, \1).
        import re
        updated = re.sub(
            rf"{re.escape(CLAUDE_MD_MARKER_START)}.*?{re.escape(CLAUDE_MD_MARKER_END)}",
            lambda _m: CLAUDE_MD_NODE,
            content,
            flags=re.DOTALL,
        )
        claude_md.write_text(updated)
        print("  CLAUDE.md: node updated → ~/.claude/CLAUDE.md")
    else:
        claude_md.write_text(content.rstrip() + "\n\n" + CLAUDE_MD_NODE + "\n")
        print("  CLAUDE.md: node appended → ~/.claude/CLAUDE.md")

    return True


def copy_skill(pkg_dir: Path) -> bool:
    src = pkg_dir / "skills" / "invokerai"
    dest = Path.home() / ".claude" / "skills" / "invokerai"
    if not src.exists():
        return False
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    print(f"  Skill: invokerai → ~/.claude/skills/invokerai/")
    return True


def run(pkg_dir: Path | None = None) -> None:
    if pkg_dir is None:
        pkg_dir = Path(__file__).parent.parent

    _clear_pycache(pkg_dir)
    _install_hook_script()
    print("Configuring InvokerAI for editors...")
    print()
    setup_claude_code(pkg_dir)
    setup_cursor(pkg_dir)
    setup_kiro(pkg_dir)
    setup_copilot(pkg_dir)
    inject_claude_md()
    copy_skill(pkg_dir)
    print()
    print("Done. Restart Claude Code / Cursor / Kiro to activate the MCP server.")
    print("Verify: mcp__invokerai__spawn_specialist is visible in Claude's tool list.")


if __name__ == "__main__":
    run()