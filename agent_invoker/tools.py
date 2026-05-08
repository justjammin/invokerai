"""
Bulk tool management for InvokerAI agent registry and agent .md files.

API:
    add_tools(targets, tools, agents_dir, registry_path)
        targets: list of agent ids | "all" | category name | callable filter

    remove_tools(targets, tools, agents_dir, registry_path)

    list_tools(agent_id, agents_dir)

CLI:
    invoker tools add --agents debugger,backend-developer WebSearch WebFetch
    invoker tools add --category backend WebSearch
    invoker tools add --all ctx_read ctx_shell
    invoker tools remove --agents debugger WebSearch
    invoker tools list debugger
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, List, Union

DEFAULT_AGENTS_DIR = Path(__file__).parent.parent / "agents"
DEFAULT_REGISTRY = Path(__file__).parent / "registry" / "agents.json"

TargetSpec = Union[str, List[str], Callable[[dict], bool]]


def add_tools(
    targets: TargetSpec,
    tools: list[str],
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    registry_path: Path = DEFAULT_REGISTRY,
) -> dict[str, list[str]]:
    """
    Add tools to matching agents — updates both .md frontmatter and agents.json.

    Returns dict of {agent_id: final_tools_list} for every agent modified.
    """
    return _apply(targets, tools, mode="add", agents_dir=agents_dir, registry_path=registry_path)


def remove_tools(
    targets: TargetSpec,
    tools: list[str],
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    registry_path: Path = DEFAULT_REGISTRY,
) -> dict[str, list[str]]:
    return _apply(targets, tools, mode="remove", agents_dir=agents_dir, registry_path=registry_path)


def list_tools(
    agent_id: str,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
) -> list[str]:
    """Return current tools list for a single agent from its .md file."""
    md = agents_dir / f"{agent_id}.md"
    if not md.exists():
        return []
    fm = _parse_frontmatter(md.read_text())
    return [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]


# ── internals ────────────────────────────────────────────────────────────────

def _apply(
    targets: TargetSpec,
    tools: list[str],
    mode: str,
    agents_dir: Path,
    registry_path: Path,
) -> dict[str, list[str]]:
    agent_ids = _resolve_targets(targets, agents_dir, registry_path)
    results = {}

    registry = _load_registry(registry_path)

    for agent_id in agent_ids:
        md_path = agents_dir / f"{agent_id}.md"
        current = list_tools(agent_id, agents_dir)

        if mode == "add":
            updated = _merge(current, tools)
        else:
            updated = [t for t in current if t not in tools]

        if set(updated) == set(current):
            continue

        # Update .md file
        if md_path.exists():
            _update_md_tools(md_path, updated)

        # Update agents.json
        if agent_id in registry:
            registry[agent_id]["tools"] = updated
            results[agent_id] = updated

    if results:
        _save_registry(registry, registry_path)

    return results


def _resolve_targets(
    targets: TargetSpec,
    agents_dir: Path,
    registry_path: Path,
) -> list[str]:
    registry = _load_registry(registry_path)

    if targets == "all":
        return list(registry.keys())

    if callable(targets):
        return [aid for aid, data in registry.items() if targets(data)]

    if isinstance(targets, str):
        # Single id or category name
        if targets in registry:
            return [targets]
        # Treat as category
        return [aid for aid, data in registry.items() if data.get("category") == targets]

    if isinstance(targets, list):
        return targets

    return []


def _merge(current: list[str], new: list[str]) -> list[str]:
    seen = set(current)
    return current + [t for t in new if t not in seen]


def _parse_frontmatter(content: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip().strip('"')
    return result


def _update_md_tools(md_path: Path, tools: list[str]) -> None:
    content = md_path.read_text()
    tools_line = "tools: " + ", ".join(tools)
    updated = re.sub(r"^tools:.*$", tools_line, content, flags=re.MULTILINE)
    md_path.write_text(updated)


def _load_registry(registry_path: Path) -> dict[str, dict]:
    data = json.loads(registry_path.read_text())
    return {a["id"]: a for a in data.get("agents", [])}


def _save_registry(registry: dict[str, dict], registry_path: Path) -> None:
    data = json.loads(registry_path.read_text())
    id_map = {a["id"]: i for i, a in enumerate(data["agents"])}
    for agent_id, updated in registry.items():
        if agent_id in id_map:
            data["agents"][id_map[agent_id]] = updated
    registry_path.write_text(json.dumps(data, indent=2) + "\n")