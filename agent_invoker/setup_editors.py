"""
Configure InvokerAI hooks for Claude Code and inject the InvokerAI node into
~/.claude/CLAUDE.md and ~/.agents/AGENTS.md.

Usage:
    python -m agent_invoker.setup_editors
    invoker setup
"""
from __future__ import annotations

import json
import shutil
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

**YOUR ROLE: orchestrator/planner ONLY.** Never write code. Never implement directly.
Before any multi-step or multi-domain task: read the agent-map, decompose into a DAG,
select agents, then spawn them in order via your own Agent tool.

**Operating contract (host agent):**

1. **Discover domains** — Read `~/.invoker/agent-map.json` to see installed domains + agents.
   ```bash
   cat ~/.invoker/agent-map.json
   ```
   If the map is missing, run `/invokerai:setup` first.

2. **Decompose** — Run `/invokerai:decompose` with the task and discovered domains.
   Always do this — even single-step tasks produce a single-node bead_graph.
   Returns a `bead_graph` DAG: each node has `id`, `domain`, `action`, `deps`, `parallel`.

3. **Select agents** — Run `/invokerai:spawn` with the bead_graph.
   Fills `agent` on each node (best-match per domain × task scoring from the map).
   If `bd` is available, creates a ticket per node and a parent epic.

4. **Execute** — Spawn each node's agent yourself via your own Agent tool:
   - Process in dependency order (nodes where `deps: []` first)
   - Respect `parallel: true` — concurrent spawns at the same DAG level
   - **Pass the bd ticket ID in the agent prompt** (if bd is available) so the agent
     closes and prunes its own ticket on completion

**`/invokerai:spawn` output shape:**
```
{
  "bead_graph": [
    {"id": "node-1", "domain": "architecture", "action": "...", "agent": "architect-reviewer",  "deps": [],          "parallel": false},
    {"id": "node-2", "domain": "backend",       "action": "...", "agent": "backend-developer",  "deps": ["node-1"],  "parallel": false},
    {"id": "node-3", "domain": "testing",       "action": "...", "agent": "test-automator",     "deps": ["node-2"],  "parallel": true}
  ],
  "pattern": "pipeline" | "parallel" | "plan_then_execute" | "feedback_loop" | ...,
  "domains": ["architecture", "backend", "testing"],
  "coverage_gaps": []
}
```

**Available domains — read from agent-map first:**
Before decomposing, read `~/.invoker/agent-map.json` to see which domains have installed agents.
Use only domain names present in the map.

If the map is missing or `~/.invoker/agent-map.json` does not exist, run `/invokerai:setup` first.

**Domain precision rule (critical):** the bead_graph is shaped by domains you provide to decompose —
wrong domains → phantom steps → wasted agents.
- Pass ONLY domains where real work exists. Ask: "does this task actually touch this layer?"
- When unsure, under-specify — low confidence will surface missing domains.
- Never add a domain speculatively.

**Domain decision guide:**

Read `~/.invoker/agent-map.json` to see all available domains and which agents
handle each one. Use only domains present in the map. General rules:

- Add a domain only when real work for that domain exists in the task.
- Skip domains where all work is a side effect of another domain.
- Under-specify rather than over-specify — low confidence will surface missing domains.
- For tasks touching non-engineering domains (marketing, sales, design, etc.),
  check the map — those agents are available if installed.

**As a subagent:** verify you are the correct specialist on your first turn.
Review the task description and confirm it matches your domain before proceeding.

**SKILL BYPASS:** When running inside a skill invocation (/graphify, /kyoko, /hyperframes,
/remotion, /weave, etc.), skills manage their own agent spawning — do not call `/invokerai:decompose`
or `/invokerai:spawn`. InvokerAI routing applies only to direct user tasks."""

CLAUDE_MD_NODE = f"{INVOKERAI_MARKER_START}\n{_INVOKERAI_NODE_BODY}\n{INVOKERAI_MARKER_END}"
AGENTS_MD_NODE = CLAUDE_MD_NODE


_SUBAGENT_HOOK_COMMAND = (
    "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"SubagentStart\",\"additionalContext\":"
    "\"InvokerAI: verify correct specialist on first turn — confirm task matches your domain. "
    "ROLE: orchestrator/planner ONLY. Never write code. Never implement directly. "
    "Read ~/.invoker/agent-map.json to discover domains. "
    "Run /invokerai:decompose to build DAG, /invokerai:spawn to select agents, then spawn via Agent tool. "
    "CAVEMAN MODE ULTRA: drop articles/filler/hedging/pleasantries. Fragments OK. Short synonyms. "
    "Abbreviate (DB/auth/config/req/res/fn/impl). Arrows for causality (X->Y). One word when one word enough. "
    "Code blocks unchanged. Technical terms exact.\"}}'"
)
_SUBAGENT_HOOK_MARKER = "InvokerAI"
_SUBAGENT_HOOK_CURRENT_MARKER = "invokerai:decompose"

_PROMPT_HOOK_COMMAND = (
    "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":"
    "\"InvokerAI: before any task, read ~/.invoker/agent-map.json for available domains, "
    "run /invokerai:decompose to build the execution DAG, /invokerai:spawn to select agents, "
    "then spawn the returned installed agents yourself in order. "
    "Never do coding tasks directly — only plan and orchestrate.\"}}'"
)
_PROMPT_HOOK_MARKER = "InvokerAI"
_PROMPT_HOOK_CURRENT_MARKER = "/invokerai:decompose"


def _inject_hook(
    settings: dict,
    hooks_key: str,
    marker: str,
    current_marker: str,
    command: str,
) -> bool:
    """Inject a single hook entry into settings, replacing stale InvokerAI entries.

    Replaces all stale entries (marker present, current_marker absent) in one pass
    and appends a fresh entry if none with current_marker is found.
    Returns True if settings were modified.
    """
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault(hooks_key, [])

    found_current = False
    changed = False
    new_entries = []

    for entry in entries:
        new_inner = []
        for h in entry.get("hooks", []):
            cmd = h.get("command", "")
            if marker in cmd:
                if current_marker in cmd:
                    new_inner.append(h)
                    found_current = True
                else:
                    changed = True  # stale — drop
            else:
                new_inner.append(h)
        if new_inner:
            new_entry = dict(entry)
            new_entry["hooks"] = new_inner
            new_entries.append(new_entry)
        elif new_inner != entry.get("hooks", []):
            changed = True  # entry became empty, drop it

    if changed:
        hooks[hooks_key] = new_entries

    if found_current:
        return changed

    new_entries.append({"hooks": [{"type": "command", "command": command}]})
    hooks[hooks_key] = new_entries
    return True


def _inject_subagent_hook(settings: dict) -> bool:
    return _inject_hook(
        settings,
        "SubagentStart",
        _SUBAGENT_HOOK_MARKER,
        _SUBAGENT_HOOK_CURRENT_MARKER,
        _SUBAGENT_HOOK_COMMAND,
    )


def _inject_prompt_hook(settings: dict) -> bool:
    return _inject_hook(
        settings,
        "UserPromptSubmit",
        _PROMPT_HOOK_MARKER,
        _PROMPT_HOOK_CURRENT_MARKER,
        _PROMPT_HOOK_COMMAND,
    )


def setup_claude_code(pkg_dir: Path) -> bool:
    """Inject SubagentStart + UserPromptSubmit hooks into ~/.claude/settings.json."""
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

    hooks_changed = False

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

    print("Configuring InvokerAI for editors...")
    print()
    setup_claude_code(pkg_dir)
    inject_claude_md()
    inject_agents_md()
    copy_skill(pkg_dir)
    print()
    print("Done. Restart Claude Code to activate.")
    print("Usage: invoker spawn \"TASK\" --domains d1,d2")
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

    # ── ~/.claude/settings.json hooks ────────────────────────────────────────
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            changed = False

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