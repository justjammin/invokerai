---
name: invokerai
description: Agent routing brain — given a task and domains, returns the optimal specialist agent, MAS execution plan, and spawn authorization. Call before spawning any agent. Auto-configures if not present.
---

# InvokerAI — Agent Router

InvokerAI routes tasks to specialist agents using a deterministic + ML classifier. Pass explicit `domains[]` for accurate MAS step generation. Always returns spawn authorization, execution steps, and persona bundle.

## Setup (run first)

Verify MCP server is active:

```bash
invoker --model-info
```

If `invoker` is not found:

```bash
cd /path/to/invokerai && python install.py
invoker setup
```

## When to use

**PRIMARY SURFACE:** Always call `mcp__invokerai__spawn_specialist` before spawning any agent.

**Step 1 — Identify domains** (pick 1–N that apply):
`architecture` | `backend` | `frontend` | `database` | `devops` | `security`
`ml` | `testing` | `documentation` | `mobile` | `data` | `code-review`

**Step 2 — Call spawn_specialist:**

```
mcp__invokerai__spawn_specialist(
    task="build a REST API with auth and tests",
    domains=["backend", "security", "testing"]
)
→ {
    "routing": "orchestrate",
    "pattern": "pipeline",
    "spawn_count": 4,
    "spawn_authorized": true,
    "steps": [
      {"step": 1, "role": "architect-reviewer", "action": "Create implementation plan"},
      {"step": 2, "role": "backend-developer", "action": "Implement API layer"},
      {"step": 3, "role": "code-reviewer", "action": "Security review"},
      {"step": 4, "role": "test-automator", "action": "Implement test suite"},
      {"step": 5, "role": "code-reviewer", "action": "Review output"}
    ]
  }
```

## MAS step structure

Every orchestrate result follows: **PLAN → EXECUTE → REVIEW → DEPLOY PLAN** (deploy only if devops domain).

| Step | Role | Condition |
|------|------|-----------|
| Plan | `architect-reviewer` | Always first (except code-review-only) |
| Execute | domain specialists | Sequential (1–2 domains) or parallel (3+) |
| Review | `architect-reviewer` or `code-reviewer` | Always last execute step |
| Deploy plan | `cloud-architect` | Only if `devops` in domains |

## Routing rules

Every result returns `routing == "orchestrate"` with a `steps` array — always spawn from steps.

| Result | Action |
|--------|--------|
| `routing == "orchestrate"` | Spawn each step in `steps` array; parallel where `parallel: true` |
| `confidence < 50` | Ask user to clarify before routing |

## Planner role

You are **orchestrator/planner only**. Never write code. Never implement directly.
Your job: plan, decompose, identify domains, call spawn_specialist, coordinate execution.

## Skill bypass

When running inside a skill invocation (/graphify, /kyoko, /hyperframes, /remotion, /weave, etc.),
do NOT call mcp__invokerai__spawn_specialist. Skills manage their own agent spawning.

## CLI utilities

```bash
# Router status
invoker --model-info

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
