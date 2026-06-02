<p align="center">
  <img alt="InvokerAI" src="docs/invokerAI-mark.svg" width="200" />
</p>

# InvokerAI

**InvokerAI is the conductor that enforces route-first discipline.** It sits between your task and your coding agent — Claude Code, Cursor, Kiro, or Copilot — and routes work to the right specialist context instead of letting your agent YOLO everything in one generic context window.

Drop a real task: "refactor the payment gateway, add the Stripe webhook, and migrate the orders table to Postgres 16." Without routing, your agent thrashes between backend, database, and infrastructure all at once. Output works. Doesn't feel great.

With InvokerAI, you get a backend specialist for the gateway work, a database specialist for the migration, and a cloud engineer for the infrastructure. Each one gets only the context they need. Cleaner reasoning. Fewer hallucinations. Actual specialist work instead of generalist noise.

**How it actually works:**

- **Local ML router** — TF-IDF + KNN by default (zero downloads, ships ready). Upgrades to bge-large embeddings + RandomForest once you hit 200 logged decisions. All local. No API keys. No cloud calls. Auditable via `invoker why "task"`.
- **Three-tier persona composition** — role selection walks domain rules → subdomain patterns → framework specifics, collapsing into one prompt fragment capped at 6000 tokens. A FastAPI task pulls all three tiers. A generic backend task pulls one or two. Tighter match, deeper context.
- **Hard-block enforcement on Claude Code / Kiro** — PreToolUse + SubagentStart hooks gate the Agent call behind a spawn token issued by the router. No valid token, the call is denied at the platform layer. Real block, not advisory. Cursor / GitHub Copilot use soft enforcement via CLAUDE.md guidance (no hooks available), but routing is still active and agents that follow the protocol get routed correctly.
- **Private, observable infrastructure** — Routing happens on your machine. Your decisions log to `~/.invokerai/routing_log.jsonl`. Confidence gating (70+ spawns clean, 50–69 shows runners-up, below 50 refuses). Phase 2 retraining uses only your own data. No telemetry. No external calls.

84 specialist personas in the default registry. Custom registries override on collision. Confidence gates the spawn: high confidence ships clean, low confidence returns candidates and asks for clarification before anything runs.

No cloud. No API keys. No config file editing. Runs entirely on your machine.

Extracted from [LENA](https://github.com/justjammin/lena), the AI orchestrator I've been running on Claude Code. After using this routing logic daily it deserved its own thing.

---

## Install

Requires Python 3.10+. Check yours first if anything fails:

```bash
python --version
```

```bash
git clone https://github.com/justjammin/invokerai
cd invokerai
python install.py
```

The installer creates a venv at `~/.invokerai/venv`. Activate it so the `invoker` command is on your PATH:

```bash
source ~/.invokerai/venv/bin/activate
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

You type your task. Your agent identifies the relevant domains, calls `mcp__invokerai__spawn_specialist`, and hands execution to the right specialist. All before any code gets written. You just get a backend engineer when you need one.

For "refactor the payment gateway to async/await", InvokerAI returns the specialist with that context. The confidence-aware gate handles everything below 70: warning at 50-69, ask the user to clarify below 50.

---

## What spawn_specialist actually does

No seriously: when Claude calls `mcp__invokerai__spawn_specialist(task, domains=[...])`, it isn't getting a label back. It's getting a fully constructed specialist identity.

Here's what fires under the hood:

```
spawn_specialist("build a FastAPI endpoint with Pydantic validation", domains=["backend"])
        │
        ▼
1. Router scores the task — deterministic signals first (sentence shape, imperative verbs, domain
   hits, file refs) + keyword triggers pick the role → "backend-developer", confidence = 87.
   On low-confidence tasks (< 70) an optional local ML classifier runs as a tie-breaker and is
   adopted only when it beats the heuristic. (Phase 1: TF-IDF + KNN, zero downloads.)
        │
        ▼
2. Tier-tree walk — _load_persona("backend-developer")
        │
        ├── agents/backend.md          ← Tier 1: universal backend rules
        │   HTTP verbs, status codes, RBAC, structured logging, connection pooling...
        │
        ├── agents/backend/python.md   ← Tier 2: Python-specific patterns
        │   Type hints, Pydantic v2, asyncio, dependency injection...
        │
        └── agents/backend/python/fastapi.md  ← Tier 3: FastAPI deep specialist
            Routers, Depends(), background tasks, OpenAPI conventions...
        │
        ▼
3. Fragments composed → system_prompt_fragment (capped 6000 tok)
        │
        ▼
4. Bundle returned:
   {
     role: "backend-developer",
     confidence: 87,
     routing: "solo",
     tools: ["Read", "Write", "Edit", "Bash", ...],
     persona: {
       resource_uri: "agent://backend-developer",
       system_prompt_fragment: "# Roleplay Notes\n- HTTP verbs: GET read-only..."
     }
   }
```

The spawned agent doesn't get a name. It gets a composed behavioral contract, stacked from domain rules, subdomain patterns, and specialist depth, all assembled for this exact task. Three tiers collapse into one prompt fragment the agent runs as.

The tighter the match, the deeper the stack. A FastAPI task pulls all three tiers. A generic backend task pulls one or two. Task context shapes the specialist in real time, without any manual agent selection.

---

## Multi-agent tasks

When a task spans multiple domains, InvokerAI hands Claude a structured decomposition instead of free-text guidance. Six patterns, detected from the task text, no config required:

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

`permissionDecision: deny` is a real platform block. The Agent call doesn't happen. There's no workaround. That's the whole point.

**Kiro:** Same token pattern via `agentSpawn` + `userPromptSubmit` hooks.

**Cursor / GitHub Copilot:** No hook system. Routing is enforced via CLAUDE.md guidance: agents that follow it call `spawn_specialist` and get routed correctly. No platform-level block exists; an agent that ignores the rule can bypass routing silently.

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
invoker update                               Reinstall editable, rebuild router, run migration
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
invoker why "task text"                      Explain why a role was picked (trigger, confidence, runner-ups)
invoker why "task text" --json               Same, machine-readable JSON
invoker spawn "task" --dry-run               Preview role + persona + steps without committing
invoker spawn "task" --project-id myrepo     Track role usage per project
```

Primary surface for Agent/MCP: `mcp__invokerai__spawn_specialist(task, domains=[...])`

If MCP is unavailable (Cursor agent mode, Codex, or any harness where MCP args can't be passed), use the CLI equivalent from terminal. Returns the same bundle and writes the spawn token:

```bash
invoker spawn "TASK" --domains d1,d2
```

---

## The routing model

InvokerAI ships in two phases. Phase 1 works out of the box. Phase 2 gets smarter the more you use it.

| Phase | Model | What it needs |
|-------|-------|----------------|
| 1 (default) | TF-IDF + KNeighborsClassifier | Nothing. Ships working, no downloads |
| 2 | `BAAI/bge-large-en-v1.5` + RandomForestClassifier | 200+ logged decisions + one ~1.3 GB download |

Every routing decision logs to `~/.invokerai/routing_log.jsonl`. Hit 200 entries and want the accuracy bump?

```bash
pip install agent-invoker[embeddings]
python scripts/build_router.py --phase 2
```

Downloads once to `~/.cache/huggingface/`, runs fully local after that. No API calls. Everything stays on your machine.

---

## Custom agents

84+ agents in the default registry. Add your own: custom agents override defaults on `id` collision.

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
