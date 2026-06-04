---
name: invokerai:setup
description: Build the domain→agent mapping from installed agents. Run once or when agents change. Writes ~/.invoker/agent-map.json.
---

# invokerai:setup — Agent Mapping

Build a domain-to-agent mapping from your installed agents. This mapping guides domain classification in decompose and agent selection in spawn.

---

## What You Do

### Step 1: Scan agent files

Look for agent files in these directories (in order, scan all):

- `~/.claude/agents/`
- `~/.codex/agents/` (if present)
- `~/.gemini/agents/` (if present)

For each `.md` file, extract the frontmatter:

```yaml
---
name: <agent-name>
description: <one-line description>
tools: <comma-separated list>
model: <model name (optional)>
---
```

Collect all agents into a list: `[{name, description, tools, model}, ...]`.

### Step 2: Group into domains

Read all descriptions. Use your judgment to propose a **bounded domain taxonomy** (~15-40 named domains). Group related agents under shared domain names.

Examples:
- **backend**: backend-developer, engineering-backend-architect, fullstack-developer
- **frontend**: frontend-developer, design-ui-designer, design-ux-architect
- **testing**: test-automator, testing-api-tester, testing-accessibility-auditor
- **marketing**: marketing-content-creator, marketing-seo-specialist, marketing-social-media-strategist
- **sales**: sales-engineer, sales-account-strategist, sales-discovery-coach

**Critical rules:**
- Aim for ~15-40 domain names (not 200).
- A domain with one agent is fine only if it's genuinely a distinct field (e.g., "blockchain", "healthcare", "legal").
- Avoid per-agent singletons.
- The taxonomy is YOUR judgment call based on what the agents do.

### Step 3: Write agent-map.json

Write `~/.invoker/agent-map.json`:

```json
{
  "version": 1,
  "domains": {
    "backend": [
      {"name": "backend-developer", "description": "...", "tools": [...], "model": "sonnet"},
      {"name": "engineering-backend-architect", "description": "...", "tools": [...], "model": "opus"}
    ],
    "frontend": [
      {"name": "frontend-developer", "description": "...", "tools": [...], "model": "sonnet"}
    ],
    ...
  }
}
```

**Idempotent + additive:**
- If `~/.invoker/agent-map.json` already exists, merge the new agents.
- Keep existing domain buckets and hand-edits.
- Never clobber the file; only add or update agent entries.

### Step 4: Report

Output a summary:

```
Agent map built: ~/.invoker/agent-map.json
Domains: <count> (backend, frontend, testing, marketing, security, ...)
Agents mapped: <count>
Unmapped agents (if any): <list>
```

---

## Why This Exists

The Python CLI `invoker setup` builds a map via keyword classification. This sub-skill uses the main agent's judgment for better, more semantically accurate domain naming. Both write the same `~/.invoker/agent-map.json` file shape, so they can be used interchangeably.

---

## Next Steps

After setup completes, use `/invokerai:decompose` to break a task into a DAG, then `/invokerai:spawn` to select and execute agents.
