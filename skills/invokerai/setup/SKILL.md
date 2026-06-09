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

### Step 5: Install the enforcement gate (optional)

The enforcement gate is a best-effort guardrail that keeps the main thread in its
orchestrator-only lane: it blocks direct edits to files **inside the active project repo**
(the git repo the session is `cd`'d in) and nudges you to route specialist work through
`/invokerai:decompose` → `/invokerai:spawn`. Everything outside that repo stays free.
It is **fail-open** (a bug never bricks tools) and has a one-line kill switch.

Templates live in the repo's `enforcement/` directory. If you installed via `npx
invokerai-skills`, that directory is not in the npm payload — clone the repo
(`git clone https://github.com/justjammin/invokerai`) to get it, then use that path as
`<repo>/enforcement` below.

Only do this if the user wants the gate. Run these steps in order.

**1. Create the state directory.**

```bash
mkdir -p ~/.invoker/state
```

**2. Copy the hooks into `~/.claude/hooks/` and mark them executable.**

```bash
mkdir -p ~/.claude/hooks
cp <repo>/enforcement/invoker-gate.js ~/.claude/hooks/invoker-gate.js
cp <repo>/enforcement/invoker-mark.js ~/.claude/hooks/invoker-mark.js
chmod +x ~/.claude/hooks/invoker-gate.js ~/.claude/hooks/invoker-mark.js
```

**3. Install the policy + exempt templates — only if absent (never clobber an existing
policy the user has tuned).**

```bash
[ -f ~/.invoker/gate-policy.json ]  || cp <repo>/enforcement/gate-policy.json  ~/.invoker/gate-policy.json
[ -f ~/.invoker/exempt-paths.json ] || cp <repo>/enforcement/exempt-paths.json ~/.invoker/exempt-paths.json
```

**4. Patch `~/.claude/settings.json` to wire the three hook groups (idempotent, backs up
first).** The packaged `enforcement/patch-settings.js` does this safely — it reads the
JSON, adds a group only if that event does not already reference the target script,
writes a timestamped backup, validates, and writes back:

```bash
node <repo>/enforcement/patch-settings.js ~/.claude/settings.json ~/.claude/hooks
```

It adds (and only if not already present):

| Event | matcher | command |
|-------|---------|---------|
| `PreToolUse` | `Edit\|Write\|MultiEdit\|NotebookEdit\|Task\|Agent` | `node ~/.claude/hooks/invoker-gate.js` |
| `PostToolUse` | `Task\|Agent\|Skill` | `node ~/.claude/hooks/invoker-mark.js` |
| `SubagentStart` | `` (empty — all) | `node ~/.claude/hooks/invoker-mark.js` |

If you prefer not to run the script, back up `settings.json` first
(`cp ~/.claude/settings.json ~/.claude/settings.json.bak.$(date +%s)`) and add those three
groups by hand, deduping by command string so you never double-wire.

**5. Report to the user:**

```
Enforcement gate installed.
- Edits are gated ONLY inside the repo your session is cd'd in. Everything else is free.
- Kill switch: set "mode":"off" in ~/.invoker/gate-policy.json (re-read every call, no restart).
- Allow direct edits in a path: add an entry to "exempt" in ~/.invoker/exempt-paths.json
  ({ "name":"...", "path":"/abs/path", "reason":"..." }), or drop a .invoker-allow-direct
  file in that directory.
- It is fail-open and best-effort: Bash/heredoc writes and out-of-editor runtimes bypass it.
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
