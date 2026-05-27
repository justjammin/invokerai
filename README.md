<p align="center">
  <img alt="InvokerAI" src="docs/invokerAI-mark.svg" width="200" />
</p>

# InvokerAI

So you just thought of your eureka idea and it's time to build it. You drop a big task into the chat, and your agent tries to do everything at once. Auth refactor AND database migration AND frontend changes, all in one context window, one generic brain, no separation. The output is fine. Not great. Fine.

InvokerAI fixes that. Pass a task and the relevant domains. It figures out which specialist to call, builds their identity, and hands them everything they need before they write a single line. You get a backend engineer when you need one. Not a generalist pretending.

**What it's actually doing:**
- **Decomposition** — Complex tasks break into focused subtasks. Each agent gets only the context it needs.
- **Specialization** — A domain-tuned persona beats generic reasoning every time. A backend engineer sees backend patterns. A test engineer catches coverage gaps the generalist missed.
- **Parallelism** — Independent subtasks run concurrently instead of sequentially.
- **Noise reduction** — Less context window per agent means less hallucination surface and stronger reasoning.

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
1. Classifier runs — TF-IDF + KNN + regex signals → role = "backend-developer", confidence = 87
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

## Gas City Integration (Optional)

Wait until you see what happens when you pair this with [Gas City](https://github.com/gastownhall/gascity).

Here's the thing: InvokerAI decides *who* runs the work. Gas City actually runs it: supervised sessions, crash recovery, cross-agent handoff via `bd` mail instead of JSON files. Solo routing stays exactly the same. Crew routing gets a real supervisor loop.

Gas City is the engine. InvokerAI is the GPS.

**Prerequisites:**
- `gc` binary installed: `brew install gastownhall/gascity/gascity`
- Gas City >= current release
- Initialized city: `gc init` (one-time setup)
- Each project repo registered as a rig: `cd your-repo && gc rig add .`

**Enable:**

```bash
# Auto-detect gc, log a warning on first activation
export INVOKERAI_GASCITY=auto

# Require gc — error immediately if missing
export INVOKERAI_GASCITY=on

# Default: disabled (manual spawn behavior unchanged)
export INVOKERAI_GASCITY=off
```

**What changes with Gas City enabled:**

- **Crew routing:** Multi-agent steps dispatch via `gc sling --formula` with supervisor management and crash recovery
- **Handoff:** Inter-agent context via `bd` mail (beads-backed) instead of JSON files
- **Persona files:** Agent instructions written to `/tmp/invokerai-*.persona.md` per-step, swept at server startup
- **New tool:** `get_crew_status(crew_root_bead_id)` — poll progress of a running crew (pending/running/done/failed per agent)

Solo routing is unchanged regardless of Gas City setting.

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
| 2 | `all-mpnet-base-v2` + RandomForestClassifier | 200+ logged decisions + one ~420 MB download |

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
