# InvokerAI

Okay so. I got tired of watching AI agents spawn the wrong specialist and just wing it. So I built this.

InvokerAI is a local MCP server that acts as the routing brain for your agents. Before any agent gets spawned, InvokerAI intercepts it, classifies the task, and hands back the right specialist: role, system prompt fragment, and tool allowlist. Single call. No cloud, no API keys, no config file roulette.

One call. Right agent. Every time.   

<img width="200" height="200" alt="image" src="https://github.com/user-attachments/assets/abf5a9fb-8e45-486e-92a7-9dd8875eb91f" />

Extracted from [LENA](https://github.com/justjammin/lena), the AI orchestrator I've been running on Claude Code. After using this routing logic daily I figured it deserved its own thing.

---

## Install

### npm (Mac / Linux / Windows)

Requires Node 16+ and Python 3.9+.

```bash
npm install -g invokerai-mcp
```

First run creates `~/.invokerai/venv`, pip-installs `agent-invoker` into it, then starts the MCP server. Every run after that skips setup and just goes. No activation dance, no `source venv/bin/activate` every session. It finds its own Python.

Want to update the Python package without reinstalling the npm wrapper?

```bash
invoker-mcp --update
```

Done.

### Homebrew (Mac / Linux)

```bash
brew tap justjammin/invokerai
brew install invokerai
```

Fully isolated. Ships with its own virtualenv. Nothing touches your system Python.

### Direct install

```bash
git clone https://github.com/justjammin/invokerai
cd invokerai
python install.py
```

Or from PyPI if you prefer:

```bash
pip install agent-invoker
invoker setup
```

---

## Editor setup

Run this once after install. InvokerAI figures out which editors you have and writes the right MCP config for each:

```bash
invoker setup
```

That one command configures Claude Code, Cursor, Kiro, and GitHub Copilot. It also installs the enforcement hook script and injects a routing rule into your `~/.claude/CLAUDE.md`. You don't touch a single config file manually.

Migrating from v0.1.0? Run this instead:

```bash
python migrate.py
# or
invoker migrate
```

Purges the old echo hooks (real talk: Claude just ignored them anyway), rewrites your MCP entries to venv-first, and updates everything to the current enforcement model. Safe to run multiple times.

---

## The main call: `spawn_specialist`

Here's the part that got me. Instead of calling the `Agent` tool directly and hoping the AI picks the right specialist, you call `spawn_specialist` first. It routes the task and writes the spawn token that authorizes the next Agent call in one shot. The routing *is* the spawn action. Nothing to skip.

```
mcp__invokerai__spawn_specialist(task: "refactor the payment gateway to async/await")
```

And it comes back with everything you need:

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

That `spawn_authorized: true` is the signal. The PreToolUse hook sees it and lets the Agent call through. No token, no spawn. That's enforcement in one line.

For tasks that span multiple domains, you also get:

```json
"orchestrate_guidance": "Task spans multiple domains. Spawn multiple specialists sequentially. Use route_task for each sub-task to get the right role."
```

Orchestrate mode. Boom.

---

## Tool reference

### `spawn_specialist` — use this one

**Always call this instead of spawning an Agent directly.** Routes, authorizes, returns the full execution bundle. One call.

```
spawn_specialist(task: str, session_id?: str) → ExecutionBundle
```

Returns: `routing`, `role`, `confidence`, `tools[]`, `source`, `session_id`, `persona?`, `spawn_authorized: true`, `orchestrate_guidance?` (when `routing == "orchestrate"`)

---

### `route_task` — read-only classifier

No spawn token written. Use this when you want to know where a task would route without committing. Good for planning, sub-task routing inside an orchestrate flow, or debugging the classifier.

```
route_task(task: str, session_id?: str) → RoutingResult
```

Returns: `routing`, `role`, `confidence`, `tools[]`, `source`, `session_id`, `persona?`

Annotations: `readOnlyHint: true`, `idempotentHint: true`

---

### `confirm_route` — subagent self-check

Okay so this one's for the spawned agent itself. Call it on your first turn as a subagent to verify you're actually the right specialist for the job. If the classifier disagrees, it hands you the corrected persona and you adopt it. Self-correcting agents. That's pretty cool.

```
confirm_route(task: str, expected_role: str, session_id?: str) → ConfirmResult
```

Returns: `ok`, `expected_role`, `confirmed_role`, `confidence`, `session_id`, `corrected_persona?` (when `ok == false`)

---

### `list_agents` — who's on the roster

64 specialists. Browse them all, or filter by category.

```
list_agents(category?: str) → { agents: AgentSummary[] }
```

Returns: array of `{ id, category, description, orchestrate }`

---

## MCP resources and prompts

### Resources — `agent://` URI scheme

Every agent profile is available as a lazy-loadable MCP resource. `spawn_specialist` and `route_task` return a `resource_uri`. Call `resources/read` to pull the full profile when you need it. No upfront bulk load.

```
agent://backend-developer
agent://debugger
agent://react-specialist
...
```

### Prompt — `/route`

```
/route <task>
```

Shortcut that calls `mcp__invokerai__spawn_specialist` with the task. Works in any MCP-aware editor. Convenient.

---

## How enforcement actually works

No seriously. This part is worth understanding. The old version used echo hooks that Claude just... read and moved on from. Not anymore.

```
User submits prompt
        │
        ▼
UserPromptSubmit hook ─── injects routing reminder into context
        │
        ▼
Agent tool call attempted
        │
        ▼
PreToolUse[Agent] → ~/.invokerai/hooks/pre-agent.sh
        │
        ├── spawn_token exists + age < 30s?
        │         YES → consume token, exit 0 (Agent call goes through)
        │
        └── NO valid token
                  │
                  ├── CLI available? → pre-resolve route, inject into context
                  │
                  └── hookSpecificOutput: permissionDecision: deny
                            Agent call is blocked. Hard.
        │
        ▼
SubagentStart hook ──── reminds subagent to call confirm_route on first turn
```

`permissionDecision: deny` is a real platform block, not a polite suggestion. The Agent call doesn't happen. The only way through is `spawn_specialist` first.

**Kiro:** Same token pattern via `agentSpawn` + `userPromptSubmit` hooks.

**Cursor / GitHub Copilot:** No hook system. Enforcement via `spawn_specialist` inversion + CLAUDE.md blocking rule. The inversion pattern works because `spawn_specialist` is what agents *want* to call. It returns the execution bundle. There's nothing to skip.

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
invoker --model-info                             Show router phase, model, logged decisions

invoker setup                                    Configure MCP for all detected editors
invoker migrate                                  Upgrade v0.1.0 setup
invoker mcp                                      Start MCP server on stdio
invoker train                                    Build Phase 1 router from labeled examples
invoker train --phase 2                          Build Phase 2 router (needs 200+ log entries)

invoker tools add --all TOOL [TOOL...]           Add tools to all agents
invoker tools add --category NAME TOOL [TOOL...] Add tools to a category
invoker tools add --agents ID,ID TOOL [TOOL...]  Add tools to specific agents
invoker tools remove --all TOOL [TOOL...]        Remove tools
invoker tools list AGENT_ID                      List tools for an agent
```

Quick demo:

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

Right specialist, right tools, one call.

---

## The routing model

InvokerAI ships in two phases. Phase 1 works out of the box. Phase 2 gets better the more you use it.

| Phase | Model | What it needs |
|-------|-------|----------------|
| 1 (default) | TF-IDF + KNeighborsClassifier | Nothing. Ships working, no downloads |
| 2 | `all-mpnet-base-v2` + RandomForestClassifier | 200+ logged decisions + one ~420 MB download |

Every routing decision logs to `~/.invokerai/routing_log.jsonl`. Hit 200 and want the accuracy bump?

```bash
pip install agent-invoker[embeddings]
python scripts/build_router.py --phase 2
```

Downloads once to `~/.cache/huggingface/`, runs fully local after that. No API calls. The whole thing stays on your machine.

---

## Custom agents

64 agents in the default registry. Add your own. Custom agents override defaults on `id` collision:

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

## Migrating from v0.1.0

```bash
python migrate.py
```

What it does:
- Removes old `mcp__invokerai__route_task` echo hooks
- Installs `~/.invokerai/hooks/pre-agent.sh`
- Rewrites MCP entries to venv-first detection
- Updates CLAUDE.md to blocking-requirement language
- Adds Kiro hooks

Idempotent. Run it twice if you want.

---

## License

MIT — [Jamin Echols](https://github.com/justjammin)
