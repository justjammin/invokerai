---
name: invokerai
description: Agent routing brain — given a task and domains, returns the optimal specialist agent and MAS execution plan. Run `invoker setup` first to build the agent map from installed agents.
---

# InvokerAI — Agent Router

InvokerAI routes tasks to specialist agents using a deterministic + ML classifier. Pass explicit
`--domains` for accurate MAS step generation. Always call `invoker spawn` before spawning any agent.

## Setup (run first)

Build the agent map from your installed agents:

```bash
invoker setup
```

This scans your installed agents, builds `~/.invoker/agent-map.json`, and injects the InvokerAI
routing protocol into `~/.claude/CLAUDE.md` and `~/.agents/AGENTS.md`.

Verify the router:

```bash
invoker --model-info
```

## How it works

1. `invoker setup` — scans installed agents → builds agent map (`~/.invoker/agent-map.json`)
2. `invoker spawn` — classifies the task, maps roles to installed agent names, returns the plan
3. Host agent spawns the returned agents via its own Agent tool in step order

The skill **plans**. The host agent **spawns**.

## When to use

**PRIMARY SURFACE:** Before spawning any agent, call `invoker spawn` to get the execution plan.

**Step 1 — Identify domains** (pick 1–N that apply):
`architecture` | `backend` | `frontend` | `database` | `devops` | `security`
`ml` | `testing` | `documentation` | `mobile` | `data` | `code-review`

**Domain precision is critical** — `steps[]` is shaped directly by `--domains`. Wrong domains
→ phantom steps → wasted agents.
- Pass ONLY domains where real work exists. Ask: "does this task actually touch this layer?"
- When unsure, under-specify — low confidence score will surface missing domains.
- Never add a domain speculatively.

**Domain decision guide:**

| Domain | Add when... | Skip when... |
|--------|-------------|--------------|
| `architecture` | New subsystem design, cross-cutting redesign, impl agent needs codebase context before it can safely start, "how should we structure X?" | Bug fix, additive feature with clear scope, impl path is obvious |
| `backend` | Server routes, REST/GraphQL APIs, IPC handlers, business logic, auth middleware | Pure UI work, DB-only schema changes with no server code |
| `frontend` | UI components, styling, client-side state, browser events, rendering | Server-only work, no user-facing changes |
| `database` | Schema changes, migrations, query optimization, indexes, ORM models | No DB reads/writes in the task |
| `devops` | CI/CD pipelines, Dockerfiles, infra config, deploy scripts, env vars | App code changes only |
| `security` | Auth flows, permissions, secrets handling, input validation, CVE fixes | Feature work with no trust boundary changes |
| `ml` | Model training, inference, embeddings, prompt engineering, vector search | Standard CRUD with no ML components |
| `testing` | Writing/fixing tests, test infra, coverage gaps, flaky test diagnosis | Impl work where tests are a side effect (let impl agent write them) |
| `documentation` | API docs, READMEs, changelogs, docstrings, user guides | Code-only changes with no public surface |
| `mobile` | iOS/Android native code, React Native, Flutter, mobile-specific APIs | Web-only work |
| `data` | ETL pipelines, data transforms, analytics queries, reporting | App features with no data pipeline involvement |
| `code-review` | Reviewing a diff/PR, auditing quality/security, post-impl review | Active implementation (review ≠ build) |

**Step 2 — Call `invoker spawn`:**

```bash
invoker spawn "build a REST API with auth and tests" --domains backend,security,testing
```

Returns:

```json
{
  "routing": "crew",
  "pattern": "pipeline",
  "spawn_authorized": true,
  "steps": [
    {"step": 1, "agent": "architect-reviewer", "action": "Create implementation plan", "parallel": false},
    {"step": 2, "agent": "backend-developer", "action": "Implement API layer", "parallel": false},
    {"step": 3, "agent": "code-reviewer", "action": "Security review", "parallel": false},
    {"step": 4, "agent": "test-automator", "action": "Implement test suite", "parallel": false}
  ],
  "domains": ["backend", "security", "testing"],
  "session_id": "default"
}
```

**Step 3 — Spawn the returned agents yourself:**

Using your own Agent tool, spawn each agent from `steps[]` in order, respecting
`parallel: true` flags (parallel steps can be spawned simultaneously).

For solo routing, spawn the single agent in `agent`.

## Output shape

| Field | Description |
|-------|-------------|
| `routing` | `"solo"` or `"crew"` |
| `agent` | Solo: installed agent name |
| `steps` | Crew: ordered list with `agent`, `action`, `parallel`, `domain` |
| `pattern` | MAS pattern: `pipeline`, `parallel`, `plan_then_execute`, `feedback_loop`, `hierarchical` |
| `domains` | Resolved domains |
| `spawn_authorized` | Always `true` unless `dry_run` |
| `session_id` | Session identifier |
| `coverage_gaps` | Domains with no installed agent (fallback used) |

## Routing rules

| Result | Action |
|--------|--------|
| `routing == "crew"` | Spawn each step in `steps[]`; parallel where `parallel: true` |
| `routing == "solo"` | Spawn the single `agent` |
| `spawn_authorized == false` | Do NOT spawn (`dry_run` mode — preview only) |
| `coverage_gaps` non-empty | Some domains had no installed agent; fallback agent used |

## Planner role

You are **orchestrator/planner only**. Never write code. Never implement directly.
Your job: plan, decompose, identify domains, call `invoker spawn`, then spawn the returned
agents in order using your own Agent tool.

## Skill bypass

When running inside a skill invocation (/graphify, /kyoko, /hyperframes, /remotion, /weave, etc.),
do NOT call `invoker spawn`. Skills manage their own agent spawning.

## CLI reference

```bash
# Get execution plan (primary surface)
invoker spawn "task" --domains d1,d2

# Preview routing without committing
invoker spawn "task" --dry-run

# Explain routing decision
invoker why "task text"
invoker why "task text" --json

# Subagent self-check
invoker confirm "task" "expected-role"

# Build agent map from installed agents
invoker setup

# List available specialist agents
invoker agents
invoker agents --category backend

# Track role usage per project
invoker spawn "task" --project-id myrepo

# Bulk add tools to all agents
invoker tools add --all mcp__lean-ctx__ctx_read mcp__lean-ctx__ctx_shell

# Add tools to a category
invoker tools add --category backend WebSearch WebFetch

# List tools for an agent
invoker tools list debugger
```

## Build router (required for ML routing)

```bash
python scripts/build_router.py          # Phase 1: TF-IDF + kNN
python scripts/build_router.py --phase 2  # Phase 2: mpnet + RandomForest
```

Phase 2 requires: `pip install agent-invoker[embeddings]`

## Custom agents

```json
{
  "version": "1.0",
  "agents": [{
    "id": "my-agent",
    "category": "backend",
    "description": "Does X for Y",
    "domains": ["backend"],
    "triggers": ["keyword1", "keyword2"],
    "tools": ["Read", "Write", "Bash"],
    "orchestrate": false
  }]
}
```

```bash
invoker --registry ./my-agents.json "task text"
```
