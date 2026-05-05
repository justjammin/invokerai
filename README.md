<p align="center">
  <img alt="InvokerAI" src="docs/invokerAI-mark.svg" width="200" />
</p>

# InvokerAI

Okay so. I got tired of watching AI agents spawn the wrong specialist and just wing it. So I built this.

InvokerAI is a local routing brain that wires into your AI editors. Install it, run one setup command, and from that point every agent task gets classified and routed to the right specialist before Claude touches anything. Role, prompt fragment, tool allowlist — all resolved. You keep working. InvokerAI keeps the agents honest.

No cloud. No API keys. No config file roulette. Runs entirely on your machine.

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

Or from PyPI:

```bash
pip install agent-invoker
invoker setup
```

---

## One command. Then you're done.

After install, run this once:

```bash
invoker setup
```

InvokerAI scans what you have installed and wires everything up:

- **Claude Code** — MCP server registered, PreToolUse / SubagentStart / UserPromptSubmit hooks installed, routing rule injected into `~/.claude/CLAUDE.md`
- **Cursor** — MCP server registered in `~/.cursor/mcp.json`
- **Kiro** — MCP + `agentSpawn` / `userPromptSubmit` hooks in `~/.kiro/agents/invokerai.json`
- **GitHub Copilot** — MCP server registered in `.github/copilot/mcp.json`

No config file to edit. No hook to write. Restart your editor. Routing is live.

---

## What happens next

Nothing you have to do. That's the thing.

You type your task. Claude identifies the relevant domains, calls `mcp__invokerai__spawn_specialist`, and hands execution to the right specialist — all before any code gets written. You just get a backend engineer when you need one.

For "refactor the payment gateway to async/await", InvokerAI returns the specialist with that context. There's also a gate that ensures no Agent call bypasses routing.

---

## Multi-agent tasks

When a task spans multiple domains, InvokerAI hands Claude a structured decomposition instead of free-text guidance. Six patterns — detected from the task text, no config required:

| Pattern | When | Structure |
|---|---|---|
| `pipeline` | Sequential domains, default | Ordered steps, each a different specialist |
| `parallel` | "simultaneously", "concurrently" | Steps marked `parallel: true`, integration at end |
| `supervisor` | "manage", "coordinate", "oversee agents" | Planner → workers → reviewer |
| `feedback_loop` | "review and revise", "iterate until" | Generator → critic → revise (3-step loop) |
| `plan_then_execute` | "design first then", "plan then build" | Architect step first, execution follows |
| `hierarchical` | Full-stack + enterprise/platform keywords | Top supervisor → domain leads → integration |

Curious what Claude gets handed for a complex task? Peek at it:

```bash
invoker decompose "build the react frontend, implement the api, migrate postgres, deploy to k8s"
```

```json
  "domain_roles": [
    { "domain": "frontend", "role": "frontend-developer" },
    { "domain": "backend",  "role": "backend-developer"  },
    { "domain": "database", "role": "database-optimizer" },
    { "domain": "devops",   "role": "cloud-architect"    }
  ]
```

Right shape, right roles, right execution order. `parallel: true` flags what can fire simultaneously. Claude reads this and orchestrates from there.

---

## How enforcement actually works

This is worth understanding. This is where the fun starts.

```
User submits prompt
        │
        ▼
UserPromptSubmit hook ─── injects routing reminder into context
        │
        ▼
Claude calls `mcp__invokerai__spawn_specialist(task, domains=[...])` before doing anything
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
SubagentStart hook ──── spawned agent runs:
                        `mcp__invokerai__confirm_route(task, expected_role)` on first turn
                        Self-corrects if the classifier disagrees.
```

`permissionDecision: deny` is a real platform block. The Agent call doesn't happen. There's no workaround — which is the whole point.

**Kiro:** Same token pattern via `agentSpawn` + `userPromptSubmit` hooks.

**Cursor / GitHub Copilot:** No hook system. Enforcement via CLAUDE.md blocking rule. InvokerAI is what agents *want* to call — it returns the execution bundle. There's nothing to skip.

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

### Setup and management

Commands you run directly:

```
invoker setup                                Configure MCP + hooks for all detected editors
invoker migrate                              Upgrade v0.1.0 setup
invoker uninstall                            Remove all InvokerAI config
invoker uninstall --purge                    Also delete ~/.invokerai/ (venv, logs, tokens)
invoker --model-info                         Show router phase + status
invoker mcp                                  Start MCP server on stdio (editors handle this)
invoker train                                Build Phase 1 router from labeled examples
invoker train --phase 2                      Build Phase 2 router (needs 200+ log entries)

invoker tools add --all TOOL [TOOL...]           Add tools to all agents
invoker tools add --category NAME TOOL [TOOL...] Add to a category
invoker tools add --agents ID,ID TOOL [TOOL...]  Add to specific agents
invoker tools remove --all TOOL [TOOL...]         Remove tools
invoker tools list AGENT_ID                       List tools for an agent
```

### Routing commands

These are for debugging — see exactly what the router returns:

```
invoker "task text"                          Route only (no token)
invoker --registry PATH "task text"          Use custom agent registry
invoker --no-log "task text"                 Skip logging
invoker decompose "task"                     MAS pattern + skeleton steps
```

Primary surface for Agent/MCP: `mcp__invokerai__spawn_specialist(task, domains=[...])`

---

## The routing model

InvokerAI ships in two phases. Phase 1 works out of the box. Phase 2 gets smarter the more you use it.

| Phase | Model | What it needs |
|-------|-------|----------------|
| 1 (default) | TF-IDF + KNeighborsClassifier | Nothing. Ships working, no downloads |
| 2 | `all-mpnet-base-v2` + RandomForestClassifier | 200+ logged decisions + one ~420 MB download |

Every routing decision logs to `~/.invokerai/routing_log.jsonl`. Hit 200 entries and want the accuracy bump?

```bash
pip install agent-invoker[embeddings]
python scripts/build_router.py --phase 2
```

Downloads once to `~/.cache/huggingface/`, runs fully local after that. No API calls. Everything stays on your machine.

---

## Custom agents

64 agents in the default registry. Add your own — custom agents override defaults on `id` collision:

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

## License

MIT — [Jamin Echols](https://github.com/justjammin)
