"""agent_map.py — build/refresh ~/.invoker/agent-map.json.

Scans the user's installed Claude agents (~/.claude/agents/*.md by default),
parses their YAML frontmatter, classifies each agent into a routing domain, and
writes an additive agent-map JSON that `invoker spawn` will read to resolve real
installed agents per domain.

Classification priority (in order):
  1. Exact name match in _ROLE_DOMAIN             → domain, source="name"
  2. description text through _collect_matches    → domain, source="description"
  3. Fallback                                     → domain="unmapped", source="unmapped"
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from agent_invoker.domains import _ROLE_DOMAIN
from agent_invoker.registry.loader import load_registry

_DEFAULT_AGENTS_DIR = Path.home() / ".claude" / "agents"
_DEFAULT_MAP_PATH = Path.home() / ".invoker" / "agent-map.json"

_MAP_VERSION = 1


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Return parsed YAML frontmatter dict, or None if absent/invalid."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    yaml_block = text[3:end].strip()
    try:
        data = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _normalize_tools(raw: Any) -> list[str]:
    """Normalise tools field from either 'a, b, c' string or YAML list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    # string form: "Read, Write, Edit" or "Read,Write"
    return [t.strip() for t in str(raw).split(",") if t.strip()]


# ---------------------------------------------------------------------------
# Domain classification
# ---------------------------------------------------------------------------

def _classify(name: str, description: str) -> tuple[str, str]:
    """Return (domain, source).

    Priority:
      1. exact name match in _ROLE_DOMAIN → source="name"
      2. _collect_matches on description  → source="description"
      3. fallback                         → source="unmapped"
    """
    # Priority 1 — name match (certain, cheap)
    if name in _ROLE_DOMAIN:
        return _ROLE_DOMAIN[name], "name"

    # Priority 2 — description-based classification via existing registry matcher
    if description:
        from agent_invoker.domains import _collect_matches
        registry = _get_registry()
        matches = _collect_matches(description, registry)
        if matches:
            role = matches[0]["role"]
            domain = _ROLE_DOMAIN.get(role)
            if domain is not None:
                return domain, "description"

    # Priority 3 — unmapped
    return "unmapped", "unmapped"


# Registry singleton for classification (loaded once per build_agent_map call,
# then passed implicitly via module-level cache).
_registry_cache: dict | None = None


def _get_registry() -> dict:
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = load_registry()
    return _registry_cache


# ---------------------------------------------------------------------------
# Map I/O helpers
# ---------------------------------------------------------------------------

def _load_map(map_path: Path) -> dict:
    """Load existing map from disk, returning a valid skeleton if absent/corrupt."""
    if not map_path.exists():
        return {"version": _MAP_VERSION, "platforms": {}, "domains": {}}
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": _MAP_VERSION, "platforms": {}, "domains": {}}
        data.setdefault("version", _MAP_VERSION)
        data.setdefault("platforms", {})
        data.setdefault("domains", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"version": _MAP_VERSION, "platforms": {}, "domains": {}}


def _existing_names(domain_map: dict[str, list]) -> set[str]:
    """Collect all agent names already recorded in any domain bucket."""
    names: set[str] = set()
    for bucket in domain_map.values():
        for entry in bucket:
            if isinstance(entry, dict) and "name" in entry:
                names.add(entry["name"])
    return names


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_agent_map(
    agents_dir: Path | None = None,
    map_path: Path | None = None,
) -> dict:
    """Scan installed agents, classify them by domain, merge into the map file.

    Parameters
    ----------
    agents_dir:
        Directory containing *.md agent files. Defaults to ~/.claude/agents.
    map_path:
        Path to write/update the JSON map. Defaults to ~/.invoker/agent-map.json.

    Returns
    -------
    The full map dict (version/platforms/domains) after the merge.
    """
    global _registry_cache

    agents_dir = agents_dir or _DEFAULT_AGENTS_DIR
    map_path = map_path or _DEFAULT_MAP_PATH

    # Load or initialise the existing map (preserves hand-edits)
    existing = _load_map(map_path)
    domain_map: dict[str, list] = existing["domains"]
    already_known = _existing_names(domain_map)

    new_count = 0
    unchanged_count = 0
    unmapped_count = 0

    for md_file in sorted(agents_dir.glob("*.md")):
        if not md_file.is_file():
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        fm = _parse_frontmatter(text)
        if fm is None:
            continue

        name = fm.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()

        if name in already_known:
            unchanged_count += 1
            continue

        description = str(fm.get("description") or "").strip()
        tools = _normalize_tools(fm.get("tools"))
        model = str(fm.get("model") or "").strip()

        domain, source = _classify(name, description)

        entry: dict[str, Any] = {
            "name": name,
            "description": description,
            "tools": tools,
            "model": model,
            "source": source,
        }

        domain_map.setdefault(domain, []).append(entry)
        already_known.add(name)
        new_count += 1
        if domain == "unmapped":
            unmapped_count += 1

    # Update platform pointer
    existing["platforms"]["claude"] = str(agents_dir)

    # Write map
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    total_unmapped = len(domain_map.get("unmapped", []))
    print(
        f"+{new_count} new, {unchanged_count} unchanged, "
        f"{total_unmapped} total unmapped"
    )

    return existing
