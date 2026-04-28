"""
Auto-configure InvokerAI MCP server for Claude Code, Cursor, and GitHub Copilot.
Also injects the InvokerAI CLAUDE.md node into ~/.claude/CLAUDE.md.

Usage:
    python -m agent_invoker.setup_editors
    invoker setup
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

CLAUDE_MD_MARKER_START = "<!-- INVOKERAI-START -->"
CLAUDE_MD_MARKER_END = "<!-- INVOKERAI-END -->"

CLAUDE_MD_NODE = """\
<!-- INVOKERAI-START -->
## InvokerAI — Agent Router

Before spawning any agent, call `mcp__invokerai__route_task` to get the optimal specialist.

```
mcp__invokerai__route_task(task: str, custom_registry?: str)
→ { routing, role, confidence, tools[] }
```

**Rules:**
- `routing == "direct"` → spawn the `role` agent with the returned `tools`
- `routing == "orchestrate"` → use multi-agent coordination
- `confidence < 50` → ask user to clarify before routing
- Always pass the returned `tools` list to the spawned agent
<!-- INVOKERAI-END -->"""


def _python_cmd() -> str:
    return sys.executable


def _mcp_entry(pkg_dir: Path) -> dict:
    py = _python_cmd()
    # Prefer module invocation (works after pip install)
    # Fall back to direct script path if package not installed
    try:
        subprocess.run(
            [py, "-c", "import agent_invoker"],
            check=True, capture_output=True,
        )
        return {"command": py, "args": ["-m", "agent_invoker.mcp_server"]}
    except subprocess.CalledProcessError:
        script = str(pkg_dir / "agent_invoker" / "mcp_server.py")
        return {"command": py, "args": [script]}


def setup_claude_code(pkg_dir: Path) -> bool:
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.parent.exists():
        print("  Claude Code: not installed, skipping")
        return False

    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    if "invokerai" in settings["mcpServers"]:
        print("  Claude Code: MCP already registered (skipped)")
    else:
        settings["mcpServers"]["invokerai"] = _mcp_entry(pkg_dir)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        print("  Claude Code: MCP registered → ~/.claude/settings.json")

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
        config["servers"]["invokerai"] = {
            "command": entry["command"],
            "args": entry["args"],
            "type": "stdio",
        }
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
        # Replace existing node
        import re
        updated = re.sub(
            rf"{re.escape(CLAUDE_MD_MARKER_START)}.*?{re.escape(CLAUDE_MD_MARKER_END)}",
            CLAUDE_MD_NODE,
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

    print("Configuring InvokerAI for editors...")
    print()
    setup_claude_code(pkg_dir)
    setup_cursor(pkg_dir)
    setup_copilot(pkg_dir)
    inject_claude_md()
    copy_skill(pkg_dir)
    print()
    print("Done. Restart Claude Code / Cursor to activate the MCP server.")
    print("Verify: mcp__invokerai__route_task is visible in Claude's tool list.")


if __name__ == "__main__":
    run()