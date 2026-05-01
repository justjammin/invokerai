# Changelog

All notable changes to InvokerAI are documented here.

Format: [Semantic Versioning](https://semver.org). Types: Added, Changed, Fixed, Removed.

---

## [Unreleased]

## [0.2.0] — 2026-04-30

### Added
- `spawn_specialist(task)` MCP tool — primary surface, routes + writes spawn token → returns role, persona bundle, `spawn_authorized: true`
- `confirm_route(task, expected_role)` MCP tool — subagent self-correction on first turn
- `list_agents(category?)` MCP tool — discover available specialists with categories
- `persona` field on `RoutingResult` — `{resource_uri, system_prompt_fragment}` loaded from `~/.claude/agents/{role}.md`
- MCP resources: `agent://` URI scheme exposes every agent profile for lazy-load
- MCP prompt: `/route <task>` shortcut
- Session ledger — in-memory, 30-min TTL, zero-config `"default"` session
- Tool annotations (`readOnlyHint`, `idempotentHint`) on read-only tools
- `~/.invokerai/hooks/pre-agent.sh` — B+C hybrid hook: spawn-token gate + `hookSpecificOutput` JSON hard block
- `migrate.py` / `invoker migrate` — upgrades existing installs (purges old echo hooks, rewrites MCP entries)
- Kiro editor support: `~/.kiro/agents/invokerai.json` with `agentSpawn` + `userPromptSubmit` hooks
- `SubagentStart` hook support for Claude Code
- `~/.invokerai/venv/bin/python` as priority-1 MCP entry (fixes silent failures from wrong interpreter)

### Changed
- `mcp_server.py` version bumped to `0.2.0`
- `_mcp_entry()` detection order: venv-first → Homebrew → npm → fallback
- CLAUDE.md node updated to blocking-requirement language referencing `spawn_specialist`
- `setup_claude_code()` now writes MCP entry to `~/.claude.json` (primary) and hooks to `~/.claude/settings.json` (separate)

## [0.1.0] — 2026-04-28

### Added
- `route(task)` — core routing function. Returns `RoutingResult` with routing, role, confidence, tools
- Phase 1 classifier: TF-IDF + `KNeighborsClassifier` via scikit-learn (zero downloads)
- Phase 2 classifier hook: `all-mpnet-base-v2` + `RandomForestClassifier` (local, no API)
- 64-agent curated registry (`agent_invoker/registry/agents.json`) — all LENA agents
- Custom registry support — pass a `.json` file or directory to merge with defaults
- `invoker` CLI — `invoker "task text"` → JSON routing result
- `invoker --model-info` — show current router phase and logged decision count
- `invoker --registry PATH` — use custom agent registry
- `scripts/build_router.py` — generates `~/.invokerai/router.pkl` from labeled examples (50 included)
- `install.py` — Python-based installer (pip install + router build + verify)
- Decision logging to `~/.invokerai/routing_log.jsonl` (feeds Phase 2 training)
- Regex fallback when `router.pkl` not present
- MIT license