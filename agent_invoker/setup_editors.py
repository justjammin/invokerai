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

INVOKERAI_MARKER_START = "<!-- INVOKERAI-START -->"
INVOKERAI_MARKER_END = "<!-- INVOKERAI-END -->"

# Back-compat aliases used by inject functions and tests
CLAUDE_MD_MARKER_START = INVOKERAI_MARKER_START
CLAUDE_MD_MARKER_END = INVOKERAI_MARKER_END
AGENTS_MD_MARKER_START = INVOKERAI_MARKER_START
AGENTS_MD_MARKER_END = INVOKERAI_MARKER_END

_INVOKERAI_NODE_BODY = """\
## InvokerAI — Agent Router

**BLOCKING REQUIREMENT:** NEVER call the `Agent` tool directly and NEVER do coding tasks directly. Always use
`mcp__invokerai__spawn_specialist(task, domains=[...])` — it routes AND returns the execution bundle.
If MCP is unavailable: `invoker spawn "TASK" --domains d1,d2` from terminal returns the same bundle and writes the spawn token.

**ROLE: orchestrator/planner ONLY.** Never write code. Never read files for implementation purposes.
Only: plan, decompose, identify domains, call spawn_specialist.

**Canonical domains** (pass 1–N):
`architecture` | `backend` | `frontend` | `database` | `devops` | `security`
`ml` | `testing` | `documentation` | `mobile` | `data` | `code-review`

```
mcp__invokerai__spawn_specialist(task: str, domains: list[str])
→ { routing, role, confidence, tools[], persona: { system_prompt_fragment },
    spawn_authorized: true, spawn_count: N, steps: [...] }
```

**Rules:**
- `routing == "direct"` → spawn returned `role` with returned `tools` and `system_prompt_fragment`
- `routing == "orchestrate"` → spawn each step in `steps` array sequentially (or parallel where `parallel: true`)
- `confidence < 50` → ask user to clarify before routing
- As a subagent: call `mcp__invokerai__confirm_route(task, expected_role)` on your first turn
- User naming an agent type does NOT exempt this requirement

**Domain precision rule (critical):** `steps[]` is shaped by `domains[]` you pass — wrong domains → phantom steps → wasted agents.
- Pass ONLY domains where real work exists. Ask: "does this task actually touch this layer?"
- When unsure, under-specify — low confidence score will surface missing domains.
- Never add a domain speculatively.

**Domain decision guide:**

| Domain | Add when... | Skip when... |
|--------|-------------|--------------|
| `architecture` | New subsystem design, cross-cutting redesign, impl agent needs codebase context before it can safely start, "how should we structure X?" | Bug fix, additive feature with clear scope, impl path is obvious |
| `backend` | Server routes, REST/GraphQL APIs, IPC handlers, business logic, auth middleware | Pure UI work, DB-only schema changes with no server code |
| `frontend` | UI components, styling, client-side state, browser events, rendering | Server-only work, no user-facing changes |
| `database` | Schema changes, migrations, query optimization, indexes, ORM models | No DB reads/writes in the task |
| `devops` | CI/CD pipelines, Dockerfiles, infra config, deploy scripts, env vars | App code changes only |
| `security` | Auth flows, permissions, secrets handling, input validation, CVE fixes | Feature work with no trust boundary changes |
| `ml` | Model training, inference, embeddings, prompt engineering, vector search | Standard CRUD with no ML components |
| `testing` | Writing/fixing tests, test infra, coverage gaps, flaky test diagnosis | Impl work where tests are a side effect (let impl agent write them) |
| `documentation` | API docs, READMEs, changelogs, docstrings, user guides | Code-only changes with no public surface |
| `mobile` | iOS/Android native code, React Native, Flutter, mobile-specific APIs | Web-only work |
| `data` | ETL pipelines, data transforms, analytics queries, reporting | App features with no data pipeline involvement |
| `code-review` | Reviewing a diff/PR, auditing quality/security, post-impl review | Active implementation (review ≠ build) |

**SKILL BYPASS:** When running inside a skill invocation (/graphify, /kyoko, /hyperframes,
/remotion, /weave, etc.), do NOT call mcp__invokerai__spawn_specialist. Skills manage their own
agent spawning. InvokerAI routing applies only to direct user tasks."""

CLAUDE_MD_NODE = f"{INVOKERAI_MARKER_START}\n{_INVOKERAI_NODE_BODY}\n{INVOKERAI_MARKER_END}"
AGENTS_MD_NODE = CLAUDE_MD_NODE

_HOOK_SCRIPT_PATH = Path.home() / ".invokerai" / "hooks" / "pre-agent.sh"

_INVOKERAI_AUTO_APPROVE = [
    "spawn_specialist", "route_task", "confirm_route",
    "decompose_task", "list_agents", "agent_profile", "route",
]

_HOOK_SCRIPT = r"""#!/bin/bash
# InvokerAI PreToolUse[Agent] hook — spawn token gate (multi-count)
# Allows Agent calls authorized by spawn_specialist; blocks all others.

VENV_PY="$HOME/.invokerai/venv/bin/python"
TOKEN="$HOME/.invokerai/spawn_token"
TOKEN_TTL=30

# Token gate: spawn_specialist wrote this token — allow and decrement count
if [ -f "$TOKEN" ]; then
    TOKEN_CONTENT=$(cat "$TOKEN" 2>/dev/null)

    # Support both legacy format (timestamp only) and new format (count:timestamp)
    if [[ "$TOKEN_CONTENT" =~ ^([0-9]+):([0-9]+)$ ]]; then
        TOKEN_COUNT="${BASH_REMATCH[1]}"
        TOKEN_TS="${BASH_REMATCH[2]}"
    elif [[ "$TOKEN_CONTENT" =~ ^[0-9]+$ ]]; then
        TOKEN_COUNT=1
        TOKEN_TS="$TOKEN_CONTENT"
    else
        TOKEN_COUNT=0
        TOKEN_TS=0
    fi

    if [ "$TOKEN_COUNT" -gt 0 ]; then
        TOKEN_AGE=$(( $(date +%s) - TOKEN_TS ))
        if [ "$TOKEN_AGE" -lt "$TOKEN_TTL" ]; then
            # Decrement or remove
            if [ "$TOKEN_COUNT" -gt 1 ]; then
                echo "$(( TOKEN_COUNT - 1 )):$TOKEN_TS" > "$TOKEN"
            else
                rm -f "$TOKEN"
            fi
            exit 0
        fi
    fi
    rm -f "$TOKEN"
fi

# No valid token — block with guidance
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
    printf '{"hookSpecificOutput":{"additionalContext":"InvokerAI pre-resolved: role=%s confidence=%s%%. Call mcp__invokerai__spawn_specialist(task, domains=[...]) — writes spawn token + returns execution bundle.","permissionDecision":"deny","permissionDecisionReason":"Call mcp__invokerai__spawn_specialist first."}}\n' "$ROLE" "$CONF"
else
    echo '{"hookSpecificOutput":{"additionalContext":"InvokerAI: call mcp__invokerai__spawn_specialist(task, domains=[...]) — routes, writes spawn token, returns execution bundle.","permissionDecision":"deny","permissionDecisionReason":"Call mcp__invokerai__spawn_specialist first."}}'
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
    # managed venv — immune to PATH/version changes, always has agent_invoker
    venv_py = _venv_python()
    if venv_py:
        return {"command": "/bin/bash", "args": ["-c", "$HOME/.invokerai/venv/bin/python -m agent_invoker.mcp_server"]}

    brew_bin = _homebrew_bin()
    if brew_bin:
        return {"command": str(brew_bin)}

    npm_bin = _npm_bin()
    if npm_bin:
        return {"command": str(npm_bin)}

    # last resort — sys.executable may be the wrong interpreter
    py = sys.executable
    print(f"  Warning: ~/.invokerai/venv not found. Using {py} — run installer to fix.")
    try:
        subprocess.run([py, "-c", "import agent_invoker"], check=True, capture_output=True)
        return {"command": "/bin/bash", "args": ["-c", "$HOME/.invokerai/venv/bin/python -m agent_invoker.mcp_server"]}
    except subprocess.CalledProcessError:
        return {"command": "/bin/bash", "args": ["-c", "$HOME/.invokerai/venv/bin/python -m agent_invoker.mcp_server"]}


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
    "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"SubagentStart\",\"additionalContext\":"
    "\"InvokerAI: call mcp__invokerai__confirm_route(task, expected_role) on first turn — verify correct specialist. "
    "ROLE: orchestrator/planner ONLY. Never write code. Never implement directly. "
    "Identify 1+ domains from: architecture|backend|frontend|database|devops|security|ml|testing|documentation|mobile|data|code-review. "
    "Call mcp__invokerai__spawn_specialist(task, domains=[...]) — returns execution bundle + spawns specialist+reviewer. "
    "MCP unavailable? Run: invoker spawn \\\"TASK\\\" --domains d1,d2 from terminal — same bundle, same token. "
    "CAVEMAN MODE ULTRA: drop articles/filler/hedging/pleasantries. Fragments OK. Short synonyms. "
    "Abbreviate (DB/auth/config/req/res/fn/impl). Arrows for causality (X->Y). One word when one word enough. "
    "Code blocks unchanged. Technical terms exact.\"}}'"
)
_SUBAGENT_HOOK_MARKER = "InvokerAI"

_PROMPT_HOOK_COMMAND = (
    "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":"
    "\"InvokerAI: route agent tasks via mcp__invokerai__spawn_specialist(task, domains=[...]). "
    "Identify domains first: architecture|backend|frontend|database|devops|security|ml|testing|documentation|mobile|data|code-review. "
    "Never spawn Agent directly. Never do coding tasks directly — only plan and orchestrate. "
    "MCP unavailable? Use: invoker spawn \\\"TASK\\\" --domains d1,d2 from terminal.\"}}'"
)
_PROMPT_HOOK_MARKER = "InvokerAI"
_PROMPT_HOOK_CURRENT_MARKER = "mcp__invokerai__spawn_specialist"


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


_SUBAGENT_HOOK_CURRENT_MARKER = "hookEventName"


def _inject_subagent_hook(settings: dict) -> bool:
    """Add SubagentStart hook — fires inside the spawned agent's own context.

    Replaces ALL stale InvokerAI entries in a single pass (avoids duplicates
    when multiple stale entries accumulate across upgrades).
    """
    hooks = settings.setdefault("hooks", {})
    subagent = hooks.setdefault("SubagentStart", [])

    found_current = False
    changed = False
    new_subagent = []

    for entry in subagent:
        new_inner = []
        for h in entry.get("hooks", []):
            cmd = h.get("command", "")
            if _SUBAGENT_HOOK_MARKER in cmd:
                if _SUBAGENT_HOOK_CURRENT_MARKER in cmd:
                    # already current — keep as-is, mark found
                    new_inner.append(h)
                    found_current = True
                else:
                    # stale — drop (will re-add once below if no current found yet)
                    changed = True
            else:
                new_inner.append(h)
        if new_inner:
            new_entry = dict(entry)
            new_entry["hooks"] = new_inner
            new_subagent.append(new_entry)
        elif new_inner != entry.get("hooks", []):
            changed = True  # entry became empty, drop it

    if changed:
        hooks["SubagentStart"] = new_subagent

    if found_current:
        return changed  # cleaned up stale entries but didn't need to add

    # No current entry — append fresh
    new_subagent.append({
        "hooks": [{"type": "command", "command": _SUBAGENT_HOOK_COMMAND}],
    })
    hooks["SubagentStart"] = new_subagent
    return True


def _inject_prompt_hook(settings: dict) -> bool:
    """Add UserPromptSubmit hook — stdout injected into context, nudges CLI routing."""
    hooks = settings.setdefault("hooks", {})
    submit = hooks.get("UserPromptSubmit", [])

    found_current = False
    changed = False
    new_submit = []
    for entry in submit:
        new_inner = []
        for h in entry.get("hooks", []):
            cmd = h.get("command", "")
            if _PROMPT_HOOK_MARKER in cmd:
                if _PROMPT_HOOK_CURRENT_MARKER in cmd:
                    new_inner.append(h)
                    found_current = True
                else:
                    changed = True  # stale — missing hookEventName or outdated content
            else:
                new_inner.append(h)
        if new_inner:
            new_entry = dict(entry)
            new_entry["hooks"] = new_inner
            new_submit.append(new_entry)

    if changed:
        hooks["UserPromptSubmit"] = new_submit
    if found_current:
        return changed

    new_submit.append({
        "hooks": [{"type": "command", "command": _PROMPT_HOOK_COMMAND}],
    })
    hooks["UserPromptSubmit"] = new_submit
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
    new_entry = {**_mcp_entry(pkg_dir), "autoApprove": _INVOKERAI_AUTO_APPROVE}
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


def _cursor_installed() -> bool:
    IS_WIN = sys.platform == "win32"
    IS_MAC = sys.platform == "darwin"
    candidates = []
    if IS_MAC:
        candidates = [Path("/Applications/Cursor.app"), Path.home() / "Applications" / "Cursor.app"]
    elif IS_WIN:
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Cursor" / "Cursor.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Cursor" / "Cursor.exe",
        ]
    else:
        candidates = [Path("/usr/bin/cursor"), Path("/usr/local/bin/cursor"), Path.home() / ".local" / "bin" / "cursor"]
    return any(p.exists() for p in candidates)


def setup_cursor(pkg_dir: Path) -> bool:
    cursor_mcp = Path.home() / ".cursor" / "mcp.json"
    if not cursor_mcp.parent.exists():
        if not _cursor_installed():
            print("  Cursor: not installed, skipping")
            return False
        cursor_mcp.parent.mkdir(parents=True, exist_ok=True)

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


def inject_agents_md(agents_md: Path | None = None) -> bool:
    if agents_md is None:
        agents_md = Path.home() / ".agents" / "AGENTS.md"

    agents_md.parent.mkdir(parents=True, exist_ok=True)

    if not agents_md.exists():
        agents_md.write_text(AGENTS_MD_NODE + "\n")
        print(f"  AGENTS.md: created → {agents_md}")
        return True

    content = agents_md.read_text()
    if AGENTS_MD_MARKER_START in content:
        import re
        updated = re.sub(
            rf"{re.escape(AGENTS_MD_MARKER_START)}.*?{re.escape(AGENTS_MD_MARKER_END)}",
            lambda _m: AGENTS_MD_NODE,
            content,
            flags=re.DOTALL,
        )
        agents_md.write_text(updated)
        print(f"  AGENTS.md: node updated → {agents_md}")
    else:
        agents_md.write_text(content + "\n\n" + AGENTS_MD_NODE + "\n")
        print(f"  AGENTS.md: node appended → {agents_md}")

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
    inject_agents_md()
    copy_skill(pkg_dir)
    print()
    print("Done. Restart Claude Code / Cursor / Kiro to activate.")
    print("CLI-first: `invoker spawn TASK` (preferred) or mcp__invokerai__spawn_specialist(task).")
    print("To remove: `invoker uninstall`")


def uninstall(purge: bool = False) -> None:
    print("Uninstalling InvokerAI...")
    print()

    # ── ~/.claude/CLAUDE.md ───────────────────────────────────────────────────
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        import re
        content = claude_md.read_text()
        if CLAUDE_MD_MARKER_START in content:
            updated = re.sub(
                rf"\n*{re.escape(CLAUDE_MD_MARKER_START)}.*?{re.escape(CLAUDE_MD_MARKER_END)}\n*",
                "\n",
                content,
                flags=re.DOTALL,
            )
            claude_md.write_text(updated)
            print("  CLAUDE.md: InvokerAI block removed")
        else:
            print("  CLAUDE.md: block not found (skipped)")

    # ── ~/.agents/AGENTS.md ──────────────────────────────────────────────────
    agents_md = Path.home() / ".agents" / "AGENTS.md"
    if agents_md.exists():
        import re
        content = agents_md.read_text()
        if AGENTS_MD_MARKER_START in content:
            updated = re.sub(
                rf"\n*{re.escape(AGENTS_MD_MARKER_START)}.*?{re.escape(AGENTS_MD_MARKER_END)}\n*",
                "\n",
                content,
                flags=re.DOTALL,
            )
            agents_md.write_text(updated)
            print("  AGENTS.md: InvokerAI block removed")
        else:
            print("  AGENTS.md: block not found (skipped)")

    # ── ~/.claude.json MCP entry ──────────────────────────────────────────────
    claude_json_path = Path.home() / ".claude.json"
    if claude_json_path.exists():
        try:
            data = json.loads(claude_json_path.read_text())
            if data.get("mcpServers", {}).pop("invokerai", None) is not None:
                claude_json_path.write_text(json.dumps(data, indent=2) + "\n")
                print("  ~/.claude.json: MCP entry removed")
            else:
                print("  ~/.claude.json: entry not found (skipped)")
        except (json.JSONDecodeError, OSError):
            print("  ~/.claude.json: could not parse (skipped)")

    # ── ~/.claude/settings.json hooks ────────────────────────────────────────
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            changed = False

            # PreToolUse[Agent] — remove entries referencing hook script
            pre = settings.get("hooks", {}).get("PreToolUse", [])
            new_pre = [
                e for e in pre
                if not any(_AGENT_HOOK_MARKER in h.get("command", "") for h in e.get("hooks", []))
            ]
            if len(new_pre) != len(pre):
                settings["hooks"]["PreToolUse"] = new_pre
                changed = True
                print("  settings.json: Agent hook removed")

            # SubagentStart — remove InvokerAI entries
            sub = settings.get("hooks", {}).get("SubagentStart", [])
            new_sub = [
                e for e in sub
                if not any(_SUBAGENT_HOOK_MARKER in h.get("command", "") for h in e.get("hooks", []))
            ]
            if len(new_sub) != len(sub):
                settings["hooks"]["SubagentStart"] = new_sub
                changed = True
                print("  settings.json: SubagentStart hook removed")

            # UserPromptSubmit — remove InvokerAI entries
            prompt = settings.get("hooks", {}).get("UserPromptSubmit", [])
            new_prompt = [
                e for e in prompt
                if not any(_PROMPT_HOOK_MARKER in h.get("command", "") for h in e.get("hooks", []))
            ]
            if len(new_prompt) != len(prompt):
                settings["hooks"]["UserPromptSubmit"] = new_prompt
                changed = True
                print("  settings.json: UserPromptSubmit hook removed")

            if changed:
                settings_path.write_text(json.dumps(settings, indent=2) + "\n")
            else:
                print("  settings.json: no InvokerAI hooks found (skipped)")
        except (json.JSONDecodeError, OSError):
            print("  settings.json: could not parse (skipped)")

    # ── ~/.cursor/mcp.json ────────────────────────────────────────────────────
    cursor_mcp = Path.home() / ".cursor" / "mcp.json"
    if cursor_mcp.exists():
        try:
            data = json.loads(cursor_mcp.read_text())
            if data.get("mcpServers", {}).pop("invokerai", None) is not None:
                cursor_mcp.write_text(json.dumps(data, indent=2) + "\n")
                print("  ~/.cursor/mcp.json: entry removed")
            else:
                print("  ~/.cursor/mcp.json: entry not found (skipped)")
        except (json.JSONDecodeError, OSError):
            print("  ~/.cursor/mcp.json: could not parse (skipped)")

    # ── ~/.kiro/agents/invokerai.json ─────────────────────────────────────────
    kiro_file = Path.home() / ".kiro" / "agents" / "invokerai.json"
    if kiro_file.exists():
        kiro_file.unlink()
        print("  ~/.kiro/agents/invokerai.json: removed")

    # ── .github/copilot/mcp.json (cwd) ───────────────────────────────────────
    copilot_mcp = Path.cwd() / ".github" / "copilot" / "mcp.json"
    if copilot_mcp.exists():
        try:
            data = json.loads(copilot_mcp.read_text())
            if data.get("servers", {}).pop("invokerai", None) is not None:
                copilot_mcp.write_text(json.dumps(data, indent=2) + "\n")
                print(f"  {copilot_mcp}: entry removed")
        except (json.JSONDecodeError, OSError):
            pass

    # ── ~/.invokerai/ (optional purge) ────────────────────────────────────────
    invokerai_dir = Path.home() / ".invokerai"
    if purge and invokerai_dir.exists():
        shutil.rmtree(invokerai_dir)
        print(f"  ~/.invokerai/: purged (venv, logs, tokens deleted)")
    elif invokerai_dir.exists():
        print(f"  ~/.invokerai/: kept (run with --purge to delete venv + logs)")

    print()
    print("Done. Run `pip uninstall agent-invoker` to remove the package.")


if __name__ == "__main__":
    run()