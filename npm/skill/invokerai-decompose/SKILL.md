---
name: invokerai:decompose
description: Break a task into a bead-graph DAG with ordered steps, dependencies, and parallelism. Create BEADS tickets if available.
---

# invokerai:decompose — Task Decomposition

Break a task into a directed acyclic graph (DAG) of execution steps, each with identified domains, dependencies, and parallelism flags.

---

## What You Do

### Step 0: Discover available domains from agent-map

Read `~/.invoker/agent-map.json`. Extract the `domains` keys — these are the
**only valid domains** for decomposition. Do not invent domains that aren't in the map.

```bash
# Read the map to discover available domains
cat ~/.invoker/agent-map.json
```

Extract domain names: `["backend", "frontend", "testing", "marketing", ...]`

If the map does not exist or is empty, run `/invokerai:setup` first.

### Step 1: Identify domains for this task

Given the task description and the domains discovered in Step 0:

- Select only domains where **real work exists** for this task
- Validate each selected domain is present in the agent-map
- Note any required domains with no installed agents (coverage gaps)

### Step 2: Build the bead_graph

Create a directed acyclic graph (DAG) where each node represents a step:

```json
{
  "bead_graph": [
    {
      "id": "node-1",
      "domain": "architecture",
      "action": "Create implementation plan",
      "deps": [],
      "parallel": false,
      "agent": "architect-reviewer"
    },
    {
      "id": "node-2",
      "domain": "backend",
      "action": "Implement API layer",
      "deps": ["node-1"],
      "parallel": false,
      "agent": "backend-developer"
    },
    {
      "id": "node-3",
      "domain": "security",
      "action": "Design auth layer",
      "deps": ["node-1"],
      "parallel": true,
      "agent": "security-engineer"
    },
    {
      "id": "node-4",
      "domain": "testing",
      "action": "Write test suite",
      "deps": ["node-2", "node-3"],
      "parallel": false,
      "agent": "test-automator"
    }
  ],
  "pattern": "pipeline_with_parallel",
  "task": "Build a REST API with auth and tests"
}
```

**DAG properties:**
- Each node has a unique `id` (e.g., `node-1`, `node-2`).
- `deps`: list of node IDs this step depends on (empty = no deps, can start immediately).
- `parallel`: `true` if this step can run concurrently with others at the same level.
- `agent`: the agent name (will be filled in by spawn; decompose can propose or leave blank).
- `pattern`: the multi-agent pattern (e.g., `pipeline`, `parallel`, `fan_out`, `fan_in`, `supervisor`, etc.).

**Key patterns:**
- **pipeline**: steps run sequentially, each depends on the previous (node-1 → node-2 → node-3).
- **parallel**: independent steps run concurrently, then join (node-2 + node-3 both ready, node-4 waits for both).
- **fan_out**: one step spawns many independent tasks (node-1, then node-2 + node-3 + node-4 parallel).
- **fan_in**: multiple independent steps converge on one (node-2 + node-3 parallel, then node-4 depends on both).
- **supervisor**: one step oversees others (hierarchy, not pure DAG).

### Step 3: Create BEADS tickets (if `bd` available)

If the `bd` (beads) CLI is available:

1. Create a parent epic for the task:
   ```bash
   bd create "Task: <task_description>" --epic --json
   ```
   Capture the parent ticket ID (e.g., `TICKET-123`).

2. For each node in the bead_graph, create a child ticket:
   ```bash
   bd create "Step <id>: <action>" \
     --parent TICKET-123 \
     --depends <comma-separated list of dep node IDs> \
     --json
   ```

3. Record the mapping: `{node_id → ticket_id}`.

4. Output the full ticket list.

**If `bd` is unavailable:** Skip ticket creation. Decompose outputs the bead_graph only (in-memory plan, no tickets).

### Step 4: Output the decomposition

Return:

```json
{
  "bead_graph": [...],
  "pattern": "pipeline_with_parallel",
  "domains": ["architecture", "backend", "security", "testing"],
  "tickets": {
    "parent": "TICKET-123",
    "nodes": {
      "node-1": "TICKET-124",
      "node-2": "TICKET-125",
      "node-3": "TICKET-126",
      "node-4": "TICKET-127"
    }
  },
  "coverage_gaps": [],
  "task": "Build a REST API with auth and tests"
}
```

If `bd` is absent, omit the `tickets` key.

---

## Domain Precision Rules

- **Only include domains where real work exists.** If a domain has no steps, don't include it.
- **Avoid speculative domains.** If you're unsure, ask for clarification or under-specify.
- **Check coverage.** If a domain has no installed agent, flag it as a `coverage_gap`.

---

## Decomposition Examples

### Example 1: REST API with Auth + Tests

**Task:** "Build a REST API with auth and tests"  
**Domains:** backend, security, testing

**DAG:**
```
node-1 (architecture): Create plan
├─ node-2 (backend): Implement API [deps: node-1]
└─ node-3 (security): Design auth [deps: node-1, parallel: true]
   └─ node-4 (testing): Write tests [deps: node-2, node-3]
```

**Pattern:** pipeline_with_parallel

---

### Example 2: Mobile App Redesign

**Task:** "Redesign mobile app UI and fix backend performance"  
**Domains:** frontend, backend, testing

**DAG:**
```
node-1 (frontend): Design new UI
node-2 (backend): Optimize queries [parallel: true]
node-3 (testing): Test both [deps: node-1, node-2]
```

**Pattern:** fan_out_then_fan_in

---

## Next Steps

After decompose completes, use `/invokerai:spawn` to select agents and execute the DAG.
