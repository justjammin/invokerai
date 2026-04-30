# InvokerAI Hook Enforcement — Research Notes

## Problem

The `PreToolUse` hook on `Agent` fires correctly and injects a required message into context, but Claude ignores it and spawns agents directly — especially when the user names an agent type explicitly. Hook presence ≠ hook compliance. Behavioral gap.

---

## Current Hook Config (`~/.claude/settings.json`)

### PreToolUse — Agent (blocking reminder)
```json
{
  "matcher": "Agent",
  "hooks": [
    {
      "type": "command",
      "command": "echo '[InvokerAI] REQUIRED: call mcp__invokerai__route_task before spawning this agent.'"
    }
  ]
}
```

### SubagentStart (secondary reminder)
```json
{
  "hooks": [
    {
      "type": "command",
      "command": "echo '[InvokerAI] call mcp__invokerai__route_task(task) to confirm correct specialist.'"
    }
  ]
}
```

### UserPromptSubmit (per-message reminder)
```json
{
  "hooks": [
    {
      "type": "command",
      "command": "echo '[InvokerAI] Route agent tasks: mcp__invokerai__route_task(task) → routing/role/tools.'"
    }
  ]
}
```

**All three fire correctly. Config is not the issue.**

---

## Why Compliance Fails

- Hook output is an `echo` string injected as a system reminder
- Claude sees it, processes the next action, proceeds anyway
- When user names an agent explicitly (e.g. "use fullstack-developer"), Claude treats that as sufficient and skips routing
- `echo` hooks cannot block — they inject context but don't gate the tool call

---

## Option A — Stronger Echo Message (No Config Change)

Change the `PreToolUse` message from informational to instruction format with explicit consequence:

```json
"command": "echo 'BLOCKING: DO NOT call Agent tool yet. You MUST call mcp__invokerai__route_task(task) first and use the returned role + tools. Skipping this is a protocol violation.'"
```

**Tradeoff:** Still just an echo. Better wording, same enforcement gap.

---

## Option B — Hook as Actual MCP Command (Your Idea)

Replace the `echo` with a real `mcp__invokerai__route_task` call that runs in the hook itself and injects the routing decision into context. Claude would see the already-resolved route rather than a reminder to call it.

**Constraint:** Claude Code hooks are shell commands only — they cannot call MCP tools natively. You'd need a wrapper:

```bash
# invokerai-pre-agent.sh
# Calls invokerai CLI and surfaces the result
invokerai route "$CLAUDE_TOOL_INPUT_TASK" 2>/dev/null \
  && echo "{\"hookSpecificOutput\": {\"routing\": \"$(invokerai route \"$CLAUDE_TOOL_INPUT_TASK\" | jq -r .routing)\", \"role\": \"$(invokerai route \"$CLAUDE_TOOL_INPUT_TASK\" | jq -r .role)\"}}"
```

Then in settings:
```json
{
  "matcher": "Agent",
  "hooks": [
    {
      "type": "command",
      "command": "bash ~/.claude/hooks/invokerai-pre-agent.sh"
    }
  ]
}
```

**Requires:** InvokerAI CLI accessible from shell path. Check with `which invokerai` or `invokerai --version`.

**Tradeoff:** If the CLI exists and is fast, this is the strongest option — Claude gets a pre-resolved routing decision injected as structured JSON, not just a string reminder.

---

## Option C — `hookSpecificOutput` Structured Injection

Claude Code hooks support returning `hookSpecificOutput` as structured JSON that gets injected into context as a system block. This is more authoritative than an echo string.

```bash
echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "InvokerAI: You MUST call mcp__invokerai__route_task before this Agent spawn. routing==direct → spawn returned role. routing==orchestrate → multi-agent. confidence<50 → ask user first."}}'
```

The `hookSpecificOutput` format is treated differently than a plain echo — it renders as a structured system reminder rather than raw stdout text.

**Tradeoff:** No actual routing decision, but more authoritative than echo. Zero additional dependencies.

---

## Option D — Non-Zero Exit to Hard Block

A hook that exits non-zero will **block the tool call entirely**. Could be used to gate Agent spawning behind a condition — e.g., require a flag file or env var set by a prior `mcp__invokerai__route_task` call.

```bash
# Block all Agent spawns unconditionally (extreme)
exit 1

# Or: block unless a routing token exists from this turn
[ -f /tmp/invokerai-routed-$$  ] || exit 1
```

**Tradeoff:** Unconditional block breaks everything. Conditional block requires coordinating state between the routing call and the spawn, which is complex with hook-only tooling. Not recommended without a clean token mechanism.

---

## Recommended Path

| Priority | Action |
|---|---|
| 1 | Switch `PreToolUse` echo to `hookSpecificOutput` JSON format (Option C) — immediate improvement, no deps |
| 2 | Check if `invokerai` CLI is callable from shell — if yes, implement Option B |
| 3 | Update `CLAUDE.md` rule: `"NEVER call Agent tool without first calling mcp__invokerai__route_task. Non-negotiable."` |

---

## CLAUDE.md Rule (Strengthened)

Current:
> Before spawning any agent, call `mcp__invokerai__route_task` to get the optimal specialist.

Proposed:
> **BLOCKING REQUIREMENT:** NEVER call the `Agent` tool without first calling `mcp__invokerai__route_task(task)`. This is non-negotiable — not a suggestion. `routing=="direct"` → spawn the `role` agent with returned `tools`. `routing=="orchestrate"` → use multi-agent. `confidence < 50` → ask user to clarify before routing. User naming an agent type does not exempt this requirement.

---

## Open Questions

- Does `invokerai` have a CLI binary callable from shell hooks? (`which invokerai`)
- Is `$CLAUDE_TOOL_INPUT_TASK` or equivalent env var exposed to `PreToolUse` hooks? (Would allow passing the task description to the routing call automatically)
- Is blocking via non-zero exit acceptable for Agent spawns, or would it break too many workflows?