# InvokerAI MCP API Reference

Full reference for InvokerAI v0.3.0-dev — four core tools, plus four handoff & monitoring tools. Two read-only routing classifiers, one that gates spawning, one for discovery, and three for cross-session context. If you only read one section, make it `spawn_specialist`.

## Overview

Four tools over JSON-RPC 2.0 stdio. That's the whole server. No HTTP, no auth, no config. It starts when your editor starts it and answers every call in milliseconds from a local classifier.

**The 10-second version:**
```json
{ "task": "fix the authentication bug in the login endpoint" }
→ spawn_specialist(...)
→ { "routing": "solo", "role": "backend-developer", "confidence": 87, "spawn_authorized": true, ... }
```

One call. You get the role, the system prompt fragment, the tool list, and a spawn token that authorizes the next Agent call. That's it.

Server connection:
- **Entry:** `~/.invokerai/venv/bin/python -m agent_invoker.mcp_server`
- **Protocol:** JSON-RPC 2.0 stdio
- **Version:** 0.2.0

---

## Tools

### `spawn_specialist` — PRIMARY SURFACE

This is the one. Route a task, write the spawn token, return the execution bundle — all in one call. Agents should always hit this instead of going straight to the Agent tool.

**Description:**  
Route task → write spawn token → return execution bundle. Always call this instead of the Agent tool directly. Returns role, system_prompt_fragment, tools, and spawn authorization.

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "task": {
      "type": "string",
      "description": "Task text to route and authorize"
    },
    "domains": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Explicit domains (optional; shapes multi-agent steps)"
    },
    "custom_registry": {
      "type": "string",
      "description": "Optional path to custom agents JSON"
    },
    "session_id": {
      "type": "string",
      "description": "Session ID for multi-turn coherence (optional)"
    },
    "dry_run": {
      "type": "boolean",
      "description": "Preview routing without side effects (default: false)"
    },
    "project_id": {
      "type": "string",
      "description": "Project identifier for cross-session memory (optional)"
    },
    "complexity": {
      "type": "string",
      "enum": ["low", "medium", "high"],
      "description": "Complexity hint; gates architect plan step (optional)"
    }
  },
  "required": ["task"]
}
```

**Response:**
```json
{
  "routing": "solo" | "crew",
  "role": "backend-developer" | "debugger" | ... | null,
  "confidence": 0-100,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "source": "regex" | "ml",
  "session_id": "default" | "ses_abc123",
  "spawn_authorized": true,
  "reasoning": ["backend task detected", "confidence high"],
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "You are a senior backend engineer..."
  },
  "steps": [...],
  "prior_handoff": {...},
  "project_context": {...},
  "confidence_warning": "...",
  "runner_up": {...},
  "clarification_needed": false,
  "candidates": [...],
  "dry_run": false
}
```

**Response fields:**

| Field | Type | Present when | Description |
|-------|------|---|---|
| `routing` | string | Always | "solo" for single specialist, "crew" for multi-agent |
| `role` | string \| null | Always | Recommended specialist role name |
| `confidence` | number | Always | 0–100 confidence score |
| `tools` | array | Always | Recommended tool list for the specialist |
| `source` | string | Always | "regex" or "ml" — routing source |
| `session_id` | string | Always | Session ID (from request or "default") |
| `spawn_authorized` | boolean | Always (conditional) | Conditional: true when confidence ≥ 50 and not dry_run |
| `reasoning` | array | Always (inference path) | Why this role was picked; trigger that matched, confidence source |
| `persona` | object | role is not null | Persona bundle |
| `persona.resource_uri` | string | persona present | MCP resource URI for full agent profile |
| `persona.system_prompt_fragment` | string | persona present | Role-specific system prompt (200–500 tokens) |
| `steps` | array | routing == "crew" | Multi-agent execution steps |
| `prior_handoff` | object | Handoff file exists | Prior agent session context (decisions, files, questions) |
| `project_context` | object | project_id provided | Cross-session role history; `{project_id, frequent_roles, last_domains}` |
| `confidence_warning` | string | 50 ≤ confidence < 70 | Routing uncertainty message |
| `runner_up` | object | Alongside confidence_warning | Next best role candidate |
| `clarification_needed` | boolean | confidence < 50 | Do NOT spawn; show candidates to user |
| `candidates` | array | clarification_needed=true | Top 2 runner-up role options |
| `dry_run` | boolean | dry_run=true | Confirms preview mode |

**Example — High confidence (≥ 70):**
```json
Request:
{
  "task": "Implement Redis caching for the user profiles endpoint"
}

Response:
{
  "routing": "solo",
  "role": "backend-developer",
  "confidence": 91,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "source": "regex",
  "session_id": "default",
  "spawn_authorized": true,
  "reasoning": ["backend task", "caching pattern", "high confidence"],
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "You are a senior backend engineer with deep expertise in API design, database optimization, and caching strategies. Focus on performance metrics and backward compatibility. When writing code, prefer proven patterns over novel approaches."
  }
}
```

**Example — Medium confidence (50–69):**
```json
Request:
{
  "task": "Optimize the database and improve the API response times"
}

Response:
{
  "routing": "crew",
  "role": "backend-developer",
  "confidence": 62,
  "spawn_authorized": true,
  "confidence_warning": "Routed to backend-developer at 62% confidence. Multiple paths detected: database optimization vs. caching vs. API refactoring. If wrong, call spawn_specialist again with corrected domains.",
  "runner_up": {"role": "database-optimizer"},
  "reasoning": ["multi-domain signal", "medium confidence"],
  ...
}
```

**Example — Low confidence (< 50):**
```json
Request:
{
  "task": "The system is slow"
}

Response:
{
  "routing": null,
  "role": null,
  "confidence": 42,
  "spawn_authorized": false,
  "clarification_needed": true,
  "candidates": [
    {"role": "backend-developer"},
    {"role": "database-optimizer"}
  ],
  "reasoning": ["ambiguous task", "low confidence", "multiple valid paths"]
}
```

**Side effects:**
- Writes spawn token to `~/.invokerai/spawn_token` (epoch timestamp)
- Updates session ledger (if new session_id)
- Logs routing decision to `~/.invokerai/routing_log.jsonl`

**When to use:**
- Always use for task routing
- Always call before spawning an Agent
- Multi-turn workflows: pass same `session_id` for coherence

**Usage rules:**
- If `spawn_authorized == false`: do NOT spawn. Check `clarification_needed` and show `candidates[]` to user if present.
- If `routing == "solo"`: spawn the returned `role` with the returned `tools` and `system_prompt_fragment`
- If `routing == "crew"`: use multi-agent coordination from the `steps[]` array
- If `confidence_warning` present: proceed with primary choice but inform user of runner-up
- If `confidence < 50` (clarification_needed): ask the user to clarify the task before routing
- Do NOT bypass this tool when the user names an agent type

---

### `route_task` — READ-ONLY CLASSIFIER

Okay so — same routing engine as `spawn_specialist`, but no token written. Use this for planning, sub-task routing in an orchestrate flow, or when you want to know where something would land without actually committing to it.

**Description:**  
Classify a task and return the optimal specialist agent with persona bundle. Pure read-only lookup — does not gate Agent spawning. Use spawn_specialist to route AND gate in one call.

**Annotations:**
```json
{
  "readOnlyHint": true,
  "idempotentHint": true
}
```

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "task": {
      "type": "string",
      "description": "Task text to route"
    },
    "custom_registry": {
      "type": "string",
      "description": "Optional path to custom agents JSON"
    },
    "session_id": {
      "type": "string",
      "description": "Session ID for multi-turn coherence (optional)"
    }
  },
  "required": ["task"]
}
```

**Response:**
```json
{
  "routing": "solo" | "crew",
  "role": "backend-developer" | null,
  "confidence": 0-100,
  "tools": ["Read", "Write", "Edit"],
  "source": "regex" | "ml",
  "session_id": "default" | "ses_abc123",
  "reasoning": [...],
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "..."
  }
}
```

**Difference from spawn_specialist:**
- Does NOT write spawn token
- Does NOT authorize Agent spawning
- Does NOT include `spawn_authorized` field
- Useful for: planning, diagnostics, understanding routing without committing

**Example:**
```json
Request:
{
  "task": "Debug why the CI pipeline is timing out",
  "session_id": "ses_engineering_session"
}

Response:
{
  "routing": "solo",
  "role": "debugger",
  "confidence": 78,
  "tools": ["Read", "Bash", "Edit"],
  "source": "ml",
  "session_id": "ses_engineering_session",
  "reasoning": ["debug pattern detected", "ml-high-confidence"],
  "persona": {
    "resource_uri": "agent://debugger",
    "system_prompt_fragment": "You are an expert systems debugger with strong skills in troubleshooting complex builds and infrastructure issues..."
  }
}
```

---

### `confirm_route` — SUBAGENT SELF-CORRECTION

This one's for the spawned agent itself. Call it on your first turn to verify you're actually the right specialist for the task. If the classifier disagrees, you get the corrected persona and adopt it. Self-correcting agents — I thought this was a cool detail when I shipped it.

**Description:**  
Subagent self-correction. Call on your first turn as a subagent to verify you are the correct specialist. If routing says otherwise, adopt the corrected role.

**Annotations:**
```json
{
  "readOnlyHint": true
}
```

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "task": {
      "type": "string",
      "description": "The task you were spawned to handle"
    },
    "expected_role": {
      "type": "string",
      "description": "The role you were spawned as"
    },
    "session_id": {
      "type": "string",
      "description": "Session ID (optional)"
    }
  },
  "required": ["task", "expected_role"]
}
```

**Response:**
```json
{
  "ok": true | false,
  "expected_role": "backend-developer",
  "confirmed_role": "backend-developer" | "debugger",
  "confidence": 0-100,
  "session_id": "default" | "ses_abc123",
  "corrected_persona": {
    "resource_uri": "agent://debugger",
    "system_prompt_fragment": "..."
  }
}
```

**Response fields:**

| Field | Meaning |
|-------|---------|
| `ok` | true if expected_role matches routing or confidence < 50 (inconclusive) |
| `expected_role` | The role you were called with |
| `confirmed_role` | The role routing recommends; == expected_role if ok |
| `confidence` | Confidence in the routing decision |
| `corrected_persona` | Full persona for the corrected role (only if ok == false) |

**Logic:**
```
if (routing_role == expected_role OR routing_confidence < 50):
  ok = true
  confirmed_role = expected_role
else:
  ok = false
  confirmed_role = routing_role
  corrected_persona = persona(routing_role)
```

**Example — Correct route:**
```json
Request:
{
  "task": "Optimize the database query for user lookups",
  "expected_role": "backend-developer"
}

Response:
{
  "ok": true,
  "expected_role": "backend-developer",
  "confirmed_role": "backend-developer",
  "confidence": 89,
  "session_id": "default"
}
```

**Example — Misroute detected:**
```json
Request:
{
  "task": "The API returns 500 errors — investigate the root cause",
  "expected_role": "backend-developer"
}

Response:
{
  "ok": false,
  "expected_role": "backend-developer",
  "confirmed_role": "debugger",
  "confidence": 82,
  "session_id": "default",
  "corrected_persona": {
    "resource_uri": "agent://debugger",
    "system_prompt_fragment": "You are an expert systems debugger..."
  }
}
```

**When to use:**
- Always call this as a subagent on your first turn
- If `ok == false`: adopt the `corrected_role` and `corrected_persona` for your system prompt
- If `ok == true`: proceed with your assigned role

---

### `list_agents` — DISCOVER SPECIALISTS

84+ agents in the default registry. Browse them all or filter by category. Good for building UIs, for discovery, or for when you're adding custom agents and want to check what IDs are already taken.

**Description:**  
List all available specialist agents with their categories and descriptions.

**Annotations:**
```json
{
  "readOnlyHint": true,
  "idempotentHint": true
}
```

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "category": {
      "type": "string",
      "description": "Filter by category (optional)"
    }
  }
}
```

**Response:**
```json
{
  "agents": [
    {
      "id": "backend-developer",
      "category": "engineering",
      "description": "API design, database optimization, server architecture",
      "orchestrate": false
    },
    {
      "id": "debugger",
      "category": "engineering",
      "description": "Systems troubleshooting, root cause analysis, CI/CD issues",
      "orchestrate": true
    },
    {
      "id": "technical-writer",
      "category": "documentation",
      "description": "API docs, user guides, architecture documentation",
      "orchestrate": false
    }
  ]
}
```

**Response fields:**

| Field | Type | Description |
|-------|------|---|
| `agents` | array | List of available specialists |
| `agents[].id` | string | Unique specialist role ID |
| `agents[].category` | string | Category (engineering, documentation, etc.) |
| `agents[].description` | string | Brief description of the specialist's focus |
| `agents[].orchestrate` | boolean | Can this specialist orchestrate multi-agent flows |

**Example:**
```json
Request:
{
  "category": "engineering"
}

Response:
{
  "agents": [
    {
      "id": "backend-developer",
      "category": "engineering",
      "description": "API design, database optimization, server architecture",
      "orchestrate": false
    },
    {
      "id": "debugger",
      "category": "engineering",
      "description": "Systems troubleshooting, root cause analysis, CI/CD issues",
      "orchestrate": true
    }
  ]
}
```

---

### `get_handoff` — READ PRIOR CONTEXT

Agents in a crew can read context left by previous agents in the same session. Read handoff artifact to understand decisions, open questions, and files touched by prior steps.

**Description:**  
Read handoff artifact for a session — context left by previous agents in a crew workflow.

**Annotations:**
```json
{
  "readOnlyHint": true,
  "idempotentHint": true
}
```

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Session ID for this crew step (required)"
    }
  },
  "required": ["session_id"]
}
```

**Response:**
```json
{
  "session_id": "ses_abc123",
  "last_updated": 1705000000,
  "steps_completed": [
    {
      "role": "architect-reviewer",
      "task": "Create implementation plan",
      "ts": 1705000000
    }
  ],
  "decisions": [
    "Use FastAPI for API layer",
    "PostgreSQL for database"
  ],
  "open_questions": [
    "How to handle auth token expiration?"
  ],
  "files_touched": [
    "/src/api/routes.py",
    "/src/models.py"
  ]
}
```

**Response fields:**

| Field | Type | Description |
|-------|------|---|
| `session_id` | string | Session ID |
| `last_updated` | number | Unix timestamp of last update |
| `steps_completed` | array | Prior steps: role, task, timestamp |
| `decisions` | array | Key decisions made by prior agents |
| `open_questions` | array | Unresolved questions for current/next agent |
| `files_touched` | array | Files modified by prior steps |

**Example:**
```json
Request:
{
  "session_id": "ses_auth_flow"
}

Response:
{
  "session_id": "ses_auth_flow",
  "last_updated": 1705000000,
  "steps_completed": [
    {
      "role": "architect-reviewer",
      "task": "Design authentication system",
      "ts": 1705000000
    }
  ],
  "decisions": [
    "JWT tokens with 24h expiration",
    "Refresh tokens stored in HttpOnly cookies"
  ],
  "open_questions": [
    "Should we implement rate limiting on login attempts?"
  ],
  "files_touched": [
    "/src/auth/models.py"
  ]
}
```

---

### `put_handoff` — WRITE CONTEXT FOR NEXT AGENT

Write your progress and context when completing a crew step. Next agent reads this via `get_handoff` to understand what you did, what you decided, and what questions remain.

**Description:**  
Write handoff context after completing a crew step. Subsequent agents in the workflow read this via `get_handoff`.

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Session ID for this crew step (required)"
    },
    "role": {
      "type": "string",
      "description": "Your role / specialist name (required)"
    },
    "task": {
      "type": "string",
      "description": "The task you were asked to complete (required)"
    },
    "decisions": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Key decisions made (optional)"
    },
    "open_questions": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Unresolved questions for next agent (optional)"
    },
    "files_touched": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Absolute file paths modified (optional)"
    }
  },
  "required": ["session_id", "role", "task"]
}
```

**Response:**  
Same shape as `get_handoff` — returns updated artifact.

**Example:**
```json
Request:
{
  "session_id": "ses_auth_flow",
  "role": "backend-developer",
  "task": "Implement JWT authentication",
  "decisions": [
    "Used PyJWT for token management",
    "Refresh tokens expire in 7 days"
  ],
  "open_questions": [
    "Should login endpoint rate-limit failed attempts?"
  ],
  "files_touched": [
    "/src/auth/routes.py",
    "/src/auth/models.py"
  ]
}

Response:
{
  "session_id": "ses_auth_flow",
  "last_updated": 1705000100,
  "steps_completed": [
    {
      "role": "architect-reviewer",
      "task": "Design authentication system",
      "ts": 1705000000
    },
    {
      "role": "backend-developer",
      "task": "Implement JWT authentication",
      "ts": 1705000100
    }
  ],
  "decisions": [...],
  "open_questions": [...],
  "files_touched": [...]
}
```

**When to use:**
- Always call at the end of a crew step
- Before spawning the next agent
- Provide context that saves time for downstream agents

---

### `get_project_context` — CROSS-SESSION PROJECT MEMORY

Track which specialists are used most frequently across projects. Observability only — does not influence routing, but helps understand team patterns.

**Description:**  
Retrieve cross-session project memory — which specialists used most, last active domains, previous project context.

**Annotations:**
```json
{
  "readOnlyHint": true,
  "idempotentHint": true
}
```

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "project_id": {
      "type": "string",
      "description": "Project identifier (required)"
    }
  },
  "required": ["project_id"]
}
```

**Response:**
```json
{
  "project_id": "myrepo",
  "frequent_roles": [
    ["backend-developer", 47],
    ["frontend-developer", 31],
    ["database-optimizer", 12]
  ],
  "last_domains": ["backend", "frontend", "database"],
  "last_updated": 1705000000
}
```

**Response fields:**

| Field | Type | Description |
|-------|------|---|
| `project_id` | string | Project identifier |
| `frequent_roles` | array | [role, count] pairs, sorted by count descending |
| `last_domains` | array | Most recent domains worked on |
| `last_updated` | number | Unix timestamp of last activity |

**Example:**
```json
Request:
{
  "project_id": "invokerai"
}

Response:
{
  "project_id": "invokerai",
  "frequent_roles": [
    ["backend-developer", 73],
    ["code-reviewer", 45],
    ["technical-writer", 28]
  ],
  "last_domains": ["backend", "testing", "documentation"],
  "last_updated": 1705000000
}
```

**When to use:**
- Observability and project insights
- Understanding team specialization patterns
- Planning skill development or hiring
- Does NOT influence routing decisions

---

## Resources

Here's a thing I didn't want to skip — agent profiles are MCP resources, not just data attached to tool responses. That means editors can lazy-load them on demand via `resources/read` instead of bundling the full profile on every routing call.

### Resource format

**URI:** `agent://{role}`  
**MIME type:** `text/markdown`

Resources contain the full agent profile in Markdown format. Use this to lazy-load detailed persona information after routing.

**Example:**
```
Request: resources/read with uri="agent://backend-developer"

Response: { "uri": "agent://backend-developer", "mimeType": "text/markdown", "text": "# Backend Developer\n\nA senior engineer focused on API design and database optimization...\n" }
```

### Accessing resources

1. Get a `resource_uri` from `spawn_specialist`, `route_task`, or `confirm_route`
2. Use MCP's `resources/read` method with that URI
3. Parse the Markdown to extract full persona details

**Why resources:**
- Keeps routing calls fast (persona fragment only)
- Allows lazy-loading of full profiles
- Personas are versioned with agents, not hardcoded
- Compliant with MCP resource protocol

---

## Prompts

InvokerAI registers a `/route` prompt for user-facing routing.

### `route` prompt

**Usage:** `/route <task>`

Tells Claude to route a task through `spawn_specialist` and return the execution bundle.

**Example:**
```
User: /route implement a new payment processing endpoint
→ Calls spawn_specialist("implement a new payment processing endpoint")
→ Returns routing, role, tools, persona
```

---

## Session Ledger

Session state persists to `~/.invokerai/ledger.json` with a 30-minute TTL. Pass the same `session_id` across calls and the server tracks where you've been — active role, prior routes, last seen time. Zero setup.

**Features:**
- Optional `session_id` parameter on all routing tools
- Server tracks `active_role`, `prior_routes`, and last access time per session
- Sessions auto-expire after 30 minutes of inactivity
- Ledger persists to `~/.invokerai/ledger.json` (survives server restarts)

**Default behavior:**
- If no `session_id` is provided, uses `"default"` session
- All tools return the session ID in their response

**Use cases:**
- Multi-turn workflows: pass same `session_id` to maintain persona consistency
- Handoff tracking: server logs prior routing decisions via handoff artifacts
- Re-routing: agents can read prior routes and context

**Example:**
```json
Turn 1:
{
  "task": "Set up user authentication",
  "session_id": "ses_auth_implementation"
}
→ Routes to backend-developer

Turn 2 (same session):
{
  "task": "Add JWT token validation",
  "session_id": "ses_auth_implementation"
}
→ Routes to backend-developer (same persona maintained)

Turn 3 (different session):
{
  "task": "Debug the auth flow",
  "session_id": "ses_new_session"
}
→ May route to debugger (fresh routing)
```

---

## Error Handling

All tools follow JSON-RPC 2.0 error conventions.

**Common errors:**

| Code | Message | Cause |
|------|---------|-------|
| -32602 | task is required | Missing required parameter |
| -32602 | task and expected_role are required | Missing parameter in confirm_route |
| -32603 | Internal error | Routing classifier failed |

**Example error response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "task is required"
  }
}
```

---

## Best Practices

### Always use spawn_specialist for routing
```json
DO:
{ "task": "Implement new feature" }
→ spawn_specialist(...)
→ { "role": "backend-developer", ... }

DON'T:
Call route_task and then spawn Agent separately.
```

### Respect confidence scores
```json
If confidence < 50, ask user to clarify:
→ "I see multiple paths here. Please clarify: are you looking to implement, debug, or document?"

If confidence >= 50, proceed with confidence.
```

### Use confirm_route as a subagent
```
As a spawned specialist on turn 1:
1. Call confirm_route(task, expected_role)
2. If ok == false, adopt corrected_role
3. Proceed with confirmed role
```

### Pass session_id for coherence
```json
For multi-turn workflows:
{ "task": "Set up auth", "session_id": "project_abc" }
→ Turn 1: backend-developer
{ "task": "Add JWT", "session_id": "project_abc" }
→ Turn 2: backend-developer (same session, consistent persona)
```

### Load full personas from resources
```
After spawn_specialist returns:
1. resource_uri = "agent://backend-developer"
2. Call resources/read("agent://backend-developer")
3. Extract system prompt and context hints
4. Use for detailed agent configuration
```

---

---

## Data Files

InvokerAI stores routing decisions, training data, and session state in the home directory.

| File | Purpose |
|------|---------|
| `~/.invokerai/routing_log.jsonl` | All routing decisions (feeds Phase 2 training); one JSON object per line |
| `~/.invokerai/training.jsonl` | Confirmed correct routings; populated by `confirm_route` + `log_outcome` feedback loop |
| `~/.invokerai/ledger.json` | Session state; persists across server restarts with 30-min TTL eviction |
| `~/.invokerai/handoff/{session_id}.json` | Per-session agent handoff artifacts; written by `put_handoff`, read by `get_handoff` |
| `~/.invokerai/project_memory.json` | Cross-session project role frequency; read by `get_project_context` |
| `~/.invokerai/spawn_token` | Single-use spawn authorization token (epoch timestamp) |
| `~/.invokerai/router.pkl` | Trained classifier (Phase 1 or 2); generated by `scripts/build_router.py` |

---

## Version Information

| Component | Version |
|-----------|---------|
| InvokerAI | 0.3.0-dev |
| MCP Protocol | 2024-11-05 |
| Python | 3.10+ |

---

## See Also

- [Hooks Setup Guide](hooks-guide.md) — Installation and enforcement
- [Migration Guide](migration-guide.md) — Upgrading from v0.1.0
- [Architecture](../ARCHITECTURE.md) — System design decisions
