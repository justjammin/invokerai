# Changelog

All notable changes to InvokerAI are documented here.

Format: [Semantic Versioning](https://semver.org). Types: Added, Changed, Fixed, Removed.

---

## [Unreleased]

### Gas City Integration
- Optional Gas City runtime for crew routing (INVOKERAI_GASCITY env var: off/auto/on)
- `get_crew_status` MCP tool for crew progress monitoring (pending/running/done/failed per agent)
- Handoff authority locking: session-scoped via `bd` mail or file, never merged
- Persona files written to /tmp/invokerai-*.persona.md, swept at server startup
- GcClient subprocess wrapper with typed error surface and 300s TTL cache
- Default INVOKERAI_GASCITY=off — no behavior change for existing users

### Added
- Confidence-aware dispatch: `spawn_authorized` now gates on confidence ≥ 50. Low confidence (< 50) returns `clarification_needed: true` + `candidates[]`. Medium (50–69) returns `confidence_warning` + optional `runner_up`.
- `reasoning[]` field on `spawn_specialist` and `route_task` responses — explains which trigger fired, runner-ups, confidence source
- Routing feedback loop: `confirm_route` (when confirmed) and `log_outcome` (accepted=True, corrections=0) write to `~/.invokerai/training.jsonl`. Auto-retrains Phase 1 classifier at every 50 confirmed examples.
- Handoff artifact: `get_handoff` / `put_handoff` MCP tools + `prior_handoff` field in spawn response. Agents write structured context (decisions, files, open questions) between crew steps.
- Cross-session project memory: `get_project_context` MCP tool + `--project-id` CLI flag. Tracks role frequency per project. Observability only — does not influence routing.
- `dry_run` param on `spawn_specialist` and `--dry-run` flag on `invoker spawn` — preview routing without side effects.
- `invoker why "task"` CLI command — explains routing decision (matched trigger, runner-ups, confidence). `--json` for machine-readable output.
- Contract negotiation: when `backend` + `frontend`/`mobile` span a crew (without `architecture`), an `api-designer` step is auto-injected before execute phase to define API contract.
- `candidates[]` field on `RoutingResult` — top 2 runner-up roles from inference path.
- `log_outcome` MCP tool now accepts optional `task`, `role`, `routing` params for feedback loop.

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