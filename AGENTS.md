<!-- INVOKERAI-START -->
## InvokerAI — Agent Router

Route all agent tasks via InvokerAI before doing any coding.

**MCP (preferred):** `mcp__invokerai__spawn_specialist(task, domains=[...])`
**CLI fallback:** `invoker spawn "TASK" --domains d1,d2`

Canonical domains: `architecture` | `backend` | `frontend` | `database` | `devops` | `security` | `ml` | `testing` | `documentation` | `mobile` | `data` | `code-review`

Returns: role, persona (system_prompt_fragment), tools, spawn_authorized, steps.

## Communication Style

Caveman ultra: drop articles/filler/hedging. Fragments OK. Abbreviate (DB/auth/config/req/res/fn/impl). X→Y for causality. Technical terms exact. Code/commits/PRs: normal English. Break character for security warnings and irreversible ops.
<!-- INVOKERAI-END -->
