from __future__ import annotations

# ---------------------------------------------------------------------------
# core.py — THIN RE-EXPORT SHIM
#
# All logic has been moved to the following modules:
#   domains.py   — constants, tables, shared helpers
#   persona.py   — _load_persona
#   decompose.py — DecomposeResult, decompose, _decompose_internal
#   sessions.py  — session ledger, handoff, project memory, training log
#   router.py    — RoutingResult, route, explain, _regex_score, _log
#
# Every name that was previously importable from agent_invoker.core is
# re-exported here so that existing import paths remain byte-identical.
# ---------------------------------------------------------------------------

# domains
from agent_invoker.domains import (
    _AGENTS_DIR,
    _REPO_AGENTS_DIR,
    _CAVEMAN_PREFIX,
    _ROLE_DOMAIN,
    _SUBDOMAIN_TRIGGERS,
    _TIER3_TRIGGERS,
    _read_agent_body,
    _resolve_agent_file,
    _normalize_role,
    PATTERN_PIPELINE,
    PATTERN_PARALLEL,
    PATTERN_SUPERVISOR,
    PATTERN_FEEDBACK_LOOP,
    PATTERN_HIERARCHICAL,
    PATTERN_PLAN_THEN_EXECUTE,
    _EXPLICIT_DOMAIN_ROLE,
    CANONICAL_DOMAINS,
    _DOMAIN_ROLE_MAP,
    _ROLE_LABELS,
    _CATEGORY_PRIORITY,
    _nli_cache,
    _get_nli_model,
    _count_domains,
    _complexity_score,
    _is_code_review_only,
    _domain_roles,
    _detect_pattern,
    _collect_matches,
    _suggest_role,
)

# persona
from agent_invoker.persona import _load_persona

# decompose
from agent_invoker.decompose import (
    DecomposeResult,
    _generate_steps,
    _generate_steps_v2,
    _decompose_internal,
    decompose,
)

# sessions
from agent_invoker.sessions import (
    _SESSION_LOG,
    _LEDGER_PATH,
    _LEDGER_TTL,
    TRAINING_LOG_PATH,
    AUTO_TRAIN_THRESHOLD,
    _HANDOFF_DIR,
    _PROJECT_MEMORY_PATH,
    append_session_log,
    get_session,
    update_session,
    _is_valid_role,
    record_accepted_routing,
    _auto_train,
    _sanitize_session_id,
    _get_session_handoff_backend,
    read_handoff,
    write_handoff,
    get_project_memory,
    update_project_memory,
    patch_session_log_outcome,
)

# router
from agent_invoker.router import (
    RoutingResult,
    _regex_score,
    _log,
    LOG_PATH,
    PHASE2_MILESTONE,
    route,
    explain,
)
