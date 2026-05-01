# InvokerAI — Architecture

## Vision

InvokerAI is the routing brain for AI agents. Every agent spawn on any supported platform passes through it, gets classified, and receives the correct specialist role, persona, and tool set — automatically, without user intervention.

**Key shift from current state:** Stop trying to *enforce* a prerequisite call. Instead, make `spawn_specialist(task)` the tool agents *want* to call — it does routing + persona resolution atomically. No second step to skip.

---

## Problems Addressed

| # | Problem | Source |
|---|---------|--------|
| P1 | Hook echoes fire but Claude ignores them — enforcement is theater | HOOK-ENFORCEMENT-RESEARCH.md |
| P2 | `sys.executable` fallback in `_mcp_entry()` captures wrong Python → MCP fails silently | mcp-developer review |
| P3 | `route_task` returns role name only — no persona, no system prompt, no context | architect review |
| P4 | Stateless routing loses thread context across multi-turn conversations | architect review |
| P5 | stdio MCP = single process per client — no path to team/org deployment | architect review |
| P6 | Resources, Prompts, tool annotations unused — biggest MCP surface missed | mcp-developer review |
| P7 | Cross-platform hook parity impossible — Copilot has no hooks | architect review |

---

## Architecture

### Layer 0 — MCP Entry (venv fix)

**Bug:** `_mcp_entry()` uses `sys.executable` as fallback #4. When `setup_editors` runs from system Python (e.g., Homebrew `post_install`), this captures the wrong interpreter. `agent_invoker` isn't importable there and the MCP entry silently fails.

**Fix — detection order rewrite:**

```
1. ~/.invokerai/venv/bin/python   ← check first, always stable, always has agent_invoker
2. Homebrew absolute binary       ← /opt/homebrew/bin/invoker-mcp
3. npm absolute binary            ← searched across nvm/fnm/volta/system
4. sys.executable                 ← only if venv doesn't exist yet, print warning
```

Drop `invoker-mcp` on PATH entirely — PATH at MCP server launch ≠ PATH at setup time.

**Result:** every editor's MCP config always points to `~/.invokerai/venv/bin/python -m agent_invoker.mcp_server`. No user activation required, ever.

---

### Layer 1 — Tool Suite

Replace single `route_task` with a minimal four-tool surface:

| Tool | Purpose | Stateless? |
|------|---------|-----------|
| `route_task(task, session_id?)` | Pure classifier → routing + persona bundle | Yes (ledger opt-in) |
| `spawn_specialist(task, session_id?)` | Route + return execution-ready bundle. **Primary surface.** | Yes |
| `list_agents(category?)` | Discover available specialists | Yes |
| `get_session_context(session_id)` | Multi-turn coherence — what persona is active | No |

`spawn_specialist` is the inversion pattern: agents call it to get the specialist *and* spawn context back. Nothing to skip — the routing is the action.

Skip `get_persona` (fold into `route_task` payload) and `confirm_spawn` (over-engineering).

#### Tool annotations

Add to `route_task` and `list_agents`:
```json
"annotations": {
  "readOnlyHint": true,
  "idempotentHint": true
}
```
Marks routing as a safe lookup — enables client-side caching, safer re-calls.

---

### Layer 2 — Persona Bundle

`route_task` and `spawn_specialist` return a **persona bundle**, not just a role name:

```json
{
  "routing": "direct",
  "role": "backend-developer",
  "confidence": 87,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "You are a senior backend engineer...",
    "tool_allowlist": ["Read", "Write", "Edit", "Bash", "Grep"],
    "tool_denylist": [],
    "context_hints": ["Read src/api/ before touching routes"],
    "handoff_protocol": "escalate to architect-reviewer if schema changes needed"
  },
  "decision_rationale": "task contains API + server keywords, confidence 87",
  "session_id": "ses_abc123"
}
```

`system_prompt_fragment` is load-bearing. Must be:
- Self-contained (200–500 tokens)
- Role-specific, not generic "you are an expert"
- Composable with host system prompt
- Versioned as artifacts, not hardcoded strings

#### MCP Resources (biggest miss)

Expose every agent profile as a resource:

```
agent://backend-developer
agent://debugger
agent://react-specialist
...
```

`route_task` returns `resource_uri`. Client calls `resources/read` to lazy-load full persona. Keeps routing fast, persona decoupled from classifier payload.

---

### Layer 3 — Hook Enforcement

Hooks remain belt-and-suspenders. Primary enforcement is the tool inversion in Layer 1. Hooks handle residual cases where agents bypass `spawn_specialist`.

#### Claude Code hooks (B+C hybrid)

Replace echo strings with `hookSpecificOutput` JSON that includes **both** a context block and a permission denial:

```json
{
  "hookSpecificOutput": {
    "additionalContext": "InvokerAI: call mcp__invokerai__spawn_specialist(task) — returns correct role, persona, and tools. Raw Agent spawn blocked.",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Route through mcp__invokerai__spawn_specialist first."
  }
}
```

`permissionDecision: "deny"` gates the Agent tool call. Structured JSON is more authoritative than plain echo. No unconditional `exit 1` — that breaks orchestrate-mode multi-agent flows.

If `invokerai` CLI is callable from shell:

```bash
# PreToolUse[Agent] hook
TASK=$(echo "$CLAUDE_TOOL_INPUT" | jq -r '.description // .task // ""')
ROUTE=$(invokerai route "$TASK" 2>/dev/null)
echo "{\"hookSpecificOutput\": {\"additionalContext\": \"Route resolved: $ROUTE\", \"permissionDecision\": \"deny\", \"permissionDecisionReason\": \"Use spawn_specialist — route already resolved above.\"}}"
```

This pre-resolves the route and injects the decision — Claude sees the answer, not a reminder.

#### SubagentStart + `confirm_route` tool

Hooks cannot call MCP tools. But spawned subagents inherit the MCP server. Pattern:

1. `SubagentStart` hook injects: `"You MUST call mcp__invokerai__confirm_route(task, expected_role) as your first action."`
2. Subagent calls `confirm_route(task, expected_role)` → returns `{ok, corrected_role, tools}`
3. If `ok == false`, subagent adopts `corrected_role` instead

Add `confirm_route` as a fifth tool. Misrouted subagents self-correct without orchestrator intervention.

#### CLAUDE.md rule (strengthened)

```markdown
**BLOCKING REQUIREMENT:** NEVER call the `Agent` tool directly.
Always use `mcp__invokerai__spawn_specialist(task)` — it routes AND returns the execution bundle.
User naming an agent type does not exempt this. `routing=="orchestrate"` → multi-agent.
`confidence < 50` → ask user to clarify. Non-negotiable.
```

---

### Layer 4 — Session Ledger

Stateless calls per turn, optional stateful side-channel:

- Each `route_task`/`spawn_specialist` accepts optional `session_id`
- Server maintains in-memory ledger: `{session_id: {active_role, prior_routes[], conversation_turn}}`
- `get_session_context(session_id)` returns current persona state
- Ledger TTL: 30 min idle expiry, no persistence (keep server simple)
- `session_id` generated by client (Claude passes its session ID), not server

Enables: "re-route only if task type changed" logic, handoff chain audit, mid-conversation persona stability.

---

### Layer 5 — MCP Prompts

Expose `/route` as a registered MCP prompt so users can invoke routing manually:

```json
{
  "name": "route",
  "description": "Route a task to the optimal specialist",
  "arguments": [{"name": "task", "required": true}]
}
```

Users type `/route fix the auth bug` in any MCP-aware editor — no need to know the tool name.

---

## Cross-Platform Enforcement Ladder

| Platform | Hook capability | Primary enforcement | Fallback |
|----------|----------------|--------------------|---------|
| Claude Code | Full (PreToolUse, SubagentStart, UserPromptSubmit) | `permissionDecision: deny` on raw Agent calls | `spawn_specialist` inversion |
| Kiro | `agentSpawn`, `userPromptSubmit` | `agentSpawn` hook → deny + context | `spawn_specialist` inversion |
| Cursor | MCP only, no hooks | `spawn_specialist` inversion + AGENTS.md | `list_agents` discovery |
| GitHub Copilot | No hooks | `spawn_specialist` as only spawn surface | AGENTS.md injection |

Copilot: no hooks → rely on value-add. `spawn_specialist` returns project-specific tool list and context hints Copilot wouldn't have otherwise. Carrot, not stick.

---

## Distribution Changes Required

### All channels — MCP entry fix

`_mcp_entry()` must check `~/.invokerai/venv/bin/python` first. All three install paths (npm, brew, install.py) write to this venv — it's always the right target.

### npm

After `setupVenv()` installs, run `agent_invoker.setup_editors` (already done). Venv python path is `~/.invokerai/venv/bin/python` — this must be what gets written to editor configs, not `sys.executable` from the node process.

### Homebrew

`post_install` already calls `setup_editors`. Brew's `libexec/bin/python` is isolated — write that absolute path to configs. Do not use `sys.executable`.

### install.py

Already calls `_setup_editors()`. Same fix: ensure written MCP entry points to `~/.invokerai/venv/bin/python`.

---

## Roadmap (priority order)

| Priority | Change | Impact |
|----------|--------|--------|
| P0 | Fix `_mcp_entry()` venv detection order | Eliminates silent MCP failures |
| P0 | Switch hooks to `hookSpecificOutput` + `permissionDecision: deny` | Real enforcement, not theater |
| P1 | Add `spawn_specialist` tool | Inversion pattern — enforcement dissolves |
| P1 | Add `confirm_route` tool | Subagent self-correction |
| P1 | Add `system_prompt_fragment` to route payload | Actual persona switching |
| P2 | Expose agent profiles as MCP resources | Persona lazy-load, protocol-correct |
| P2 | Add session ledger | Multi-turn persona coherence |
| P2 | Register `/route` MCP prompt | User-facing discoverability |
| P3 | HTTP/SSE transport option | Team/org deployment |
| P3 | Classifier behind HTTP boundary | Central persona updates, no client redeploy |
| P3 | Telemetry — `report_route_outcome` | Classifier tuning feedback loop |

---

## Final Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Persona source | Authored per-agent in `agents/*.md` body (after frontmatter) | Full control, versioned with agents, composable |
| Hard blocking | Yes — all raw Agent spawns blocked via token mechanism | User confirmed OK; token mechanism prevents breaking `spawn_specialist`→Agent flow |
| Platform priority | Full hook parity preferred; MCP registration alone acceptable where hooks unavailable | Cursor/Kiro get hooks where the platform supports them |
| Session ID | Zero-config — defaults to `"default"` session if none supplied, opt-in per-call | No wiring required; multi-tenant can pass explicit IDs |
| Hook enforcement | **B+C hybrid with token gate** | See Layer 3 for full spec |

### Hook Enforcement — Final Spec (B+C Hybrid + Token Gate)

**Problem with unconditional blocking:** If PreToolUse blocks all Agent calls, `spawn_specialist` → Agent also breaks.

**Solution: spawn token.** `spawn_specialist` writes `~/.invokerai/spawn_token` (epoch timestamp). Hook checks for it:

```
PreToolUse[Agent] fires
  ├─ token exists + age < 30s → consume token, exit 0 (allow)
  └─ no valid token:
       ├─ if venv python + CLI available → pre-resolve route (Option B)
       └─ always → hookSpecificOutput JSON + exit 1 (block)
```

Hook script lives at `~/.invokerai/hooks/pre-agent.sh`, installed by `setup_editors`. Idempotent on re-run.

**Kiro** uses same token pattern via `agentSpawn` hook (same script).

**Cursor / Copilot** — no hook system. Enforcement via `spawn_specialist` inversion + CLAUDE.md blocking rule only.

### CLAUDE.md Node — Final Text

```markdown
**BLOCKING REQUIREMENT:** NEVER call the `Agent` tool directly. Always use
`mcp__invokerai__spawn_specialist(task)` — it routes AND returns the execution
bundle (role, persona, system_prompt_fragment, tools).

- `routing == "direct"` → spawn returned `role` with returned `tools` and `system_prompt_fragment`
- `routing == "orchestrate"` → use multi-agent coordination
- `confidence < 50` → ask user to clarify before routing
- As a subagent: call `mcp__invokerai__confirm_route(task, expected_role)` on your first turn
- User naming an agent type does NOT exempt this requirement
```
