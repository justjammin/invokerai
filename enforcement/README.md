# InvokerAI Enforcement Gate

Canonical templates for the **enforcement gate** — a best-effort guardrail that keeps
the main thread in its orchestrator-only lane by blocking direct edits inside the active
project repo and nudging it to route specialist work through `/invokerai:decompose` →
`/invokerai:spawn`.

This is the **packaged copy**. Installing it is optional and is driven by
`/invokerai:setup` (see Step 5 in the setup skill). Nothing here runs until you wire it
into your `settings.json`.

---

## The model

**Two behaviors, deliberately asymmetric.**

1. **Edit-block (hard, but scoped).** A `PreToolUse` hook (`invoker-gate.js`) denies the
   main thread's `Edit` / `Write` / `MultiEdit` / `NotebookEdit` **only when the target
   file is inside the git repo the session is `cd`'d in** (`gate_cwd_repo_only`). Edits to
   anything else are free — other repos, `~/.claude`, `~/.cursor`, `~/.codex`, scratch
   dirs, `/tmp`. Path matching is boundary-safe (`/a/b` never matches `/a/bc`).

2. **Spawn-nudge (soft, never blocks).** Spawns (`Task` / `Agent`) are **never denied**.
   When the main thread spawns a specialist that is named in the agent map *without* a
   prior decompose marker, the gate emits a non-blocking `additionalContext` reminder and
   lets the spawn proceed.

**Bypasses (intended escapes):**

- **Exempt roots** — absolute-path prefixes listed in `~/.invoker/exempt-paths.json`
  (`exempt[].path`) are always free to edit.
- **Marker file** — a `.invoker-allow-direct` file in the target's directory (or any
  ancestor) frees that subtree.
- **Subagents** — any call carrying an `agent_id` (i.e. made *inside* a spawned subagent)
  always bypasses. Subagents are the legitimate workers.

**State.** `invoker-mark.js` is a `PostToolUse` + `SubagentStart` hook that maintains a
per-session token at `~/.invoker/state/<session_id>.token`
(`{decomposed, spawned, unlocked}`). A `SubagentStart` marks the session `spawned` +
`decomposed` so subagent edits flow even if a `PreToolUse` payload omits `agent_id`.

---

## Files

| File | Installs to | Purpose |
|------|-------------|---------|
| `invoker-gate.js` | `~/.claude/hooks/` | `PreToolUse` gate (edit-block + spawn-nudge) |
| `invoker-mark.js` | `~/.claude/hooks/` | `PostToolUse` + `SubagentStart` session-token writer |
| `gate-policy.json` | `~/.invoker/` | Policy: mode, exempt file/marker, agent map, gated tools |
| `exempt-paths.json` | `~/.invoker/` | Generic empty template — add your own exempt roots |
| `patch-settings.js` | (run in place) | Idempotently wires the three hooks into `settings.json` |

`gate-policy.json` is generic:

```json
{
  "mode": "always-block",
  "exempt_file": "~/.invoker/exempt-paths.json",
  "exempt_marker": ".invoker-allow-direct",
  "agent_map": "~/.invoker/agent-map.json",
  "gate_tools": ["Edit", "Write", "MultiEdit", "NotebookEdit", "Task", "Agent"],
  "gate_cwd_repo_only": true
}
```

`mode`: `always-block` (default — deny in-repo edits outright), `warn` (prompt to allow),
or `off` (kill switch, see below).

---

## settings.json wiring

The gate needs three hook groups. `patch-settings.js` adds them idempotently, or wire by
hand:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write|MultiEdit|NotebookEdit|Task|Agent",
        "hooks": [{ "type": "command", "command": "node \"/Users/you/.claude/hooks/invoker-gate.js\"" }] }
    ],
    "PostToolUse": [
      { "matcher": "Task|Agent|Skill",
        "hooks": [{ "type": "command", "command": "node \"/Users/you/.claude/hooks/invoker-mark.js\"" }] }
    ],
    "SubagentStart": [
      { "matcher": "",
        "hooks": [{ "type": "command", "command": "node \"/Users/you/.claude/hooks/invoker-mark.js\"" }] }
    ]
  }
}
```

(Use the absolute path to your hooks dir — replace `/Users/you` with your home. `patch-settings.js` fills this in for you.)

---

## Kill switch

Set `"mode": "off"` in `~/.invoker/gate-policy.json`. The policy is re-read on **every**
hook call — no restart needed. The gate immediately allows everything.

## Add exempt roots

Append to `exempt` in `~/.invoker/exempt-paths.json`:

```json
{ "version": 1, "exempt": [
  { "name": "my notes", "path": "/Users/me/notes", "reason": "I author these directly" }
] }
```

---

## Fail-open by design

Every hook wraps its body in a global try/catch and exits `0` on **any** error: missing
policy, unparseable stdin, unreadable agent map, detection failure. A bug in the gate can
never brick your tools — worst case it stops gating. It is a guardrail, not a security
boundary.

---

## Honest ceiling — what this does NOT stop

This gate is **best-effort, not unbypassable.** It only sees what flows through the gated
*editor* tools (`Edit`/`Write`/`MultiEdit`/`NotebookEdit`) on the main thread:

- **Bash / heredoc writes bypass it.** `cat > file`, `echo ... >`, `sed -i`, `tee`,
  `python -c "open(...).write(...)"`, `git apply`, etc. run under `Bash` and are not gated.
- **Out-of-editor runtimes bypass it.** Anything that writes files outside the matched
  tools — a build step, a generator script, an MCP server with its own write path.
- **Fail-open means a crash = no gate.** By design (see above).

So the gate is a *lane-keeper for the well-behaved path*, not a sandbox. It makes the
intended orchestrator-only workflow the path of least resistance; it does not make
direct edits impossible. If you need a hard boundary, use OS-level permissions, not this.
