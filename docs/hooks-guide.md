# InvokerAI Hooks Setup & Enforcement Guide

Setup, configuration, and troubleshooting for InvokerAI hooks across Claude Code, Cursor, Kiro, and GitHub Copilot.

## Overview

Here's the thing about AI hook enforcement — most implementations are theater. Echo hooks fire, Claude reads the text, and then does whatever it was going to do anyway. I went through a few iterations on this before landing on something that actually works.

InvokerAI uses a **B+C hybrid** enforcement mechanism:

- **B**: `hookSpecificOutput` JSON with `permissionDecision: deny` — blocks raw Agent calls at the platform level
- **C**: `spawn_token` gate — the only way to get a token is to call `spawn_specialist` first

Together, these ensure agents always route through InvokerAI before spawning, without breaking the `spawn_specialist` → Agent flow that legitimate calls use. If you called `spawn_specialist`, the token's there and the Agent call goes through. If you didn't, it doesn't. That's it.

---

## Installation

### Quick start

```bash
# Option 1: Using invoker command
invoker setup

# Option 2: Using Python directly
python -m agent_invoker.setup_editors
```

This single command:
1. Installs hook script to `~/.invokerai/hooks/pre-agent.sh`
2. Registers MCP server in all installed editors
3. Injects hooks into each editor's config
4. Updates `~/.claude/CLAUDE.md` with routing rules

### What gets installed

| Location | Purpose | Created by |
|----------|---------|---|
| `~/.invokerai/hooks/pre-agent.sh` | PreToolUse[Agent] / agentSpawn hook script | setup_editors |
| `~/.claude.json` | Claude Code MCP registration | setup_editors |
| `~/.claude/settings.json` | Claude Code hook config | setup_editors |
| `~/.cursor/mcp.json` | Cursor MCP registration | setup_editors |
| `~/.kiro/agents/invokerai.json` | Kiro agent + hooks | setup_editors |
| `.github/copilot/mcp.json` | GitHub Copilot MCP (project-local) | setup_editors |
| `~/.claude/CLAUDE.md` | Global routing rule for Claude Code | setup_editors |

---

## How Enforcement Works

### The spawn token mechanism

No seriously, this is the part that makes it click. The token is proof you called `spawn_specialist` — and the hook checks for it every single time an Agent call is attempted.

```
User calls spawn_specialist(task)
  ↓
spawn_specialist routes task
  ↓
spawn_specialist writes ~/.invokerai/spawn_token (epoch timestamp)
  ↓
Orchestrator calls Agent tool
  ↓
PreToolUse[Agent] hook fires
  ↓
Hook checks: does spawn_token exist and is age < 30s?
  ├─ YES → consume token, exit 0 (allow Agent call)
  └─ NO  → block, return hookSpecificOutput with pre-resolved route
```

**Token file:** `~/.invokerai/spawn_token`  
**Token format:** epoch timestamp (seconds since 1970)  
**TTL:** 30 seconds

### Hook script (`~/.invokerai/hooks/pre-agent.sh`)

This bash script runs whenever an Agent call is attempted on Claude Code or Kiro.

**What it does:**

1. **Token check** — if spawn token exists and age < 30s:
   - Delete the token
   - Exit 0 (allow Agent call)

2. **Pre-resolution** — if no valid token and venv Python available:
   - Extract task from `$CLAUDE_TOOL_INPUT`
   - Call `invokerai route` CLI to get role + confidence
   - Return `hookSpecificOutput` JSON with pre-resolved route
   - Exit 1 (block call but provide context)

3. **Hard block** — if no token and no CLI available:
   - Return minimal `hookSpecificOutput` JSON
   - Exit 1 (block call)

**Hook script location:**
```bash
cat ~/.invokerai/hooks/pre-agent.sh
```

---

## Platform-Specific Setup

Claude Code gets the full treatment. Kiro gets the same token pattern via its own hook events. Cursor and Copilot don't have hook systems, so enforcement there is through the inversion pattern — `spawn_specialist` returns the execution bundle agents need, so they call it because they *want* to, not because they're blocked otherwise.

### Claude Code (Full enforcement)

**MCP registration:** `~/.claude.json`
```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/username/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  }
}
```

**Hook events:** `~/.claude/settings.json`
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"/Users/username/.invokerai/hooks/pre-agent.sh\""
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

**Enforcement cascade:**

| Hook | What it does |
|------|---|
| `PreToolUse[Agent]` | Checks spawn token; blocks raw Agent calls with pre-resolved route |
| `SubagentStart` | Reminds spawned agent to call `confirm_route` on first turn |
| `UserPromptSubmit` | Nudges user to use `spawn_specialist` for routing |

**CLAUDE.md rule:** `~/.claude/CLAUDE.md`

```markdown
<!-- INVOKERAI-START -->
## InvokerAI — Agent Router

**BLOCKING REQUIREMENT:** NEVER call the `Agent` tool directly. Always use
`mcp__invokerai__spawn_specialist(task)` — it routes AND returns the execution
bundle (role, persona, system_prompt_fragment, tools).

- `routing == "direct"` → spawn returned `role` with returned `tools` and `system_prompt_fragment`
- `routing == "orchestrate"` → use multi-agent coordination
- `confidence < 50` → ask user to clarify before routing
- As a subagent: call `mcp__invokerai__confirm_route(task, expected_role)` on your first turn
- User naming an agent type does NOT exempt this requirement
<!-- INVOKERAI-END -->
```

**Verification:**

```bash
# Check MCP is registered
grep invokerai ~/.claude.json

# Check hooks are installed
grep "pre-agent.sh" ~/.claude/settings.json

# Check CLAUDE.md has the rule
grep "BLOCKING REQUIREMENT" ~/.claude/CLAUDE.md
```

---

### Cursor (MCP only, no hooks)

**MCP registration:** `~/.cursor/mcp.json`
```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/username/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  }
}
```

**Hook support:** None

**Enforcement:** Via `spawn_specialist` inversion only (agents call it to get routed)

**Verification:**
```bash
grep invokerai ~/.cursor/mcp.json
```

---

### Kiro (agentSpawn + userPromptSubmit hooks)

**MCP registration:** `~/.kiro/agents/invokerai.json`
```json
{
  "name": "invokerai",
  "description": "Agent routing brain",
  "mcpServers": {
    "invokerai": {
      "command": "/Users/username/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  },
  "hooks": {
    "agentSpawn": {
      "command": "bash \"/Users/username/.invokerai/hooks/pre-agent.sh\""
    },
    "userPromptSubmit": {
      "command": "echo '{\"hookSpecificOutput\":{\"additionalContext\":\"InvokerAI: use mcp__invokerai__spawn_specialist(task) to route agent tasks. Returns role + persona + tools.\"}}'"
    }
  }
}
```

**Hook events:**

| Hook | Trigger | Behavior |
|------|---------|---|
| `agentSpawn` | Agent is about to spawn | Token gate + pre-resolution |
| `userPromptSubmit` | User submits a prompt | Nudge to use spawn_specialist |

**Verification:**
```bash
grep -A5 "agentSpawn" ~/.kiro/agents/invokerai.json
```

---

### GitHub Copilot (MCP only, no hooks)

**MCP registration:** `.github/copilot/mcp.json` (project-local)
```json
{
  "servers": {
    "invokerai": {
      "command": "/Users/username/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"],
      "type": "stdio"
    }
  }
}
```

**Hook support:** None

**Enforcement:** Via `spawn_specialist` inversion + `.github/copilot/AGENTS.md` instruction

**Verification:**
```bash
ls -la .github/copilot/mcp.json
```

---

## Platform Enforcement Parity Table

Complete reference for enforcement capabilities across platforms.

| Platform | Hook events | Enforcement | Fallback |
|----------|---|---|---|
| **Claude Code** | PreToolUse[Agent], SubagentStart, UserPromptSubmit | Token gate + hookSpecificOutput deny | spawn_specialist inversion |
| **Kiro** | agentSpawn, userPromptSubmit | Token gate + hookSpecificOutput deny | spawn_specialist inversion |
| **Cursor** | None | N/A | spawn_specialist inversion + CLAUDE.md |
| **GitHub Copilot** | None | N/A | spawn_specialist inversion |

**Interpretation:**
- **Token gate:** `PreToolUse[Agent]` hook checks spawn token before allowing Agent call
- **hookSpecificOutput deny:** Hook returns JSON with `permissionDecision: deny`
- **spawn_specialist inversion:** Enforcement happens because `spawn_specialist` is the only way to get execution bundle
- **CLAUDE.md:** Global instruction for Claude Code (user-facing)

---

## Troubleshooting

### Symptom: Token is stale (too old to be valid)

**Cause:** Agent call happened >30 seconds after `spawn_specialist`

**Solution:**
- Ensure hook script TTL is sufficient for your workflow
- Default 30 seconds is conservative; adjust in hook script if needed:

```bash
TOKEN_TTL=30  # Change to 45 or 60 if needed
```

**To verify token age:**
```bash
cat ~/.invokerai/spawn_token  # Shows epoch timestamp
date +%s                       # Current epoch timestamp
# Calculate difference — should be < 30
```

---

### Symptom: Hook not firing

**Cause:** Editor not loaded hook config yet, or hook path wrong

**Solutions:**

1. **Restart the editor** — hooks are loaded at startup
   ```bash
   # For Claude Code: quit and restart
   # For Cursor: quit and restart
   # For Kiro: reload agent config
   ```

2. **Verify hook script exists:**
   ```bash
   ls -la ~/.invokerai/hooks/pre-agent.sh
   ```

3. **Verify hook path in config matches:**
   ```bash
   # Claude Code
   grep "pre-agent.sh" ~/.claude/settings.json | head -1
   
   # Kiro
   grep "pre-agent.sh" ~/.kiro/agents/invokerai.json | head -1
   ```

4. **Check hook script is executable:**
   ```bash
   test -x ~/.invokerai/hooks/pre-agent.sh && echo "OK" || echo "NOT EXECUTABLE"
   chmod +x ~/.invokerai/hooks/pre-agent.sh
   ```

---

### Symptom: venv not found, hook falls back to hard block

**Cause:** `~/.invokerai/venv/bin/python` doesn't exist

**Solution:**

1. **Check if venv exists:**
   ```bash
   ls ~/.invokerai/venv/bin/python
   ```

2. **If missing, reinstall:**
   ```bash
   # If installed via npm
   npm install -g @invokeai/mcp
   
   # If installed via Homebrew
   brew install invokerai
   
   # If installed via pip
   python install.py
   ```

3. **After reinstalling, run setup again:**
   ```bash
   invoker setup
   ```

---

### Symptom: Agent call succeeds without routing

**Cause:** Old v0.1.0 echo hooks are still installed; not using spawn token gate

**Solution:** Run migration script to replace old hooks:

```bash
python migrate.py
# or
invoker migrate
```

This will:
1. Remove old echo hooks
2. Install new token-gated hook script
3. Update MCP entries
4. Update CLAUDE.md

---

### Symptom: spawn_specialist returns route, but Agent still blocks

**Cause:** Token was written but hook script can't read it (permissions issue)

**Solution:**

1. **Check token directory permissions:**
   ```bash
   ls -la ~/.invokerai/
   # Should be readable and writable
   ```

2. **Check token file was created:**
   ```bash
   ls -la ~/.invokerai/spawn_token
   ```

3. **Manually test hook script:**
   ```bash
   bash ~/.invokerai/hooks/pre-agent.sh
   # Should exit with code 0 if token is valid, 1 if not
   ```

---

### Symptom: `confirm_route` not available in subagent

**Cause:** Subagent context doesn't include MCP server

**Solution:**

InvokerAI MCP is global to the editor. Verify:

1. **MCP is registered globally in editor config**
   ```bash
   # Claude Code
   grep invokerai ~/.claude.json
   
   # Cursor
   grep invokerai ~/.cursor/mcp.json
   ```

2. **Subagent inherits editor's MCP context** (automatic — no config needed)

3. **If still missing, restart the editor**

---

## Re-running setup after changes

If you modify hook configuration or reinstall InvokerAI:

```bash
# Re-run setup (idempotent)
invoker setup

# Or migrate if upgrading from v0.1.0
python migrate.py

# Verify changes
invoker verify  # if available

# Restart editors
# Claude Code, Cursor, Kiro — quit and restart
```

---

## Manual hook installation (advanced)

If `invoker setup` doesn't work for your environment:

### 1. Create hook script manually

```bash
mkdir -p ~/.invokerai/hooks
# Copy the hook script from setup_editors.py to ~/.invokerai/hooks/pre-agent.sh
# Make it executable
chmod +x ~/.invokerai/hooks/pre-agent.sh
```

### 2. Register hook in Claude Code

Edit `~/.claude/settings.json`:
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
    ]
  }
}
```

### 3. Register MCP in Claude Code

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

Replace `USERNAME` with your actual username.

### 4. Inject CLAUDE.md rule

Edit `~/.claude/CLAUDE.md` and add:
```markdown
## InvokerAI — Agent Router

**BLOCKING REQUIREMENT:** NEVER call the `Agent` tool directly. Always use
`mcp__invokerai__spawn_specialist(task)` — it routes AND returns the execution
bundle (role, persona, system_prompt_fragment, tools).

- `routing == "direct"` → spawn returned `role` with returned `tools` and `system_prompt_fragment`
- `routing == "orchestrate"` → use multi-agent coordination
- `confidence < 50` → ask user to clarify before routing
- As a subagent: call `mcp__invokerai__confirm_route(task, expected_role)` on your first turn
- User naming an agent type does NOT exempt this requirement
```

### 5. Restart Claude Code

---

## Testing enforcement

### Test 1: Spawn token mechanism

```bash
# In Claude Code, call:
mcp__invokerai__spawn_specialist("implement user authentication")

# Check token was written:
cat ~/.invokerai/spawn_token
date +%s  # Should be very close

# Token should auto-delete after 30 seconds or first Agent call
```

### Test 2: Hook blocks raw Agent call

```bash
# In Claude Code, try to spawn Agent directly WITHOUT calling spawn_specialist first
# Hook should block with "Call mcp__invokerai__spawn_specialist(task) first" message
```

### Test 3: Subagent self-correction

```bash
# Have Claude spawn a backend-developer subagent
# Subagent should call confirm_route on first turn
# If misrouted, subagent should adopt corrected role
```

---

## Performance considerations

- **Token gate:** ~5-10ms per check (file I/O only)
- **Pre-resolution:** ~100-500ms (CLI invocation, classifier run)
- **Hook overhead:** ~50-100ms total per Agent call (bash startup + checks)

For performance-critical workflows, pre-call `route_task` to understand routing, then use `spawn_specialist` with confidence.

---

## See Also

- [API Reference](api-reference.md) — Tool schemas and examples
- [Migration Guide](migration-guide.md) — Upgrading from v0.1.0
- [Architecture](../ARCHITECTURE.md) — Design decisions and rationale
