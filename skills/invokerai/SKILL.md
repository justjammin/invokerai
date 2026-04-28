---
name: invokerai
description: Agent routing brain — given a task, returns the optimal specialist agent, routing decision, and tools list. Call before spawning any agent. Auto-configures if not present.
---

# InvokerAI — Agent Router

InvokerAI routes tasks to the right specialist using a deterministic + ML classifier. It returns the agent role, routing decision (direct/orchestrate), confidence score, and tools list.

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

Always call `mcp__invokerai__route_task` before spawning an agent:

```
mcp__invokerai__route_task(task="fix the null check in auth middleware")
→ {
    "routing": "direct",
    "role": "debugger",
    "confidence": 91,
    "tools": ["Read", "Bash", "Grep", "Edit", "mcp__lean-ctx__ctx_read", ...]
  }
```

## Routing rules

| Result | Action |
|--------|--------|
| `routing == "direct"` | Spawn `role` agent with returned `tools` |
| `routing == "orchestrate"` | Use multi-agent coordination |
| `confidence < 50` | Ask user to clarify before routing |
| `role == null` + orchestrate | Decompose task, assign roles per sub-task |

## CLI (direct use)

```bash
# Route a task
invoker "fix the null check in auth middleware"

# Use custom agent registry
invoker --registry ./my-agents.json "deploy the api"

# Bulk add tools to all agents
invoker tools add --all mcp__lean-ctx__ctx_read mcp__lean-ctx__ctx_shell

# Add tools to a category
invoker tools add --category backend WebSearch WebFetch

# Remove tools from specific agents
invoker tools remove --agents debugger,code-reviewer some_tool

# List tools for an agent
invoker tools list debugger

# Router status
invoker --model-info
```

## Build router (required for ML routing)

```bash
python scripts/build_router.py          # Phase 1: TF-IDF + kNN
python scripts/build_router.py --phase 2  # Phase 2: mpnet + RandomForest
```

Phase 2 requires: `pip install agent-invoker[embeddings]`

## Custom agents

Add agents without touching the default registry:

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