from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_REGISTRY = Path(__file__).parent / "agents.json"
_cache: dict[str, "Agent"] | None = None


@dataclass
class Agent:
    id: str
    category: str
    description: str
    domains: list[str]
    triggers: list[str]
    tools: list[str]
    orchestrate: bool = False


def load_registry(custom_registry: str | Path | None = None) -> dict[str, Agent]:
    global _cache
    if _cache is not None and custom_registry is None:
        return _cache

    agents = _load_file(_DEFAULT_REGISTRY)

    if custom_registry is not None:
        custom_path = Path(custom_registry)
        if custom_path.is_dir():
            for f in sorted(custom_path.glob("*.json")):
                agents.update(_load_file(f))
        elif custom_path.is_file():
            agents.update(_load_file(custom_path))

    if custom_registry is None:
        _cache = agents

    return agents


def _load_file(path: Path) -> dict[str, Agent]:
    data = json.loads(path.read_text())
    return {
        a["id"]: Agent(
            id=a["id"],
            category=a.get("category", ""),
            description=a.get("description", ""),
            domains=a.get("domains", []),
            triggers=a.get("triggers", []),
            tools=a.get("tools", []),
            orchestrate=a.get("orchestrate", False),
        )
        for a in data.get("agents", [])
    }