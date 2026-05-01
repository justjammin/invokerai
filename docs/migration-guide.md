# InvokerAI v0.1.0 → v0.2.0 Migration Guide

Okay so — v0.2.0 is a real architecture change, not a patch bump. The old version had echo hooks that Claude politely ignored and a single `route_task` tool that returned a role name and nothing else. This version has actual enforcement, a spawn token gate, four tools, and a persona bundle that actually changes agent behavior.

The migration script handles everything. But here's what changed and why, so you know what it's doing.

## What Changed

### New features in v0.2.0

| Feature | v0.1.0 | v0.2.0 | Impact |
|---------|--------|--------|--------|
| Tool suite | Single `route_task` | Four tools (`spawn_specialist`, `route_task`, `confirm_route`, `list_agents`) | Clearer API surface, routing + authorization in one call |
| Hook mechanism | Echo strings | `hookSpecificOutput` JSON + spawn token gate | Real enforcement, not theater |
| Persona data | Role name only | Full bundle (fragment + resource URI) | System prompt injection, tool selection |
| MCP resources | None | `agent://role` resources | Lazy-load full agent profiles |
| Session ledger | None | In-memory multi-turn context | Persona coherence across turns |
| Spawn authorization | None | Spawn token mechanism | Hard gating of raw Agent calls |

### Breaking changes

- `route_task` response shape changed (now includes `persona` bundle)
- Old echo hooks are replaced with `hookSpecificOutput` + token gate
- `CLAUDE.md` rule strengthened to "BLOCKING REQUIREMENT"
- Hook script location changed to `~/.invokerai/hooks/pre-agent.sh`

### Non-breaking (compatible)

- `route_task` still works as a read-only classifier
- `spawn_specialist` is a new primary surface (not a replacement, an addition)
- Session ID is optional (defaults to "default")
- Custom registry path still supported

---

## Pre-migration checklist

Before you run anything — back up your configs. The migration script is idempotent but there's no reason not to have a fallback.

```bash
# 1. Check current version
invoker --version
# Should show 0.1.0

# 2. Verify Claude Code / Cursor is installed
ls ~/.claude.json    # Claude Code
ls ~/.cursor/mcp.json  # Cursor

# 3. Back up your current config (optional but recommended)
cp ~/.claude.json ~/.claude.json.backup.pre-v0.2
cp ~/.claude/settings.json ~/.claude/settings.json.backup.pre-v0.2
cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.backup.pre-v0.2
```

---

## Migration Steps

Trust me on this — just run the automated path below. The manual steps are here if something goes wrong, but the script handles it in one shot.

### Step 1: Update InvokerAI package

Choose one based on how you installed:

**Via npm:**
```bash
npm install -g @invokeai/mcp
```

**Via Homebrew:**
```bash
brew upgrade invokerai
```

**Via pip:**
```bash
# If you have install.py from v0.1.0
python install.py --upgrade
```

Verify installation:
```bash
invoker --version
# Should show 0.2.0

python -m agent_invoker.mcp_server --version
# Should show 0.2.0
```

### Step 2: Run migration script

**Automated migration (recommended):**

```bash
python migrate.py
# or
invoker migrate
```

One command, seven things fixed. Here's what it does:

1. ✓ Install new hook script to `~/.invokerai/hooks/pre-agent.sh`
2. ✓ Purge old v0.1.0 echo hooks from all editor configs
3. ✓ Update MCP entries to use new `_mcp_entry()` detection order
4. ✓ Inject new `hookSpecificOutput` + token gate hooks
5. ✓ Update `~/.claude/CLAUDE.md` with new blocking requirement
6. ✓ Update Kiro agent config (agentSpawn + userPromptSubmit)
7. ✓ Update Cursor MCP entry

**Output (example):**
```
InvokerAI migration — upgrading existing setup...

  Hook script: installed → /Users/username/.invokerai/hooks/pre-agent.sh

  Claude Code: MCP entry updated → /Users/username/.invokerai/venv/bin/python
  Claude Code: removed 3 old echo hook(s)
  Claude Code: hooks migrated → ~/.claude/settings.json

  Cursor: MCP entry updated → /Users/username/.invokerai/venv/bin/python

  Kiro: MCP entry updated → /Users/username/.invokerai/venv/bin/python
  Kiro: agentSpawn hook updated
  Kiro: userPromptSubmit hook updated

  CLAUDE.md: node updated → ~/.claude/CLAUDE.md

Migration complete.
Restart Claude Code / Cursor / Kiro to pick up changes.

New tool surface:
  mcp__invokerai__spawn_specialist(task)       ← primary, use this
  mcp__invokerai__route_task(task)             ← read-only classifier
  mcp__invokerai__confirm_route(task, role)    ← subagent self-correction
  mcp__invokerai__list_agents()                ← discovery
```

### Step 3: Restart editors

This one people skip and then wonder why nothing changed. Close and reopen everything:

```bash
# Claude Code: Quit and restart from Applications
# Cursor: Quit and restart
# Kiro: Reload agent config or restart
```

### Step 4: Verify migration

Test the new tools in your editor:

**Tool availability:**
- [ ] `mcp__invokerai__spawn_specialist` visible in tool list
- [ ] `mcp__invokerai__route_task` visible in tool list
- [ ] `mcp__invokerai__confirm_route` visible in tool list
- [ ] `mcp__invokerai__list_agents` visible in tool list

**Test spawn_specialist:**
```
User: Call spawn_specialist with task: "fix the login bug in the auth module"
Claude: Returns routing, role, confidence, tools, persona
```

**Test confirm_route:**
```
User: Spawn a backend-developer subagent to implement a feature
Subagent (turn 1): Calls confirm_route(task, "backend-developer")
Subagent: Receives ok=true and proceeds
```

**Test hook enforcement:**
```
User: Try to call Agent directly without spawn_specialist first
Claude Code: Hook blocks with "Call mcp__invokerai__spawn_specialist(task) first"
```

**Check CLAUDE.md:**
```bash
grep "BLOCKING REQUIREMENT" ~/.claude/CLAUDE.md
# Should output the new rule
```

---

## Manual migration (if script fails)

If `python migrate.py` doesn't work — it shouldn't fail but here's the manual path if it does:

### 1. Install hook script

```bash
mkdir -p ~/.invokerai/hooks

# Copy the hook script from the InvokerAI source:
# agent_invoker/setup_editors.py → _HOOK_SCRIPT variable

cat > ~/.invokerai/hooks/pre-agent.sh << 'EOF'
#!/bin/bash
# InvokerAI PreToolUse[Agent] hook — B+C hybrid with spawn token gate
VENV_PY="$HOME/.invokerai/venv/bin/python"
TOKEN="$HOME/.invokerai/spawn_token"
TOKEN_TTL=30

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
EOF

chmod +x ~/.invokerai/hooks/pre-agent.sh
```

### 2. Update Claude Code MCP entry

Edit `~/.claude.json`:
```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/USERNAME/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  }
}
```

Replace `USERNAME` with your username.

### 3. Purge old hooks and inject new ones

Edit `~/.claude/settings.json`. Remove entries containing:
- `mcp__invokerai__route_task`
- `REQUIRED: call mcp__invokerai`
- `confirm correct specialist`

Then add the new hook structure:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"/Users/USERNAME/.invokerai/hooks/pre-agent.sh\""
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"additionalContext\":\"InvokerAI: call mcp__invokerai__confirm_route(task, expected_role) on your first turn to verify correct specialist.\"}}'"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"additionalContext\":\"InvokerAI: use mcp__invokerai__spawn_specialist(task) to route agent tasks. Returns role + persona + tools.\"}}'"
          }
        ]
      }
    ]
  }
}
```

### 4. Update Cursor MCP entry

Edit `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/USERNAME/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  }
}
```

### 5. Update Kiro agent config

Edit `~/.kiro/agents/invokerai.json`:
```json
{
  "name": "invokerai",
  "description": "Agent routing brain — route tasks to optimal specialist via MCP",
  "mcpServers": {
    "invokerai": {
      "command": "/Users/USERNAME/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  },
  "hooks": {
    "agentSpawn": {
      "command": "bash \"/Users/USERNAME/.invokerai/hooks/pre-agent.sh\""
    },
    "userPromptSubmit": {
      "command": "echo '{\"hookSpecificOutput\":{\"additionalContext\":\"InvokerAI: use mcp__invokerai__spawn_specialist(task) to route agent tasks. Returns role + persona + tools.\"}}'"
    }
  }
}
```

### 6. Update CLAUDE.md

Edit `~/.claude/CLAUDE.md`. Find the section between:
```markdown
<!-- INVOKERAI-START -->
...
<!-- INVOKERAI-END -->
```

Replace it with:
```markdown
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
<!-- INVOKERAI-END -->
```

---

## Verifying successful migration

### Check all files were updated

```bash
# 1. Hook script installed
ls -la ~/.invokerai/hooks/pre-agent.sh
# Should exist and be executable (755)

# 2. MCP entries updated (venv path)
grep "\.invokerai/venv" ~/.claude.json
grep "\.invokerai/venv" ~/.cursor/mcp.json

# 3. Hooks use new format
grep "hookSpecificOutput" ~/.claude/settings.json
grep "pre-agent.sh" ~/.claude/settings.json

# 4. CLAUDE.md updated
grep "BLOCKING REQUIREMENT" ~/.claude/CLAUDE.md

# 5. Kiro config updated
grep "pre-agent.sh" ~/.kiro/agents/invokerai.json
```

### Run integration test

In Claude Code, test the new tool surface:

```javascript
// Test 1: spawn_specialist works
const result1 = await mcp__invokerai__spawn_specialist(
  "implement user authentication with JWT"
);
console.log(result1.role);  // Should be a specialist role
console.log(result1.spawn_authorized);  // Should be true

// Test 2: route_task works
const result2 = await mcp__invokerai__route_task(
  "debug the database connection timeout"
);
console.log(result2.role);  // Should be a specialist role
console.log(result2.spawn_authorized);  // Should be undefined (read-only)

// Test 3: list_agents works
const result3 = await mcp__invokerai__list_agents();
console.log(result3.agents.length > 0);  // Should be true

// Test 4: confirm_route works
const result4 = await mcp__invokerai__confirm_route(
  "implement REST API",
  "backend-developer"
);
console.log(result4.ok);  // Should be true or false
```

All four tools should be available and return valid responses.

---

## Rollback (if needed)

If you need to revert to v0.1.0:

```bash
# 1. Restore from backup
cp ~/.claude.json.backup.pre-v0.2 ~/.claude.json
cp ~/.claude/settings.json.backup.pre-v0.2 ~/.claude/settings.json
cp ~/.claude/CLAUDE.md.backup.pre-v0.2 ~/.claude/CLAUDE.md

# 2. Downgrade InvokerAI
npm install -g @invokeai/mcp@0.1.0
# or
brew install invokerai@0.1.0

# 3. Restart editors
```

---

## Troubleshooting migration

### Issue: `python migrate.py` says "command not found"

**Solution:** Make sure you're in the InvokerAI repo directory:
```bash
cd /path/to/invokerai
python migrate.py
```

Or use the invoker CLI:
```bash
invoker migrate
```

### Issue: Hook script installation fails

**Solution:** Check permissions on `~/.invokerai/`:
```bash
ls -la ~/.invokerai/
# Should be writable (755 or 700)
chmod 755 ~/.invokerai
mkdir -p ~/.invokerai/hooks
chmod 755 ~/.invokerai/hooks
```

Then re-run migration.

### Issue: Old hooks still active after migration

**Solution:** Restart the editor completely:
```bash
# For Claude Code: Cmd+Q to quit, then reopen
# For Cursor: Cmd+Q to quit, then reopen
```

Editors cache hook configurations at startup.

### Issue: MCP entry points to wrong Python

**Solution:** Verify `_mcp_entry()` is using the new detection order:
```bash
# Should be ~/.invokerai/venv/bin/python
grep command ~/.claude.json | grep invokerai

# If it's something else, re-run setup
invoker setup
```

### Issue: Token gate is blocking legitimate calls

**Solution:** Increase TTL in hook script:
```bash
# Edit ~/.invokerai/hooks/pre-agent.sh
TOKEN_TTL=45  # Change from 30 to 45 or 60
```

Then restart editors.

---

## What to expect after migration

### New behavior

1. **`spawn_specialist` is now primary** — use this for all task routing
2. **Hook enforcement is real** — raw Agent calls are blocked, not just warned
3. **Personas are available** — returned with routing, usable for system prompt injection
4. **Subagents self-correct** — via `confirm_route` on first turn
5. **Sessions track routing** — optional, for multi-turn coherence

### Backwards compatibility

- Old `route_task` calls still work (read-only)
- Custom registry paths still supported
- Session ID is optional
- CLAUDE.md rule is stronger but compatible with existing workflows

---

## Migration support

If you get stuck:

1. Check [Hooks Setup Guide](hooks-guide.md) for enforcement details
2. Check [API Reference](api-reference.md) for tool schemas
3. Review [Architecture](../ARCHITECTURE.md) for design rationale
4. Run `invoker verify` to diagnose setup issues (if available)

---

## Timeline: v0.1.0 → v0.2.0

| Phase | What | Time |
|-------|------|------|
| **Prep** | Back up config, check versions | 2 min |
| **Update** | Run migration script or manual steps | 5-10 min |
| **Verify** | Restart editors, test tools | 5 min |
| **Deploy** | Commit updated config to project | 1 min |
| **Total** | | ~13-18 min |

---

## Next steps

After successful migration:

1. **Update project documentation** — mention new `spawn_specialist` primary surface
2. **Test routing** — try a few tasks to verify classifier still works
3. **Enable multi-turn workflows** — use `session_id` for persona coherence
4. **Load agent profiles** — use `resources/read` to get full persona details
5. **Monitor logs** — check `~/.invokerai/routing_log.jsonl` for routing decisions

---

## See Also

- [API Reference](api-reference.md) — Complete tool reference
- [Hooks Guide](hooks-guide.md) — Enforcement details
- [Architecture](../ARCHITECTURE.md) — Design decisions
