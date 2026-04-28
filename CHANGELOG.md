# Changelog

All notable changes to InvokerAI are documented here.

Format: [Semantic Versioning](https://semver.org). Types: Added, Changed, Fixed, Removed.

---

## [Unreleased]

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