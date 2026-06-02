from __future__ import annotations

import json
import time
import re
from pathlib import Path

from agent_invoker import classifier
from agent_invoker.registry.loader import load_registry

_SESSION_LOG = Path.home() / ".claude" / "logs" / "invokerai-sessions.md"
_LEDGER_PATH = Path.home() / ".invokerai" / "ledger.json"
_LEDGER_TTL = 1800
TRAINING_LOG_PATH = Path.home() / ".invokerai" / "training.jsonl"
AUTO_TRAIN_THRESHOLD = 50

_HANDOFF_DIR = Path.home() / ".invokerai" / "handoff"
_PROJECT_MEMORY_PATH = Path.home() / ".invokerai" / "project_memory.json"


def append_session_log(task: str, role: str | None, confidence: int, routing: str, domains: list[str] | None, duration: str = "") -> None:
    try:
        date = time.strftime("%Y-%m-%d")
        short_task = (task[:77] + "...") if len(task) > 80 else task
        short_task = short_task.replace("\n", " ").strip()
        domains_str = ", ".join(domains) if domains else "—"
        entry = (
            f"\n### {date} — {short_task}\n"
            f"- **Role selected:** {role or 'unknown'}\n"
            f"- **Confidence:** {confidence}\n"
            f"- **Routing:** {routing}\n"
            f"- **Domains passed:** {domains_str}\n"
            f"- **Wall-clock:** {duration}\n"
        )
        _SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _SESSION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception:
        pass


def get_session(session_id: str) -> dict:
    now = time.time()
    try:
        data: dict = json.loads(_LEDGER_PATH.read_text()) if _LEDGER_PATH.exists() else {}
    except Exception:
        data = {}
    stale = [k for k, v in data.items() if now - v.get("last_seen", 0) > _LEDGER_TTL]
    for k in stale:
        del data[k]
    if session_id not in data:
        data[session_id] = {"active_role": None, "prior_routes": [], "last_seen": now}
    data[session_id]["last_seen"] = now
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_PATH.write_text(json.dumps(data))
    except Exception:
        pass
    return data[session_id]


def update_session(session_id: str, role: str | None, routing: str) -> None:
    s = get_session(session_id)
    s["active_role"] = role
    s["prior_routes"].append({"role": role, "routing": routing, "ts": int(time.time())})
    if len(s["prior_routes"]) > 20:
        s["prior_routes"] = s["prior_routes"][-20:]
    # Set handoff_backend once at session creation; never overwrite.
    if "handoff_backend" not in s:
        s["handoff_backend"] = "file"
    try:
        data: dict = json.loads(_LEDGER_PATH.read_text()) if _LEDGER_PATH.exists() else {}
    except Exception:
        data = {}
    data[session_id] = s
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_PATH.write_text(json.dumps(data))
    except Exception:
        pass


def _is_valid_role(role: str) -> bool:
    """Check role against the trusted (built-in) registry. Never use a caller-supplied registry."""
    if not role or not isinstance(role, str):
        return False
    try:
        registry = load_registry()
    except Exception:
        return False
    return role in registry


def record_accepted_routing(task: str, role: str, routing: str) -> None:
    if not _is_valid_role(role):
        return
    try:
        TRAINING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRAINING_LOG_PATH.open("a") as f:
            f.write(json.dumps({"ts": int(time.time()), "task": task, "role": role, "routing": routing}) + "\n")
        count = sum(1 for _ in TRAINING_LOG_PATH.open())
        if count >= AUTO_TRAIN_THRESHOLD and count % AUTO_TRAIN_THRESHOLD == 0:
            _auto_train(count)
    except OSError:
        pass


def _auto_train(count: int) -> None:
    import sys
    try:
        examples = []
        for ln in TRAINING_LOG_PATH.read_text().splitlines():
            try:
                e = json.loads(ln)
                examples.append((e["task"], f"{e['routing']}|{e['role']}"))
            except Exception:
                continue
        if len(examples) < 10:
            return
        classifier.build(examples, phase=1)
        print(
            f"\n[invokerai] Auto-trained classifier on {count} confirmed routings.\n"
            f"  Run 'invoker train --phase 2' for higher accuracy after 200+ examples.\n",
            file=sys.stderr,
        )
    except Exception:
        pass


def _sanitize_session_id(session_id: str) -> str:
    """Strip anything outside [a-zA-Z0-9_-]. Raise ValueError if result empty."""
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '', session_id or "")
    if not cleaned:
        raise ValueError("invalid session_id")
    return cleaned


def _get_session_handoff_backend(session_id: str) -> str:
    """Return the handoff_backend for session_id. Always 'file' — mail backend removed."""
    return "file"


def read_handoff(session_id: str) -> dict:
    safe_id = _sanitize_session_id(session_id)
    path = _HANDOFF_DIR / f"{safe_id}.json"
    if not path.resolve().is_relative_to(_HANDOFF_DIR.resolve()):
        raise ValueError("path traversal detected")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def write_handoff(
    session_id: str,
    role: str,
    task: str,
    decisions: list[str] | None = None,
    open_questions: list[str] | None = None,
    files_touched: list[str] | None = None,
) -> dict:
    safe_id = _sanitize_session_id(session_id)
    existing = read_handoff(safe_id)
    step = {"role": role, "task": task, "ts": int(time.time())}
    updated = {
        "session_id": safe_id,
        "last_updated": int(time.time()),
        "steps_completed": existing.get("steps_completed", []) + [step],
        "decisions": existing.get("decisions", []) + (decisions or []),
        "open_questions": existing.get("open_questions", []) + (open_questions or []),
        "files_touched": existing.get("files_touched", []) + (files_touched or []),
    }
    _HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    path = _HANDOFF_DIR / f"{safe_id}.json"
    if not path.resolve().is_relative_to(_HANDOFF_DIR.resolve()):
        raise ValueError("path traversal detected")
    try:
        path.write_text(json.dumps(updated, indent=2))
    except OSError:
        pass
    return updated


def get_project_memory(project_id: str) -> dict:
    if not _PROJECT_MEMORY_PATH.exists():
        return {}
    try:
        data = json.loads(_PROJECT_MEMORY_PATH.read_text())
        return data.get(project_id, {})
    except Exception:
        return {}


def update_project_memory(project_id: str, role: str, domains: list[str] | None = None) -> None:
    try:
        data: dict = json.loads(_PROJECT_MEMORY_PATH.read_text()) if _PROJECT_MEMORY_PATH.exists() else {}
        entry = data.get(project_id, {"role_counts": {}, "last_domains": [], "last_updated": 0})
        entry["role_counts"][role] = entry["role_counts"].get(role, 0) + 1
        if domains:
            entry["last_domains"] = domains
        entry["last_updated"] = int(time.time())
        data[project_id] = entry
        _PROJECT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PROJECT_MEMORY_PATH.write_text(json.dumps(data))
    except OSError:
        pass


def patch_session_log_outcome(date: str, task_prefix: str, corrections: int, accepted: bool) -> dict:
    """Append correction/acceptance metrics to an existing session log entry.

    Matches the first entry whose header starts with ``### {date} — {task_prefix}``
    and inserts two outcome bullet points immediately after it.  Returns
    ``{"ok": True}`` on success or ``{"ok": False, "error": "..."}`` on failure.
    """
    try:
        if not _SESSION_LOG.exists():
            return {"ok": False, "error": "entry not found"}
        text = _SESSION_LOG.read_text(encoding="utf-8")
        header_prefix = f"### {date} — {task_prefix}"
        lines = text.split("\n")
        header_idx = next(
            (i for i, ln in enumerate(lines) if ln.startswith(header_prefix)),
            -1,
        )
        if header_idx == -1:
            return {"ok": False, "error": "entry not found"}
        insert_idx = len(lines)
        for j in range(header_idx + 1, len(lines)):
            if lines[j].startswith("### ") or lines[j].strip() == "":
                insert_idx = j
                break
        outcome_lines = [
            f"- **Correction cycles:** {corrections}",
            f"- **First-pass accepted:** {'yes' if accepted else 'no'}",
        ]
        lines[insert_idx:insert_idx] = outcome_lines
        _SESSION_LOG.write_text("\n".join(lines), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
