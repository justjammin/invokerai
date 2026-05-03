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

Migrating from v0.1.0? Run `invoker migrate` instead — it swaps out the old echo hooks (real talk: Claude just ignored them anyway), rewrites MCP entries, and patches your CLAUDE.md. Idempotent. Run it twice if you feel like it.

---

## What happens next

Nothing you have to do. That's the thing.

You type your task. Claude intercepts it, routes it, adopts the right persona, and gets to work — all before the first tool call. You just get a backend engineer when you need a backend engineer.

Here's what's happening under the hood when you type "refactor the payment gateway to async/await":

```
UserPromptSubmit hook fires
  → routing reminder injected into Claude's context

Claude runs: invoker spawn "refactor the payment gateway to async/await" --persona
  → backend-developer (91% confidence)
  → spawn token written
  → system_prompt_fragment loaded: "You are a senior backend engineer..."

Claude adopts the persona. Starts work.

If Claude tries to spawn a subagent:
  PreToolUse[Agent] hook fires
    → checks for valid spawn token (age < 30s)
    → token found? Agent call goes through.
    → no token? Agent call is blocked. Hard.
```

The JSON Claude actually sees:

```json
{
  "routing": "direct",
  "role": "backend-developer",
  "confidence": 91,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "spawn_authorized": true,
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "You are a senior backend engineer..."
  }
}
```

Want to see exactly what Claude gets? Run `invoker spawn "your task" --persona` in your terminal anytime.

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
{
  "pattern": "hierarchical",
  "steps": [
    { "step": 1, "role": "architect-reviewer",  "action": "Top-level decomposition",  "parallel": false },
    { "step": 2, "role": "frontend-developer",  "action": "Lead UI layer cluster",    "parallel": false },
    { "step": 3, "role": "backend-developer",   "action": "Lead API layer cluster",   "parallel": true  },
    { "step": 4, "role": "database-optimizer",  "action": "Lead data layer cluster",  "parallel": true  },
    { "step": 5, "role": "architect-reviewer",  "action": "Final integration review", "parallel": false }
  ],
  "domain_roles": [
    { "domain": "frontend", "role": "frontend-developer" },
    { "domain": "backend",  "role": "backend-developer"  },
    { "domain": "database", "role": "database-optimizer" },
    { "domain": "devops",   "role": "cloud-architect"    }
  ]
}
```

Right shape, right roles, right execution order. `parallel: true` flags what can fire simultaneously. Claude reads this and orchestrates from there.

---

## How enforcement actually works

This is worth understanding. The old version used echo hooks that Claude just... read and moved on from. Not anymore.

```
User submits prompt
        │
        ▼
UserPromptSubmit hook ─── injects routing reminder into context
        │
        ▼
Claude runs `invoker spawn "task" --persona` before doing anything
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
                        `invoker confirm "TASK" "ROLE"` on first turn
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

These are what Claude calls automatically via the installed hooks. Run them yourself to debug or see what Claude sees:

```
invoker spawn "task" --persona               Route + spawn token + system_prompt_fragment
invoker spawn "task"                         Route + spawn token (no persona blob)
invoker confirm "task" "expected-role"       Subagent self-check / self-correction
invoker decompose "task"                     MAS pattern + skeleton steps
invoker "task text"                          Route only (no token)
invoker --registry PATH "task text"          Use custom agent registry
invoker --no-log "task text"                 Skip logging
```

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

## Migrating from v0.1.0

```bash
python migrate.py
# or
invoker migrate
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
