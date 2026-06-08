---
name: invokerai
description: >
  InvokerAI agent routing brain delivered as sub-skills. Three sub-skills:
  invokerai:setup (build domain→agent map once), invokerai:decompose (break task into bead-graph DAG),
  invokerai:spawn (select and spawn agents in order). Run setup first, then decompose, then spawn.
---

# InvokerAI — Agent Router

InvokerAI routes tasks to specialist agents by breaking work into a directed acyclic graph (DAG), mapping domains to installed agents, and spawning them in dependency order. The skill **plans**. You (the main agent) **spawn** using your own Agent tool.

---

## How It Works

Three sub-skills execute the routing pipeline:

### 1. **invokerai:setup**

Run once (or when agents change). Builds `~/.invoker/agent-map.json` from your installed agents.

- Scans agent files: `~/.claude/agents/`, `~/.codex/agents`, `~/.gemini/agents`
- Groups agents into a bounded domain taxonomy (~15-40 domains)
- Writes `~/.invoker/agent-map.json` with all agents indexed by domain
- Idempotent + additive: merges new agents, keeps hand-edits

### 2. **invokerai:decompose**

Break a task into a DAG of execution steps.

- Identify domains the task touches
- Build a `bead_graph`: ordered nodes with dependencies, parallelism flags, MAS pattern (pipeline/parallel/fan-out/fan-in/etc.)
- Create BEADS tickets (if `bd` available): one ticket per node, linked as a family tree
- Output: DAG structure + ticket IDs

### 3. **invokerai:spawn**

Select agents and spawn them in order.

- For each DAG node: look up the domain in agent-map, select the best-match agent
- Spawn each agent via your own Agent tool in DAG order (parallel where flagged)
- BEADS lifecycle: mark tickets running → on completion CLOSE + PRUNE (delete) them to keep .beads store small
- If `bd` unavailable: proceed normally (no tracking)
- On finish: confirm all tickets closed + pruned

---

## Operating Principle

**The skill is the planner. You are the executor.**

- `invokerai:setup` → builds map (one-time)
- `invokerai:decompose` → plans the work (task → DAG)
- `invokerai:spawn` → guides execution (spawns agents, tracks via BEADS, confirms completion)

You use your native Agent tool to spawn; the skill never spawns. The skill returns structured plans; you execute them.

---

## When to Use

### Before your first task:

```
/invokerai:setup
```

This builds the agent map from your installed agents. Re-run if you add new agents.

### For each task:

```
/invokerai:decompose
```

Provide the task and your identified domains. Get back a DAG + tickets.

```
/invokerai:spawn
```

Execute the DAG: spawn agents in order, track via BEADS, confirm completion.

---

## Domain Decision Guide

Pick domains that actually apply to the task:

| Domain | Add when... | Skip when... |
|--------|-------------|--------------|
| `architecture` | New subsystem design, cross-cutting redesign, impl agent needs codebase context before safe start | Bug fix, additive feature with clear scope, impl path obvious |
| `backend` | Server routes, REST/GraphQL APIs, IPC handlers, business logic, auth middleware | Pure UI work, DB-only schema changes with no server code |
| `frontend` | UI components, styling, client-side state, browser events, rendering | Server-only work, no user-facing changes |
| `database` | Schema changes, migrations, query optimization, indexes, ORM models | No DB reads/writes in the task |
| `devops` | CI/CD pipelines, Dockerfiles, infra config, deploy scripts, env vars | App code changes only |
| `security` | Auth flows, permissions, secrets handling, input validation, CVE fixes | Feature work with no trust boundary changes |
| `ml` | Model training, inference, embeddings, prompt engineering, vector search | Standard CRUD with no ML components |
| `testing` | Writing/fixing tests, test infra, coverage gaps, flaky test diagnosis | Impl work where tests are a side effect |
| `documentation` | API docs, READMEs, changelogs, docstrings, user guides | Code-only changes with no public surface |
| `mobile` | iOS/Android native code, React Native, Flutter, mobile-specific APIs | Web-only work |
| `data` | ETL pipelines, data transforms, analytics queries, reporting | App features with no data pipeline |
| `code-review` | Reviewing a diff/PR, auditing quality/security, post-impl review | Active implementation (review ≠ build) |

**Domain precision is critical:** wrong domains → phantom steps → wasted agents.
- Pass ONLY domains where real work exists.
- When unsure, under-specify — gaps will surface in decompose.
- Never add a domain speculatively.

---

## Sub-skill Reference

| Skill | When | Output |
|-------|------|--------|
| `/invokerai:setup` | First run, after adding agents | `~/.invoker/agent-map.json` + summary |
| `/invokerai:decompose` | For each task | bead_graph (DAG) + ticket IDs (or in-memory plan) |
| `/invokerai:spawn` | After decompose | Spawned agents + confirmed completion |

---

## Skill Bypass

When running inside other skill invocations (`/graphify`, `/kyoko`, `/hyperframes`, `/remotion`, `/weave`, etc.), those skills manage their own agent spawning. InvokerAI routing applies only to direct orchestrator tasks.

---

## Example Flow

### Task: "Build a REST API with auth and tests"

**Setup (first time):**
```
/invokerai:setup
```

**Decompose:**
```
/invokerai:decompose
Task: Build a REST API with auth and tests
Domains: backend, security, testing
```

Returns a DAG like:
```
node-1: architect-reviewer (backend) — Create impl plan
node-2: backend-developer (backend) — Implement API [depends on node-1]
node-3: security-engineer (security) — Design auth layer [parallel with node-2]
node-4: test-automator (testing) — Write tests [depends on node-2 + node-3]
```

**Spawn:**
```
/invokerai:spawn
[You spawn architect-reviewer]
[Wait for completion, spawn backend-developer + security-engineer in parallel]
[When both done, spawn test-automator]
[Confirm all tickets closed + pruned]
```

---

## Files Referenced

- `~/.invoker/agent-map.json` — Domain-to-agent mapping (built by setup)
- `~/.claude/agents/*.md` — Installed agent definitions
- `.beads/` — Ticket store (optional, if `bd` available)
