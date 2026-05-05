#!/usr/bin/env python3
"""
InvokerAI one-time migration script.

Upgrades an existing InvokerAI setup to the current architecture:
  - Replaces echo-based hooks with hookSpecificOutput + spawn-token gate script
  - Updates MCP entry to use ~/.invokerai/venv/bin/python (venv-first)
  - Updates CLAUDE.md node to blocking-requirement language
  - Installs ~/.invokerai/hooks/pre-agent.sh
  - Updates Kiro agentSpawn / userPromptSubmit hooks
  - Updates Cursor MCP entry

Safe to run multiple times — idempotent after first migration.

Usage:
    python migrate.py
    invoker migrate
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ── old patterns to purge ─────────────────────────────────────────────────────

_OLD_HOOK_MARKERS = [
    "mcp__invokerai__route_task",          # old prompt/agent echo hooks
    "REQUIRED: call mcp__invokerai",       # old agent hook text
    "confirm correct specialist",          # old subagent hook text
    "invoker spawn TASK (CLI",             # old CLI-preferred prompt hook
    "invoker spawn TASK --persona",        # old CLI-preferred subagent hook
    "invoker confirm TASK ROLE",           # old CLI confirm subagent hook
    "CLI-first",                           # old CLI-first marker
]

# Hooks that have the right marker content but are missing hookEventName — handled
# by _inject_subagent_hook / _inject_prompt_hook stale detection, not purge. Listed
# here only for documentation; purge skips them intentionally so inject fns replace them.
_STALE_MISSING_HOOK_EVENT_NAME_MARKERS = [
    "hookSpecificOutput",  # any hookSpecificOutput without hookEventName is stale
]

_OLD_CLAUDE_MD_MARKER_START = "<!-- INVOKERAI-START -->"
_OLD_CLAUDE_MD_MARKER_END = "<!-- INVOKERAI-END -->"

# ── load current setup_editors state ─────────────────────────────────────────


# ── hook purge helpers ────────────────────────────────────────────────────────

def _is_old_hook(hook: dict) -> bool:
    cmd = hook.get("command", "")
    return any(marker in cmd for marker in _OLD_HOOK_MARKERS)


def _purge_old_hooks(settings: dict) -> int:
    """Remove old InvokerAI echo hooks from settings dict. Returns count removed."""
    removed = 0
    hooks = settings.get("hooks", {})
    for event_name in list(hooks.keys()):
        entries = hooks[event_name]
        if not isinstance(entries, list):
            continue
        new_entries = []
        for entry in entries:
            new_inner = [h for h in entry.get("hooks", []) if not _is_old_hook(h)]
            old_count = len(entry.get("hooks", []))
            removed += old_count - len(new_inner)
            if new_inner:
                entry = {**entry, "hooks": new_inner}
                new_entries.append(entry)
            # Drop the outer entry entirely if no hooks remain
        hooks[event_name] = new_entries
    # Drop empty event lists
    settings["hooks"] = {k: v for k, v in hooks.items() if v}
    return removed


# ── per-editor migration ──────────────────────────────────────────────────────

def migrate_claude_code(pkg_dir: Path) -> None:
    from agent_invoker.setup_editors import (
        _mcp_entry, _inject_agent_hook, _inject_subagent_hook,
        _inject_prompt_hook, _HOOK_SCRIPT_PATH, _INVOKERAI_AUTO_APPROVE,
    )

    claude_json_path = Path.home() / ".claude.json"
    settings_path = Path.home() / ".claude" / "settings.json"

    if not settings_path.parent.exists():
        print("  Claude Code: not installed, skipping")
        return

    # ── MCP entry (force update) ──
    claude_json: dict = {}
    if claude_json_path.exists():
        try:
            claude_json = json.loads(claude_json_path.read_text())
        except json.JSONDecodeError:
            claude_json = {}

    claude_json.setdefault("mcpServers", {})
    new_entry = {**_mcp_entry(pkg_dir), "autoApprove": _INVOKERAI_AUTO_APPROVE}
    old_entry = claude_json["mcpServers"].get("invokerai")
    if old_entry != new_entry:
        claude_json["mcpServers"]["invokerai"] = new_entry
        claude_json_path.write_text(json.dumps(claude_json, indent=2) + "\n")
        print(f"  Claude Code: MCP entry updated → {new_entry.get('command')}")
    else:
        print("  Claude Code: MCP entry already current (skipped)")

    # ── hooks (purge old, inject new) ──
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    purged = _purge_old_hooks(settings)
    if purged:
        print(f"  Claude Code: removed {purged} old echo hook(s)")

    changed = False
    changed |= _inject_agent_hook(settings)
    changed |= _inject_subagent_hook(settings)
    changed |= _inject_prompt_hook(settings)

    if purged or changed:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        print("  Claude Code: hooks migrated → ~/.claude/settings.json")
        if changed:
            print("    (stale hooks replaced — hookEventName now present in SubagentStart + UserPromptSubmit)")
    else:
        print("  Claude Code: hooks already current (skipped)")


def migrate_cursor(pkg_dir: Path) -> None:
    from agent_invoker.setup_editors import _mcp_entry

    cursor_mcp = Path.home() / ".cursor" / "mcp.json"
    if not cursor_mcp.parent.exists():
        print("  Cursor: not installed, skipping")
        return

    config: dict = {"mcpServers": {}}
    if cursor_mcp.exists():
        try:
            config = json.loads(cursor_mcp.read_text())
        except json.JSONDecodeError:
            config = {"mcpServers": {}}

    config.setdefault("mcpServers", {})
    new_entry = _mcp_entry(pkg_dir)
    old_entry = config["mcpServers"].get("invokerai")
    if old_entry != new_entry:
        config["mcpServers"]["invokerai"] = new_entry
        cursor_mcp.write_text(json.dumps(config, indent=2) + "\n")
        print(f"  Cursor: MCP entry updated → {new_entry.get('command')}")
    else:
        print("  Cursor: MCP entry already current (skipped)")


def migrate_kiro(pkg_dir: Path) -> None:
    from agent_invoker.setup_editors import (
        _mcp_entry, _HOOK_SCRIPT_PATH,
        _PROMPT_HOOK_COMMAND, _PROMPT_HOOK_MARKER,
    )

    kiro_agents_dir = Path.home() / ".kiro" / "agents"
    if not kiro_agents_dir.parent.exists():
        print("  Kiro: not installed, skipping")
        return

    kiro_agents_dir.mkdir(parents=True, exist_ok=True)
    agent_file = kiro_agents_dir / "invokerai.json"

    config: dict = {"name": "invokerai", "mcpServers": {}, "hooks": {}}
    if agent_file.exists():
        try:
            config = json.loads(agent_file.read_text())
        except json.JSONDecodeError:
            pass

    config.setdefault("mcpServers", {})
    config.setdefault("hooks", {})
    changed = False

    new_entry = _mcp_entry(pkg_dir)
    if config["mcpServers"].get("invokerai") != new_entry:
        config["mcpServers"]["invokerai"] = new_entry
        changed = True
        print(f"  Kiro: MCP entry updated → {new_entry.get('command')}")

    kiro_agent_hook = f'bash "{_HOOK_SCRIPT_PATH}"'
    if config["hooks"].get("agentSpawn", {}).get("command") != kiro_agent_hook:
        config["hooks"]["agentSpawn"] = {"command": kiro_agent_hook}
        changed = True
        print("  Kiro: agentSpawn hook updated")

    if _PROMPT_HOOK_MARKER not in config["hooks"].get("userPromptSubmit", {}).get("command", ""):
        config["hooks"]["userPromptSubmit"] = {"command": _PROMPT_HOOK_COMMAND}
        changed = True
        print("  Kiro: userPromptSubmit hook updated")

    if changed:
        agent_file.write_text(json.dumps(config, indent=2) + "\n")
    else:
        print("  Kiro: already current (skipped)")


def migrate_claude_md() -> None:
    from agent_invoker.setup_editors import inject_claude_md
    inject_claude_md()


# ── main ──────────────────────────────────────────────────────────────────────

def run() -> None:
    pkg_dir = Path(__file__).parent
    sys.path.insert(0, str(pkg_dir))

    from agent_invoker.setup_editors import _install_hook_script

    print("InvokerAI migration — upgrading existing setup...")
    print()

    _install_hook_script()
    print()

    migrate_claude_code(pkg_dir)
    migrate_cursor(pkg_dir)
    migrate_kiro(pkg_dir)
    migrate_claude_md()

    print()
    print("Migration complete.")
    print("Restart Claude Code / Cursor / Kiro to pick up changes.")
    print()
    print("New tool surface:")
    print("  mcp__invokerai__spawn_specialist(task)       ← primary, use this")
    print("  mcp__invokerai__route_task(task)             ← read-only classifier")
    print("  mcp__invokerai__confirm_route(task, role)    ← subagent self-correction")
    print("  mcp__invokerai__list_agents()                ← discovery")


if __name__ == "__main__":
    run()
