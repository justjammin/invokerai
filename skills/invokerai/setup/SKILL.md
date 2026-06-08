---
name: invokerai:setup
description: Build the domain→agent mapping from installed agents. Run once or when agents change. Writes ~/.invoker/agent-map.json.
---

# invokerai:setup — Agent Mapping

Build a domain-to-agent mapping from your installed agents. This mapping is the
**source of truth** for available domains in decompose and agent selection in spawn.

---

## What You Do

### Step 0: Load existing map (if any)

Read `~/.invoker/agent-map.json` if it exists. Record the current domain names.
You **must preserve** those names — never rename or remove existing domains.

### Step 1: Scan agent files

Look for agent files in these directories (scan all that exist):

- `~/.claude/agents/`
- `~/.codex/agents/`
- `~/.gemini/agents/`

For each `.md` file, extract the frontmatter:

```yaml
---
name: <agent-name>
description: <one-line description>
tools: <comma-separated list>
model: <model name (optional)>
---
```

Skip files with no `name` field. Collect all agents: `[{name, description, tools, model}]`.

### Step 2: Classify new agents into domains

For agents NOT already in the existing map:

1. Read the agent's `name` and `description`.
2. Assign to a domain using this priority:
   - **Name match:** If the name clearly signals a domain (e.g. `backend-developer` → `backend`), use that.
   - **Description match:** Read the description and assign to the closest domain.
   - **Unmapped:** If no clear domain, assign to `"unmapped"`.
3. Set `source` to `"name"`, `"description"`, or `"unmapped"` accordingly.

**Domain naming rules (critical for resolver compatibility):**
- Use short, lowercase names: `backend`, `frontend`, `testing`, `ml`, `security`, `devops`, `data`, `architecture`, `documentation`, `mobile`.
- For non-engineering domains, use clear short names: `marketing`, `sales`, `design`, `product`, `finance`, `legal`, `hr`, `game-dev`, `research`.
- If an existing domain name in the map already covers the agent, use that exact name.
- Target 15–40 domains total. Avoid per-agent singletons unless genuinely unique.

### Step 3: Write agent-map.json

Write `~/.invoker/agent-map.json` using this exact schema:

```json
{
  "version": 1,
  "platforms": {
    "claude": "/Users/<username>/.claude/agents"
  },
  "domains": {
    "backend": [
      {
        "name": "backend-developer",
        "description": "Expert backend developer...",
        "tools": ["Read", "Write", "Bash"],
        "model": "claude-sonnet-4-6",
        "source": "name"
      },
      {
        "name": "fullstack-developer",
        "description": "...",
        "tools": ["Read", "Write", "Bash", "Edit"],
        "model": "",
        "source": "description"
      }
    ],
    "frontend": [
      {
        "name": "frontend-developer",
        "description": "...",
        "tools": ["Read", "Write", "Edit"],
        "model": "",
        "source": "name"
      }
    ],
    "unmapped": [
      {
        "name": "some-unusual-agent",
        "description": "...",
        "tools": [],
        "model": "",
        "source": "unmapped"
      }
    ]
  }
}
```

**Required fields for every entry (no exceptions):**

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Agent name from frontmatter |
| `description` | string | From frontmatter; empty string `""` if absent |
| `tools` | array | List of strings; empty array `[]` if absent |
| `model` | string | From frontmatter; empty string `""` if absent |
| `source` | string | Must be `"name"`, `"description"`, or `"unmapped"` |

**Top-level required keys:**

| Key | Type | Notes |
|-----|------|-------|
| `version` | integer | Always `1` |
| `platforms` | object | Map of `platform → agents_dir_path`; always include `"claude"` |
| `domains` | object | Map of `domain_name → [agent entries]` |

**Idempotent + additive:**
- Agents already in the map: keep as-is. Do not update or re-classify.
- New agents: append to the matching domain bucket.
- Never remove existing entries.
- Never rename existing domain buckets.

### Step 4: Report

```
Agent map built: ~/.invoker/agent-map.json
Domains: <count> (<name>, <name>, ...)
Agents mapped: <count> new, <count> existing
Unmapped: <count> (run again after adding specialist agents)
```

---

## Why This Exists

`invoker setup` (CLI) builds the map via keyword classification. This sub-skill
uses the host agent's judgment for semantically accurate domain assignment. Both
write the same `~/.invoker/agent-map.json` schema — they are interchangeable.
The map is read by `invokerai:decompose` (domain discovery) and `invokerai:spawn`
(agent selection).

---

## Next Steps

After setup completes, use `/invokerai:decompose` to break a task into a DAG
using the domains in the map, then `/invokerai:spawn` to select and execute agents.
