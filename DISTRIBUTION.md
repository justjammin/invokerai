# InvokerAI Distribution Guide

Three distribution channels. `invoker setup` detects which one you used and writes
the correct MCP config automatically — you never need to edit it by hand.

## How setup detects your install

`invoker setup` runs `_mcp_entry()` in this priority order:

| Priority | Install method | Config written |
|----------|---------------|----------------|
| 1 | **Managed venv** (`~/.invokerai/venv/bin/python`) | `{"command": "~/.invokerai/venv/bin/python", "args": ["-m", "agent_invoker.mcp_server"]}` — always stable, always has `agent_invoker`, immune to PATH/version issues |
| 2 | **Homebrew** | `{"command": "/opt/homebrew/bin/invoker-mcp"}` — absolute path, immune to PATH changes |
| 3 | **npm** (nvm / fnm / volta / system) | `{"command": "/absolute/path/to/invoker-mcp"}` — searched across all node version managers |
| 4 | **sys.executable fallback** | `{"command": "/path/to/python", "args": ["-m", "agent_invoker.mcp_server"]}` — last resort; prints a warning if `~/.invokerai/venv` is missing |

> **Why venv-first matters:** All three install channels (npm, Homebrew, install.py) write
> to `~/.invokerai/venv`. This venv always has `agent_invoker` installed and is immune to
> nvm version switches, Homebrew Python isolation, and PATH differences between your shell
> and the editor's launch environment. Checking it first eliminates silent MCP failures.

> **Note for existing installs:** If you installed v0.1.0 before this detection order was
> in place, run `python migrate.py` or `invoker migrate` to rewrite your editor configs to
> the correct venv entry point.

---

## Supported editors

| Editor | MCP | Hooks | Config file |
|--------|-----|-------|-------------|
| Claude Code | Yes | PreToolUse, SubagentStart, UserPromptSubmit | `~/.claude.json`, `~/.claude/settings.json` |
| Cursor | Yes | None | `~/.cursor/mcp.json` |
| Kiro | Yes | agentSpawn, userPromptSubmit | `~/.kiro/agents/invokerai.json` |
| GitHub Copilot | Yes | None | `.github/copilot/mcp.json` |

---

## Channel 1 — npm (Mac / Linux / Windows)

**Package:** `invokerai-mcp` on npmjs.com  
**Source:** `npm/` directory  

The npm package is a thin Node.js launcher. On first run it:
1. Finds Python 3.9+ on the host
2. Creates `~/.invokerai/venv`
3. `pip install agent-invoker` from PyPI into that venv
4. Execs `~/.invokerai/venv/bin/python -m agent_invoker.mcp_server` (stdio passes through)

Subsequent runs skip setup and exec immediately.

### Prerequisites

- Node.js 16+
- Python 3.9+

### User install

```bash
npm install -g invokerai-mcp
```

### Update agent-invoker without reinstalling npm package

```bash
invoker-mcp --update
```

### Publish to npm

```bash
# 1. Bump version in npm/package.json to match agent-invoker version
# 2. From repo root:
cd npm
npm publish --access public
```

> **Important:** Publish `agent-invoker` to PyPI first (see below).  
> The npm launcher pulls it from PyPI on first run.

---

## Channel 2 — Homebrew tap (Mac / Linux)

**Tap:** `brew tap justjammin/invokerai`  
**Formula:** `homebrew/Formula/invokerai.rb`  
**Source:** `homebrew/` directory  

Homebrew installs a fully isolated Python virtualenv + all deps.  
No system Python, no venv setup on first run — install is complete immediately.

### User install

```bash
brew tap justjammin/invokerai
brew install invokerai
```

### Publish steps

#### Step 1 — publish agent-invoker to PyPI

```bash
# In repo root
pip install build twine
python -m build
twine upload dist/*
```

This gives you a PyPI URL like:
```
https://files.pythonhosted.org/packages/source/a/agent-invoker/agent_invoker-0.2.0.tar.gz
```

#### Step 2 — get sha256 + resource hashes

```bash
# Creates a skeleton formula with real sha256
brew create https://files.pythonhosted.org/packages/source/a/agent-invoker/agent_invoker-0.2.0.tar.gz

# Generates resource blocks with sha256 for all dependencies
brew update-python-resources invokerai --print-only
```

#### Step 3 — update formula

Replace `PLACEHOLDER` values in `homebrew/Formula/invokerai.rb` with real URLs + sha256 hashes.

#### Step 4 — create the tap repo

```bash
# Homebrew taps must live in a repo named homebrew-<tapname>
# Create: github.com/justjammin/homebrew-invokerai
# Copy formula there:
mkdir -p ~/homebrew-invokerai/Formula
cp homebrew/Formula/invokerai.rb ~/homebrew-invokerai/Formula/
cd ~/homebrew-invokerai
git init && git add . && git commit -m "add invokerai formula"
git remote add origin git@github.com:justjammin/homebrew-invokerai.git
git push -u origin main
```

#### Step 5 — test the tap

```bash
brew tap justjammin/invokerai
brew install invokerai
brew test invokerai
```

---

## Channel 3 — Direct install (pip / source)

```bash
git clone https://github.com/justjammin/invokerai
cd invokerai
python install.py
```

Or from PyPI once published:

```bash
pip install agent-invoker
invoker setup
```

---

## Version sync

Keep versions in sync across all three places before any publish:

| File | Field |
|------|-------|
| `pyproject.toml` | `version` |
| `npm/package.json` | `version` |
| `homebrew/Formula/invokerai.rb` | `url` (version in filename) |

---

## Local dev MCP config

While iterating locally, point directly at the venv Python:

```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/you/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/invokerai"
      }
    }
  }
}
```

Or install editable into the venv:

```bash
python3 -m venv ~/.invokerai/venv
~/.invokerai/venv/bin/pip install -e /path/to/invokerai
```

Then MCP config (no PYTHONPATH needed):

```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/you/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  }
}
```

# InvokerAI

InvokerAI is a local MCP server that acts as the routing brain for AI agents. When any agent is about to be spawned, InvokerAI intercepts it, classifies the task, and returns the right specialist — including role, system prompt fragment, and tool allowlist — in a single call. No cloud, no API keys, no configuration beyond initial setup.

Extracted from [LENA](https://github.com/justjammin/lena), the AI orchestrator for Claude Code.

---

## Install

### npm (Mac / Linux / Windows)

Requires Node 16+ and Python 3.9+.

```bash
npm install -g invokerai-mcp
```

On first run the launcher creates `~/.invokerai/venv`, pip-installs `agent-invoker` from PyPI into it, then starts the MCP server. Subsequent runs skip setup and exec immediately.

Update the Python package without reinstalling the npm wrapper:

```bash
invoker-mcp --update
```

### Homebrew (Mac / Linux)

```bash
brew tap justjammin/invokerai
brew install invokerai
```

Fully isolated — ships its own Python virtualenv. No system Python changes.

### Direct install

```bash
git clone https://github.com/justjammin/invokerai
cd invokerai
python install.py
```

Or from PyPI:

```bash
pip install agent-invoker
invoker setup
```

---

## Editor setup

Run this once after any install method. InvokerAI auto-detects which editors are installed and writes the correct MCP config for each:

```bash
invoker setup
```

Configures: **Claude Code**, **Cursor**, **Kiro**, **GitHub Copilot**.

- Installs `~/.invokerai/hooks/pre-agent.sh`
- Writes MCP entry to each editor's config file
- Injects an `InvokerAI` node into `~/.claude/CLAUDE.md` (Claude Code only)

**Migrating from v0.1.0?** Run the migration script instead:

```bash
python migrate.py
# or
invoker migrate
```

This purges old echo hooks, rewrites MCP entries to venv-first, and updates the CLAUDE.md node to blocking-requirement language.

---

## First use: `spawn_specialist`

`spawn_specialist` is the primary entry point. Call it instead of the `Agent` tool directly — it routes the task **and** writes the spawn token that authorizes the next Agent call. The routing is the spawn action.

```
mcp__invokerai__spawn_specialist(task: "refactor the payment gateway to async/await")
```

Response:

```json
{
  "routing": "direct",
  "role": "backend-developer",
  "confidence": 91,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "source": "ml-phase1",
  "session_id": "default",
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "You are a senior backend engineer..."
  },
  "spawn_authorized": true
}
```

Use the returned `role`, `system_prompt_fragment`, and `tools` when you spawn the agent. The `spawn_authorized: true` flag means the PreToolUse hook will allow the subsequent Agent call.

For orchestrate tasks (multi-domain), `spawn_specialist` also returns:

```json
"orchestrate_guidance": "Task spans multiple domains. Spawn multiple specialists sequentially. Use route_task for each sub-task to get the right role."
```

---

## Tool reference

### `spawn_specialist`

**Primary surface.** Routes a task, writes a spawn token, and returns the full execution bundle in one call. Always call this instead of spawning an Agent directly.

```
spawn_specialist(task: str, session_id?: str) → ExecutionBundle
```

**Returns:** `routing`, `role`, `confidence`, `tools[]`, `source`, `session_id`, `persona?`, `spawn_authorized: true`, `orchestrate_guidance?` (when `routing == "orchestrate"`)

---

### `route_task`

Read-only classifier. Returns routing and persona bundle without writing a spawn token. Use this for planning or sub-task routing inside an orchestrate flow.

```
route_task(task: str, session_id?: str) → RoutingResult
```

**Returns:** `routing`, `role`, `confidence`, `tools[]`, `source`, `session_id`, `persona?`

Annotations: `readOnlyHint: true`, `idempotentHint: true`

---

### `confirm_route`

Subagent self-correction. Call this on your first turn as a subagent to verify you are the right specialist for the task. If the confirmed role differs from your expected role, adopt the corrected role.

```
confirm_route(task: str, expected_role: str, session_id?: str) → ConfirmResult
```

**Returns:** `ok`, `expected_role`, `confirmed_role`, `confidence`, `session_id`, `corrected_persona?` (when `ok == false`)

---

### `list_agents`

Discover available specialists. Optionally filter by category.

```
list_agents(category?: str) → { agents: AgentSummary[] }
```

**Returns:** array of `{ id, category, description, orchestrate }`

---

## MCP resources and prompts

**Resources — `agent://` URI scheme**

Every agent profile is available as a lazy-loadable MCP resource. `spawn_specialist` and `route_task` return a `resource_uri`; call `resources/read` to load the full profile.

```
agent://backend-developer
agent://debugger
agent://react-specialist
...
```

**Prompt — `/route`**

```
/route <task>
```

Shortcut that calls `mcp__invokerai__spawn_specialist` with the supplied task. Available in any MCP-aware editor.

---

## Hook enforcement

InvokerAI installs three Claude Code hooks and enforces agent routing at the platform level.

```
User prompt submitted
        │
        ▼
UserPromptSubmit hook ──── injects routing reminder into prompt context
        │
        ▼
Agent tool call attempted
        │
        ▼
PreToolUse[Agent] → ~/.invokerai/hooks/pre-agent.sh
        │
        ├── spawn_token exists + age < 30s?
        │         YES → consume token, exit 0 (Agent call allowed)
        │
        └── NO valid token
                  │
                  ├── venv CLI available?
                  │         YES → pre-resolve route, inject into context
                  │
                  └── hookSpecificOutput: permissionDecision: deny
                            Agent call blocked
        │
        ▼
SubagentStart hook ──────── reminds subagent to call confirm_route on first turn
```

**Kiro:** same token pattern via `agentSpawn` + `userPromptSubmit` hooks in `~/.kiro/agents/invokerai.json`.

**Cursor / GitHub Copilot:** no hook system. Enforcement via `spawn_specialist` inversion + CLAUDE.md blocking rule only.

---

## Supported editors

| Editor | MCP | Hooks | Config file |
|--------|-----|-------|-------------|
| Claude Code | Yes | PreToolUse, SubagentStart, UserPromptSubmit | `~/.claude.json`, `~/.claude/settings.json` |
| Cursor | Yes | None | `~/.cursor/mcp.json` |
| Kiro | Yes | agentSpawn, userPromptSubmit | `~/.kiro/agents/invokerai.json` |
| GitHub Copilot | Yes | None | `.github/copilot/mcp.json` |

---

## CLI reference

```
invoker "task text"                              Route a task, print JSON result
invoker --registry PATH "task text"              Use custom agent registry
invoker --no-log "task text"                     Skip logging this decision
invoker --model-info                             Show router phase, model, logged decision count

invoker setup                                    Configure MCP for all detected editors
invoker migrate                                  Upgrade v0.1.0 setup (purge old hooks, rewrite entries)
invoker mcp                                      Start MCP server on stdio

invoker tools add --all TOOL [TOOL...]           Add tools to all agents
invoker tools add --category NAME TOOL [TOOL...] Add tools to all agents in a category
invoker tools add --agents ID,ID TOOL [TOOL...]  Add tools to specific agents
invoker tools remove --all TOOL [TOOL...]        Remove tools from all agents
invoker tools list AGENT_ID                      List tools for one agent
```

Example:

```bash
invoker "add dark mode to the settings panel"
```

```json
{
  "routing": "direct",
  "role": "frontend-developer",
  "confidence": 88,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "source": "ml-phase1"
}
```

---

## Routing model

InvokerAI ships in two phases:

| Phase | Model | Requires |
|-------|-------|----------|
| 1 (default) | TF-IDF + KNeighborsClassifier | Nothing — works immediately after install |
| 2 | `all-mpnet-base-v2` + RandomForestClassifier | ~200 logged decisions + one download (~420 MB) |

Every routing decision is logged to `~/.invokerai/routing_log.jsonl`. When you accumulate 200 decisions and want the accuracy boost:

```bash
pip install agent-invoker[embeddings]
python scripts/build_router.py --phase 2
```

The model downloads once to `~/.cache/huggingface/` and runs fully locally after that.

---

## Custom agents

InvokerAI ships with 64 curated agents. Custom agents override defaults on `id` collision:

```bash
invoker --registry ./my-agents.json "task text"
invoker --registry ./agents/ "task text"        # loads every *.json in the directory
```

Registry format:

```json
{
  "version": "1.0",
  "agents": [
    {
      "id": "my-agent",
      "category": "backend",
      "description": "Does X for Y",
      "domains": ["backend"],
      "triggers": ["keyword1", "keyword2"],
      "tools": ["Read", "Write", "Bash"],
      "orchestrate": false
    }
  ]
}
```

---

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design rationale: tool inversion pattern, hook enforcement spec, MCP entry detection order, session ledger, and persona bundle format.

---

## Migration from v0.1.0

```bash
python migrate.py
```

What it does:

- Removes old `mcp__invokerai__route_task` echo hooks
- Installs `~/.invokerai/hooks/pre-agent.sh` (spawn-token gate)
- Rewrites MCP entries in Claude Code, Cursor, and Kiro to venv-first detection
- Updates CLAUDE.md node to blocking-requirement language
- Adds Kiro `agentSpawn` and `userPromptSubmit` hooks

Safe to run multiple times — idempotent.

---

## License

MIT — [Jamin Echols](https://github.com/justjammin)
