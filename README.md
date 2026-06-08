<p align="center">
  <img alt="InvokerAI" src="docs/invokerAI-mark.svg" width="200" />
</p>

# InvokerAI

**InvokerAI routes tasks to specialist agents.** It sits between your task and your AI agent (Claude Code, Cursor, Kiro, Copilot, or any agent host) and decomposes work into the right specialists instead of letting one generic context window thrash across multiple domains.

Instead of asking a single agent to "refactor the payment gateway, add Stripe webhooks, and migrate to Postgres 16" all at once, InvokerAI splits the work: a backend specialist handles the gateway, a database specialist handles the migration, and a devops engineer handles the infrastructure. Each gets only the context they need.

## What You Get

**The Skill** — Agent skill installed via `npx invokerai-skills` (primary) or `invoker setup` (CLI). Runs as sub-skills (setup → decompose → spawn), each a prompt the host agent executes. Plans work; you spawn the agents via your own Agent tool.

**The SDK** — A Python library. Call `orchestrate(task, domains)` → get back a fully-resolved, topologically-ordered plan. No spawning, no execution—you bring your own runtime (Claude Agent SDK, CrewAI, LangGraph, etc.) and call the agents yourself.

---

## Install

### Primary: Skill (npm)

Requires Node 18+. Fastest path — no global install, copies the skill straight into `~/.claude/skills`:

```bash
npx invokerai-skills
```

Or install the package (adds the `invokerai-skills` command for re-running with flags like `--user` / `--project`):

```bash
npm install -g invokerai-skills
```

or scoped to your project:

```bash
npm install invokerai-skills --save-dev
```

This copies the skill (router + 3 sub-skills) to `~/.claude/skills/invokerai` and is ready to use in-editor immediately.

### Alternative: CLI + SDK (Python)

Requires Python 3.10+.

```bash
git clone https://github.com/justjammin/invokerai
cd invokerai
python install.py
```

The installer creates a venv at `~/.invokerai/venv`. Activate it:

```bash
source ~/.invokerai/venv/bin/activate
```

The Python path also installs the CLI (`invoker …` commands) and SDK (`import agent_invoker`). Run `invoker setup` once to build the agent map.

### Claude Code plugin

InvokerAI ships a plugin manifest, so you can install it from Claude Code's plugin marketplace. Add the marketplace, then install the plugin:

```
/plugin marketplace add justjammin/invokerai
/plugin install invokerai@invokerai
```

Or run `/plugin`, open the **Discover** tab, search for `invokerai`, and press Enter to pick the install scope (user / project / local).

### Upgrading from the old MCP build

Earlier versions registered an `invokerai` MCP server and per-editor hooks. The current build is skill + CLI + SDK only — no MCP. The new code won't auto-remove the old live registrations, so on any device where the old `invoker setup` ran, follow the per-device checklist in [`docs/MCP_CLEANUP.md`](docs/MCP_CLEANUP.md) (read-only audit first, then guided removal with backups). Fresh installs can skip this.

---

## The Skill

### Three sub-skills working together

The skill installs as a router and three sub-skills, each executed by the host agent as a prompt:

1. **`invokerai:setup`** — Main agent reads installed-agent frontmatter, classifies each into a
   domain by judgment (name-match, description analysis, or unmapped), writes
   `~/.invoker/agent-map.json` as `{domain: [agents]}`. Run once after adding new agents.

2. **`invokerai:decompose`** — Main agent builds the bead_graph (domains → DAG of steps),
   detects multi-agent patterns (pipeline, parallel, supervisor, etc.), optionally writes
   beads tracking tickets for each step. Closed and pruned on task completion.

3. **`invokerai:spawn`** — Main agent selects an installed agent per domain by description match
   (via `agent_select.resolve_plan`), emits a fully-resolved, topologically-ordered execution
   plan with agent names, actions, and dependencies. Hands it back to you.

### How it works

```
Task: "build a REST API with auth and tests"
         │
         ▼
  Host agent invokes setup sub-skill (if needed)
         ▼ reads agent-map or builds it
  Host agent invokes decompose sub-skill
         ▼ domains → bead_graph + pattern + steps
  Host agent invokes spawn sub-skill
         ├─ Router: classify task → identify domains
         ├─ Select: per domain, pick agent by description match from agent-map
         ├─ Resolve: map roles → real installed agent names
         └─ Return: fully-resolved, ordered plan
         │
         ▼
  Host agent spawns returned agents in order via its own Agent tool
  (Skill plans. Host spawns. Skill never spawns.)
```

### Primary surface (in-editor)

After `invoker setup` (or `npx invokerai-skills` install), the host agent invokes the three
sub-skills as needed. Internally, they call the routing + selection engine. Result:

```json
{
  "routing": "crew",
  "pattern": "pipeline",
  "spawn_authorized": true,
  "steps": [
    {
      "step": 1,
      "agent": "architect-reviewer",
      "action": "Create implementation plan",
      "parallel": false,
      "domain": "architecture"
    },
    {
      "step": 2,
      "agent": "backend-developer",
      "action": "Implement API layer",
      "parallel": false,
      "domain": "backend"
    },
    {
      "step": 3,
      "agent": "code-reviewer",
      "action": "Security review",
      "parallel": false,
      "domain": "security"
    },
    {
      "step": 4,
      "agent": "test-automator",
      "action": "Implement test suite",
      "parallel": false,
      "domain": "testing"
    }
  ],
  "domains": ["backend", "security", "testing"],
  "session_id": "default"
}
```

The host agent then spawns each agent from `steps[]` in order, respecting `parallel: true` flags.

### Domains

Domains are **dynamic** — derived from your installed agents. The setup sub-skill names them by
judgment from agent frontmatter. Novel domains (e.g., `legal`, `devrel`, `sales`) route when you
have agents for them. The built-in seed (below) covers the common case and serves as the
fallback for text-based inference:

| Domain | Add when... | Skip when... |
|--------|-------------|--------------|
| `architecture` | New subsystem design, cross-cutting redesign, impl path needs codebase context, "how should we structure X?" | Bug fix, additive feature with clear scope, path is obvious |
| `backend` | Server routes, REST/GraphQL APIs, IPC handlers, business logic, auth middleware | Pure UI work, DB-only schema changes with no server code |
| `frontend` | UI components, styling, client-side state, browser events, rendering | Server-only work, no user-facing changes |
| `database` | Schema changes, migrations, query optimization, indexes, ORM models | No DB reads/writes in task |
| `devops` | CI/CD pipelines, Dockerfiles, infra config, deploy scripts, env vars | App code changes only |
| `security` | Auth flows, permissions, secrets handling, input validation, CVE fixes | Feature work with no trust boundary changes |
| `ml` | Model training, inference, embeddings, prompt engineering, vector search | Standard CRUD with no ML components |
| `testing` | Writing/fixing tests, test infra, coverage gaps, flaky test diagnosis | Impl work where tests are a side effect |
| `documentation` | API docs, READMEs, changelogs, docstrings, user guides | Code-only changes with no public surface |
| `mobile` | iOS/Android native code, React Native, Flutter, mobile-specific APIs | Web-only work |
| `data` | ETL pipelines, data transforms, analytics queries, reporting | App features with no data pipeline involvement |
| `code-review` | Reviewing a diff/PR, auditing quality/security, post-impl review | Active implementation (review ≠ build) |
| `marketing` | Campaign strategy, content, SEO, audience funnel, paid search, ad spend, ROAS, bid strategy | Feature development with no marketing component |
| `business` | Stakeholder requirements, competitive analysis, roadmapping, KPIs, OKRs, prioritization, ROI | Technical implementation with no business strategy |
| `research` | Literature review, investigation, data synthesis, findings documentation, comparative analysis | Standard feature work with no research depth |

### Routing patterns

InvokerAI detects multi-agent patterns automatically. No config required:

| Pattern | When | Structure |
|---------|------|-----------|
| `pipeline` | Sequential domains (default) | Ordered steps, each a different specialist |
| `parallel` | "simultaneously", "concurrently" | Steps marked `parallel: true`, integration at end |
| `supervisor` | "manage", "coordinate", "oversee agents" | Planner → workers → reviewer |
| `feedback_loop` | "review and revise", "iterate until" | Generator → critic → revise (3-step loop) |
| `plan_then_execute` | "design first then", "plan then build" | Architect step first, execution follows |
| `hierarchical` | Full-stack + enterprise/platform keywords | Top supervisor → domain leads → integration |

### Routing confidence

Confidence gates the route:

- **70+** — High confidence, clean route
- **50–69** — Medium confidence, returns runner-up roles alongside primary
- **< 50** — Low confidence, asks for clarification before spawning

Check routing decisions:

```bash
invoker why "refactor payment gateway to async"
```

```
Role:       backend-developer
Confidence: 87%  (deterministic)
Routing:    solo

Why:
  Matches: "refactor" (verb), "async" (keyword)
  Category: coding (priority 5)

Runner-ups:
  refactoring-specialist
  fullstack-developer

To override: invoker spawn "refactor payment gateway to async" --domains backend
```

### CLI reference (Skill)

```bash
# Get execution plan — primary surface
invoker spawn "task" --domains d1,d2

# Preview only, don't commit token
invoker spawn "task" --dry-run

# Track usage per project (auto-derived from cwd if omitted)
invoker spawn "task" --project-id myrepo

# Persist under named session
invoker spawn "task" --session-id my-session

# Explain routing decision
invoker why "task text"
invoker why "task text" --json

# Subagent self-check — verify the routed specialist matches the task
invoker confirm "task" "expected-role"

# Build agent map from installed agents
invoker setup

# List all available specialists
invoker agents
invoker agents --category backend

# Decompose pattern + steps only (no agent resolution)
invoker decompose "task"

# Route-only (no token, no spawn)
invoker "task text"
invoker --registry PATH "task text"
invoker --no-log "task text"
invoker --model-info

# Uninstall routing
invoker uninstall
invoker uninstall --purge                    # Also delete ~/.invokerai/

# Update package and rebuild router
invoker update

# Add tools to agents
invoker tools add --all TOOL [TOOL...]           # All agents
invoker tools add --category NAME TOOL [TOOL...] # By category
invoker tools add --agents ID,ID TOOL [TOOL...]  # By agent
invoker tools list AGENT_ID                      # List tools for agent

# Build router (required for Phase 2)
invoker train                                # Phase 1: TF-IDF + kNN
invoker train --phase 2                      # Phase 2: embeddings + RandomForest

# Patch session outcome metrics
invoker log-outcome DATE PREFIX CORRECTIONS ACCEPTED
```

---

## The SDK

### Python library: pure orchestration, no execution.

InvokerAI is available as an importable SDK. It returns plans and agent definitions; executes nothing. You bring the runtime and auth.

```bash
pip install agent-invoker
```

The SDK core has **zero heavy dependencies**. It imports `decompose`, `load_agent_map`, `resolve_plan`, `compose_agent_definition`, `topological_order`, `parallel_groups`, `orchestrate` at the package root.

### Public API

| Function | Purpose | Returns |
|----------|---------|---------|
| `decompose(task, domains, complexity)` | Detect MAS pattern + skeleton steps + bead graph | `DecomposeResult` |
| `load_agent_map(map_path)` | Load agent-map from disk | `dict \| None` |
| `resolve_plan(task, plan, agent_map)` | Map roles → installed agent names | `dict` |
| `compose_agent_definition(node, task)` | Build plain-dict agent definition from node | `dict` |
| `topological_order(bead_graph)` | Order bead-graph nodes into dependency levels | `list[list[str]]` |
| `parallel_groups(bead_graph)` | Same as `topological_order` (alias for clarity) | `list[list[str]]` |
| `orchestrate(task, domains, agent_map, map_path)` | One-call full plan (decompose → resolve → compose → order) | `dict` |

### No side effects

- No network calls
- No spawning
- No token writes
- No file modifications
- Pure computation: task in → plan out

### Example: Claude Agent SDK

```python
import asyncio
from anthropic import Anthropic
from agent_invoker import orchestrate

client = Anthropic()

async def run_orchestration(task: str, domains: list[str]):
    """Get plan from InvokerAI, execute with Claude Agent SDK."""
    
    # Step 1: Get full plan from InvokerAI (zero execution)
    plan = orchestrate(task, domains=domains)
    
    print(f"Pattern: {plan['pattern']}")
    print(f"Levels: {len(plan['levels'])}")
    
    # Step 2: Execute topologically-ordered levels
    for level_idx, level in enumerate(plan['levels']):
        print(f"\nLevel {level_idx + 1} ({len(level)} agents):")
        
        # Run all agents in this level concurrently (they're dependency-independent)
        tasks = [
            client.agents.execute(
                agent_id=node["agent"],
                # compose_agent_definition already in node["prompt"]
                system_prompt=node["prompt"],
                tools=node["tools"],
                input=task,
            )
            for node in level
        ]
        
        results = await asyncio.gather(*tasks)
        
        for node, result in zip(level, results):
            print(f"  {node['agent']}: {result.get('status', 'done')}")
    
    return plan

# Run it
asyncio.run(run_orchestration(
    "build a FastAPI endpoint with Pydantic validation and tests",
    domains=["backend", "testing"]
))
```

### Example: CrewAI

```python
from crewai import Agent, Task, Crew
from agent_invoker import orchestrate

def run_with_crewai(task: str, domains: list[str]):
    """Get plan from InvokerAI, execute with CrewAI."""
    
    # Step 1: Orchestrate (returns fully-resolved, ordered plan)
    plan = orchestrate(task, domains=domains)
    
    # Step 2: Map levels to CrewAI agents + tasks
    all_agents = []
    all_tasks = []
    
    for level_idx, level in enumerate(plan['levels']):
        level_agents = []
        level_tasks = []
        
        for node in level:
            # node keys: node_id, agent, prompt, tools, model, deps, annotation
            agent = Agent(
                role=node['agent'],
                goal=node['annotation'] or f"Execute {node['agent']}",
                backstory=node['prompt'],  # Composed system prompt
                tools=[...],  # Map node['tools'] to CrewAI tool objects
                model=node['model'],
            )
            level_agents.append(agent)
            
            task = Task(
                description=task,
                expected_output=f"Completed: {node['annotation']}",
                agent=agent,
                dependencies=[all_tasks[i] for i in node['deps']] if node['deps'] else [],
            )
            level_tasks.append(task)
        
        all_agents.extend(level_agents)
        all_tasks.extend(level_tasks)
    
    # Step 3: Create crew and execute
    crew = Crew(agents=all_agents, tasks=all_tasks)
    result = crew.kickoff(inputs={"task": task})
    
    return result

# Run it
run_with_crewai(
    "build a FastAPI endpoint with Pydantic validation and tests",
    domains=["backend", "testing"]
)
```

### Example: LangChain / LangGraph

```python
from langgraph.graph import StateGraph
from agent_invoker import orchestrate, topological_order

def run_with_langgraph(task: str, domains: list[str]):
    """Get plan from InvokerAI, execute with LangGraph."""
    
    # Step 1: Orchestrate (returns fully-resolved plan + bead_graph)
    plan = orchestrate(task, domains=domains)
    
    # Step 2: Build LangGraph from topological levels
    graph = StateGraph(state_schema={"output": str, "task": str})
    
    # Step 3: Add nodes (one per agent)
    for level in plan['levels']:
        for node in level:
            # node keys: node_id, agent, prompt, tools, model, deps, annotation
            graph.add_node(
                node['node_id'],
                # Your runnable function that calls the agent
                create_agent_runnable(
                    name=node['agent'],
                    system_prompt=node['prompt'],
                    tools=node['tools'],
                    model=node['model'],
                ),
            )
    
    # Step 4: Wire edges based on dependencies
    for level in plan['levels']:
        for node in level:
            if node['deps']:
                # Depends on prior nodes
                for dep_id in node['deps']:
                    graph.add_edge(dep_id, node['node_id'])
            else:
                # No dependencies → starts at start
                graph.add_edge("__start__", node['node_id'])
    
    # Step 5: Execute
    compiled = graph.compile()
    result = compiled.invoke({"task": task})
    
    return result

def create_agent_runnable(name, system_prompt, tools, model):
    """Build a runnable agent with the composed prompt."""
    # Your implementation: call your AI agent with system_prompt as the system context
    pass

# Run it
run_with_langgraph(
    "build a FastAPI endpoint with Pydantic validation and tests",
    domains=["backend", "testing"]
)
```

### Orchestrate result shape

```python
{
    "pattern": "pipeline",           # or: parallel, supervisor, feedback_loop, plan_then_execute, hierarchical
    "levels": [                      # Topologically ordered
        [
            {
                "node_id": "s1",
                "agent": "architect-reviewer",
                "prompt": "# System prompt (composed from persona files)",
                "tools": ["Read", "Write", "Bash"],
                "model": "claude-opus-4-1",
                "deps": [],
                "annotation": "Create implementation plan",
            },
            ...
        ],
        [
            {
                "node_id": "s2",
                "agent": "backend-developer",
                "prompt": "...",
                "tools": [...],
                "model": "...",
                "deps": ["s1"],
                "annotation": "Implement API layer",
            },
            ...
        ],
    ],
    "coverage_gaps": [],             # Domains with no installed agent (fallback used)
}
```

---

## The routing model

InvokerAI uses two phases. Phase 1 ships out of the box. Phase 2 gets smarter as you log decisions.

| Phase | Model | What it needs |
|-------|-------|---------------|
| **1 (default)** | TF-IDF + KNeighborsClassifier | Nothing—ships working, zero downloads |
| **2** | BGE large embeddings + RandomForestClassifier | 200+ logged decisions + one ~1.3 GB download |

Every routing decision logs to `~/.invokerai/routing_log.jsonl`. Once you hit 200 entries, upgrade:

```bash
pip install agent-invoker[embeddings]
python scripts/build_router.py --phase 2
```

Downloads once to `~/.cache/huggingface/`, runs fully local after. No API calls. Everything stays on your machine.

---

## Custom agents

The default registry ships with 80+ specialist agents. Override on collision:

```bash
invoker --registry ./my-agents.json "task text"
invoker --registry ./agents/ "task text"        # Loads every *.json in dir
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

---

If you like InvokerAI, check out [promper](https://github.com/justjammin/promper) — it turns a rough request into a clean, role-grounded prompt by routing through InvokerAI to inherit the right agent's persona.
