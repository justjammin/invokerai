# InvokerAI MCP API Reference

Complete reference for InvokerAI v0.2.0 MCP server tools, resources, and prompts.

## Overview

InvokerAI exposes a four-tool suite for task routing and specialist agent discovery. All tools communicate via JSON-RPC 2.0 over stdio.

**Quick start:**
```json
{ "task": "fix the authentication bug in the login endpoint" }
→ spawn_specialist(...)
→ { "routing": "direct", "role": "backend-developer", "confidence": 87, ... }
```

Server connection:
- **Entry:** `~/.invokerai/venv/bin/python -m agent_invoker.mcp_server`
- **Protocol:** JSON-RPC 2.0 stdio
- **Version:** 0.2.0

---

## Tools

### `spawn_specialist` — PRIMARY SURFACE

Route a task and return the execution-ready bundle. This is the main entry point — agents should always call this instead of spawning the Agent tool directly.

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
  "routing": "direct" | "orchestrate",
  "role": "backend-developer" | "debugger" | ... | null,
  "confidence": 0-100,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "source": "regex" | "ml",
  "session_id": "default" | "ses_abc123",
  "spawn_authorized": true,
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "You are a senior backend engineer..."
  },
  "orchestrate_guidance": "Task spans multiple domains..."
}
```

**Response fields:**

| Field | Type | Always present | Description |
|-------|------|---|---|
| `routing` | string | ✓ | "direct" for single specialist, "orchestrate" for multi-agent |
| `role` | string \| null | ✓ | Recommended specialist role name |
| `confidence` | number | ✓ | 0–100 confidence score |
| `tools` | array | ✓ | Recommended tool list for the specialist |
| `source` | string | ✓ | "regex" or "ml" — routing source |
| `session_id` | string | ✓ | Session ID (from request or "default") |
| `spawn_authorized` | boolean | ✓ | Always true; confirms token was written |
| `persona` | object | ~ | Persona bundle; omitted if role is null |
| `persona.resource_uri` | string | ✓ | MCP resource URI for full agent profile |
| `persona.system_prompt_fragment` | string | ✓ | Role-specific system prompt (200–500 tokens) |
| `orchestrate_guidance` | string | ~ | Multi-agent coordination hints (only when routing == "orchestrate") |

**Example:**
```json
Request:
{
  "task": "Implement Redis caching for the user profiles endpoint"
}

Response:
{
  "routing": "direct",
  "role": "backend-developer",
  "confidence": 91,
  "tools": ["Read", "Write", "Edit", "Bash"],
  "source": "regex",
  "session_id": "default",
  "spawn_authorized": true,
  "persona": {
    "resource_uri": "agent://backend-developer",
    "system_prompt_fragment": "You are a senior backend engineer with deep expertise in API design, database optimization, and caching strategies. Focus on performance metrics and backward compatibility. When writing code, prefer proven patterns over novel approaches."
  }
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
- If `routing == "direct"`: spawn the returned `role` with the returned `tools` and `system_prompt_fragment`
- If `routing == "orchestrate"`: use multi-agent coordination with the guidance
- If `confidence < 50`: ask the user to clarify the task before routing
- Do NOT bypass this tool when the user names an agent type

---

### `route_task` — READ-ONLY CLASSIFIER

Pure classifier that returns routing + persona bundle without writing a spawn token. Use this for planning or diagnostic purposes.

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
  "routing": "direct" | "orchestrate",
  "role": "backend-developer" | null,
  "confidence": 0-100,
  "tools": ["Read", "Write", "Edit"],
  "source": "regex" | "ml",
  "session_id": "default" | "ses_abc123",
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
  "routing": "direct",
  "role": "debugger",
  "confidence": 78,
  "tools": ["Read", "Bash", "Edit"],
  "source": "ml",
  "session_id": "ses_engineering_session",
  "persona": {
    "resource_uri": "agent://debugger",
    "system_prompt_fragment": "You are an expert systems debugger with strong skills in troubleshooting complex builds and infrastructure issues..."
  }
}
```

---

### `confirm_route` — SUBAGENT SELF-CORRECTION

Called by a spawned subagent on its first turn to verify it was routed correctly. If routing says otherwise, the subagent should adopt the corrected role.

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

List all available specialist agents with their categories and orchestration flags.

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

## Resources

InvokerAI exposes agent profiles as MCP resources using the `agent://` URI scheme.

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

The MCP server maintains an in-memory session ledger for multi-turn coherence.

**Features:**
- Optional `session_id` parameter on all routing tools
- Server tracks `active_role`, `prior_routes`, and last access time per session
- Sessions auto-expire after 30 minutes of inactivity
- No persistence — ledger is in-memory only

**Default behavior:**
- If no `session_id` is provided, uses `"default"` session
- All tools return the session ID in their response

**Use cases:**
- Multi-turn workflows: pass same `session_id` to maintain persona consistency
- Handoff tracking: server logs prior routing decisions
- Re-routing: agents can check prior routes via `get_session_context` (planned)

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

## Version Information

| Component | Version |
|-----------|---------|
| InvokerAI | 0.2.0 |
| MCP Protocol | 2024-11-05 |
| Python | 3.10+ |

---

## See Also

- [Hooks Setup Guide](hooks-guide.md) — Installation and enforcement
- [Migration Guide](migration-guide.md) — Upgrading from v0.1.0
- [Architecture](../ARCHITECTURE.md) — System design decisions
