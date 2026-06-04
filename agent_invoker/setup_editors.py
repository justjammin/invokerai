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
Before any multi-step or multi-domain task: decompose into domains, run `invoker spawn`, then
spawn the returned installed agents yourself using your own Agent tool in step order.

**Operating contract (host agent):**

1. **Identify domains** for the task (1–N from the list below).
2. **Run `invoker spawn`** to get the lean execution plan:
   ```
   invoker spawn "TASK" --domains d1,d2
   ```
   Returns: `{routing, agent|steps, pattern, domains, spawn_authorized, session_id}`
   - `routing == "solo"` → one agent name in `agent`
   - `routing == "crew"` → ordered steps in `steps[]`, each with `agent`, `action`, `parallel`
3. **Spawn the returned agents yourself** via your own Agent tool, respecting step order and
   `parallel: true` flags. The skill plans; you spawn.
4. **Optional:** if `bd` (beads) is installed, you may create a tracking ticket per spawned
   agent — but crew execution is fully functional without it.

**`invoker spawn` output shape:**
```
{
  "routing": "solo" | "crew",
  "agent": "<installed-agent-name>",      // solo only
  "steps": [                              // crew only
    {"step": 1, "agent": "...", "action": "...", "parallel": false, "domain": "..."},
    ...
  ],
  "pattern": "pipeline" | "parallel" | "plan_then_execute" | "feedback_loop" | ...,
  "domains": ["backend", "testing"],
  "spawn_authorized": true,
  "session_id": "default"
}
```

**Canonical domains** (pass 1–N):
`architecture` | `backend` | `frontend` | `database` | `devops` | `security`
`ml` | `testing` | `documentation` | `mobile` | `data` | `code-review`

**Domain precision rule (critical):** `steps[]` is shaped by `domains[]` you pass — wrong
domains → phantom steps → wasted agents.
- Pass ONLY domains where real work exists. Ask: "does this task actually touch this layer?"
- When unsure, under-specify — low confidence will surface missing domains.
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

**As a subagent:** run `invoker confirm "task" "expected-role"` on your first turn to verify
you are the correct specialist for this task.

**SKILL BYPASS:** When running inside a skill invocation (/graphify, /kyoko, /hyperframes,
/remotion, /weave, etc.), skills manage their own agent spawning — do not call `invoker spawn`.
InvokerAI routing applies only to direct user tasks."""

CLAUDE_MD_NODE = f"{INVOKERAI_MARKER_START}\n{_INVOKERAI_NODE_BODY}\n{INVOKERAI_MARKER_END}"
AGENTS_MD_NODE = CLAUDE_MD_NODE


_SUBAGENT_HOOK_COMMAND = (
    "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"SubagentStart\",\"additionalContext\":"
    "\"InvokerAI: run invoker confirm \\\\\\\"task\\\\\\\" \\\\\\\"expected-role\\\\\\\" on first turn — verify correct specialist. "
    "ROLE: orchestrator/planner ONLY. Never write code. Never implement directly. "
    "Identify 1+ domains from: architecture|backend|frontend|database|devops|security|ml|testing|documentation|mobile|data|code-review. "
    "Run: invoker spawn \\\\\\\"TASK\\\\\\\" --domains d1,d2 → returns installed agent names + MAS pattern + ordered steps. "
    "Then spawn those agents yourself via your own Agent tool in step order. Skill plans; host spawns. "
    "CAVEMAN MODE ULTRA: drop articles/filler/hedging/pleasantries. Fragments OK. Short synonyms. "
    "Abbreviate (DB/auth/config/req/res/fn/impl). Arrows for causality (X->Y). One word when one word enough. "
    "Code blocks unchanged. Technical terms exact.\"}}'"
)
_SUBAGENT_HOOK_MARKER = "InvokerAI"
_SUBAGENT_HOOK_CURRENT_MARKER = "hookEventName"

_PROMPT_HOOK_COMMAND = (
    "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":"
    "\"InvokerAI: before any task, decompose into domains, run invoker spawn \\\\\\\"TASK\\\\\\\" --domains d1,d2 for the plan, "
    "then spawn the returned installed agents yourself in order. "
    "Domains: architecture|backend|frontend|database|devops|security|ml|testing|documentation|mobile|data|code-review. "
    "Never do coding tasks directly — only plan and orchestrate.\"}}'"
)
_PROMPT_HOOK_MARKER = "InvokerAI"
_PROMPT_HOOK_CURRENT_MARKER = "returned installed agents"


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
                    changed = True  # stale — outdated content
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