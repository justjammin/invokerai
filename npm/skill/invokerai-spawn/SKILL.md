---
name: invokerai:spawn
description: Execute the bead-graph DAG. Select agents from agent-map, spawn via your Agent tool in order, manage BEADS lifecycle (close+prune).
---

# invokerai:spawn — Agent Execution

Execute the bead-graph decomposition. Select the right agents, spawn them in DAG order, track via BEADS, and confirm completion.

---

## Core Principle

**The skill is the planner. You are the executor.**

This skill:
- Guides you through the DAG
- Selects the best-match agent for each step
- Tracks execution via BEADS (if available)
- Confirms completion + cleanup

You:
- Spawn each agent using your own Agent tool (never the skill)
- Monitor execution
- Report results back to the skill

---

## What You Do

### Step 1: Load the decomposition

Receive the bead_graph from invokerai:decompose:

```json
{
  "bead_graph": [
    {"id": "node-1", "domain": "architecture", "action": "...", "deps": [], "parallel": false},
    {"id": "node-2", "domain": "backend", "action": "...", "deps": ["node-1"], "parallel": false},
    ...
  ],
  "tickets": {
    "parent": "TICKET-123",
    "nodes": {"node-1": "TICKET-124", ...}
  }
}
```

### Step 2: Select agents for each node

For each node in the bead_graph:

1. Look up the node's domain in `~/.invoker/agent-map.json`.
2. Read the agents in that domain.
3. Choose the best match: whose frontmatter description most closely matches the node's `action`.
4. If no agents in that domain: fall back to a general-purpose agent and note the gap.

Example:

```
node-1 (domain: architecture, action: "Create implementation plan")
  → agent-map["architecture"] = [architect-reviewer, software-architect]
  → best match: architect-reviewer (description mentions "implementation plan")
  → selected: architect-reviewer
```

### Step 3: Spawn agents in DAG order

Process the nodes in dependency order:

1. **Identify the first level:** nodes with `deps: []` (no dependencies).
2. **Spawn all level-1 nodes:** For each node, spawn the selected agent via YOUR OWN Agent tool.
3. **Wait for completion:** Monitor execution. When all level-1 agents complete, record results.
4. **Mark as running (BEADS):** If `bd` is available, mark the corresponding tickets as running:
   ```bash
   bd update TICKET-124 --status running
   ```
5. **Next level:** Identify nodes whose deps are all satisfied. Spawn them (respecting `parallel: true` flags for concurrent execution).
6. **Repeat:** Until all nodes are spawned and completed.

**Parallelism:** Nodes at the same level with `parallel: true` can be spawned simultaneously. Nodes at different levels still respect dependency order.

### Step 4: BEADS lifecycle (critical)

**Mark running:**
When a node's agent is spawned, update the ticket:
```bash
bd update <ticket_id> --status running
```

**Mark complete:**
When an agent completes, mark the ticket done:
```bash
bd close <ticket_id> --reason "Completed by <agent_name>"
```

**Prune (delete):**
After closing, DELETE the ticket from the store to keep `.beads` small:
```bash
bd delete <ticket_id>
```

**Why prune?** The .beads store can grow unbounded. Pruning after each run keeps it manageable (~MB, not GB). Tickets accumulate if not deleted — this is a known runaway risk.

**If `bd` is absent:**
Skip all BEADS operations. Proceed normally with no tracking. Spawn proceeds without tickets.

**BEADS failures never block spawning.** If a `bd` command fails (e.g., `bd` not installed, store corrupted), log the error but continue spawning.

### Step 5: Confirm completion

After all nodes are spawned and completed:

1. If `bd` available:
   - Verify all node tickets are closed.
   - Prune any remaining tickets.
   - Confirm the parent epic is marked done (optional; parent lifecycle is your choice).
   - Report: "All tickets closed + pruned. Store clean."

2. If `bd` absent:
   - Confirm all agents executed and reported results.
   - Report: "All agents completed. (bd unavailable, no tracking)"

---

## Example Execution

**DAG:**
```
node-1 (architect-reviewer): Create plan [TICKET-124]
├─ node-2 (backend-developer): Implement API [TICKET-125, depends: node-1]
└─ node-3 (security-engineer): Design auth [TICKET-126, depends: node-1, parallel: true]
   └─ node-4 (test-automator): Write tests [TICKET-127, depends: node-2 + node-3]
```

**Your execution flow:**

1. **Level 1:**
   - Spawn architect-reviewer for node-1
   - Mark TICKET-124 running: `bd update TICKET-124 --status running`

2. **Wait for architect-reviewer to complete**
   - Close TICKET-124: `bd close TICKET-124 --reason "Completed by architect-reviewer"`
   - Prune TICKET-124: `bd delete TICKET-124`

3. **Level 2 (parallel):**
   - Spawn backend-developer for node-2
   - Spawn security-engineer for node-3 (parallel)
   - Mark TICKET-125 running: `bd update TICKET-125 --status running`
   - Mark TICKET-126 running: `bd update TICKET-126 --status running`

4. **Wait for both to complete**
   - Close + prune TICKET-125, TICKET-126

5. **Level 3:**
   - Spawn test-automator for node-4
   - Mark TICKET-127 running: `bd update TICKET-127 --status running`

6. **Wait for completion**
   - Close + prune TICKET-127

7. **Confirm:**
   - All tickets closed + pruned
   - Parent epic TICKET-123 status: done (optional)
   - Report: "Execution complete. 3 agents spawned, 4 steps completed."

---

## Error Handling

### Agent fails

If an agent reports an error or incomplete work:

1. Decide: continue or retry?
2. If retry: spawn the agent again for the same node.
3. If continue: mark the ticket with a note (e.g., `bd update TICKET-125 --note "Partial success, will retry in next phase"`) and move on.
4. If stop: close remaining tickets and prune. Report the failure.

### bd command fails

If a `bd` command fails (e.g., `bd` not installed, store corrupted):

1. Log the error: "BEADS error: <error message>"
2. **Continue spawning.** Tickets are optional; the DAG is not.
3. Proceed without tracking.

### Coverage gap (domain has no agent)

If a domain has no installed agent:

1. Spawn a general-purpose agent (e.g., `multi-agent-coordinator`, `specialized-developer-advocate`).
2. Note the gap: "Coverage gap: domain 'blockchain' has no specialist agent; using fallback."
3. Recommend to the caller: "Add a blockchain-engineer agent to ~/.claude/agents/."

---

## Skill Bypass

When running inside other skill invocations (`/graphify`, `/kyoko`, `/hyperframes`, `/remotion`, `/weave`, etc.), those skills manage their own agent spawning. InvokerAI spawn applies only to direct orchestrator tasks.

---

## Next Steps

After spawn completes:

- Confirm all work is done (agents executed, tickets pruned).
- Collect results from spawned agents.
- Return final summary to the caller.

---

## Reference

- **~/.invoker/agent-map.json** — Domain-to-agent mapping (built by setup).
- **~/.claude/agents/*.md** — Agent definitions with tools, model, description.
- **.beads/** — Ticket store (if `bd` installed).
- **Node structure:** `{id, domain, action, deps, parallel, agent}`.
- **Ticket structure:** `{parent: TICKET-123, nodes: {node-id: TICKET-id, ...}}`.
