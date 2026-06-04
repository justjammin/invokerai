"""agent_invoker.sdk — Orchestration SDK.

Returns plans and agent definitions; executes nothing.
You bring the runtime and auth.

Public API::

    decompose(task, domains, complexity)  -> DecomposeResult
    load_agent_map(map_path)              -> dict | None
    resolve_plan(task_text, plan, agent_map) -> dict
    compose_agent_definition(node, task)  -> dict
    topological_order(bead_graph)         -> list[list[str]]
    parallel_groups(bead_graph)           -> list[list[str]]
    orchestrate(task, domains, agent_map, map_path) -> dict

No side effects. No network. No spawning. No token writes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# Re-exports from existing internals — no re-implementation.
from agent_invoker.decompose import DecomposeResult, decompose
from agent_invoker.agent_select import load_agent_map, resolve_plan
from agent_invoker.persona import _load_persona

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "decompose",
    "load_agent_map",
    "resolve_plan",
    "compose_agent_definition",
    "topological_order",
    "parallel_groups",
    "orchestrate",
]


# ---------------------------------------------------------------------------
# compose_agent_definition
# ---------------------------------------------------------------------------

def compose_agent_definition(node: dict, task: str) -> dict:
    """Build a plain-dict agent definition from a resolved bead-graph node.

    Parameters
    ----------
    node:
        An enriched node dict carrying at minimum the keys produced by
        ``orchestrate``'s internal join step:
        ``{agent, description, tools, model, id, deps, annotation}``.
        The ``agent`` key is the resolved installed-agent name.
    task:
        The original task string passed to the orchestration call.
        Used to hydrate the persona (subdomain selection, tone, etc.).

    Returns
    -------
    A plain dict shaped like a Claude AgentDefinition::

        {
            "name":        <str>,   # installed agent name
            "description": <str>,   # from agent-map entry
            "prompt":      <str>,   # composed system-prompt fragment
            "tools":       <list>,  # tool grants from agent-map entry
            "model":       <str>,   # model from agent-map entry
        }

    The ``prompt`` value is the dynamic persona the caller passes as the
    subagent system prompt.  It is produced by ``_load_persona`` which stacks
    domain tier-1, tier-2, tier-3, and caveman prefix.  If no persona file is
    found the field is an empty string — callers must handle that case.
    """
    agent_name: str = node.get("agent", "")
    persona = _load_persona(agent_name, task)
    return {
        "name": agent_name,
        "description": node.get("description", ""),
        "prompt": persona.get("system_prompt_fragment", ""),
        "tools": node.get("tools", []),
        "model": node.get("model", ""),
    }


# ---------------------------------------------------------------------------
# DAG-walk helpers
# ---------------------------------------------------------------------------

def topological_order(bead_graph: dict) -> list[list[str]]:
    """Return node ids grouped into dependency-ordered levels.

    Level 0 contains nodes with no dependencies.  Each subsequent level
    contains nodes whose dependencies are all satisfied by earlier levels.
    Nodes within a level are dependency-independent and safe to run
    concurrently.

    Parameters
    ----------
    bead_graph:
        The ``bead_graph`` dict produced by ``decompose()`` (or built manually).
        Must contain a ``"nodes"`` list where each node has ``"id"`` and
        ``"deps"`` keys.

    Returns
    -------
    A list of levels, each level being a list of node ids::

        [["s1"], ["s2", "s3", "s4"], ["s5"], ["s6"]]

    Raises
    ------
    ValueError
        If the graph contains a cycle (cannot be a valid DAG).
    """
    nodes: list[dict] = bead_graph.get("nodes", [])
    if not nodes:
        return []

    remaining_deps: dict[str, set[str]] = {
        n["id"]: set(n.get("deps", [])) for n in nodes
    }
    resolved: set[str] = set()
    levels: list[list[str]] = []

    while remaining_deps:
        level = [
            nid for nid, deps in remaining_deps.items() if deps <= resolved
        ]
        if not level:
            raise ValueError(
                f"Cycle detected in bead_graph — nodes still unresolved: "
                f"{list(remaining_deps.keys())}"
            )
        levels.append(sorted(level))
        resolved.update(level)
        for nid in level:
            del remaining_deps[nid]

    return levels


def parallel_groups(bead_graph: dict) -> list[list[str]]:
    """Return dependency-ordered parallel groups for the bead graph.

    Each group is a list of node ids that are dependency-independent and
    safe to execute concurrently.  A fan-in barrier is implicit: a node
    depending on N prior nodes lands in a later group after all N complete.

    This is equivalent to ``topological_order`` — each level IS a parallel
    group — but exposed as a distinct entry-point with its own docstring for
    clarity in caller code.

    Parameters
    ----------
    bead_graph:
        The ``bead_graph`` dict produced by ``decompose()``.

    Returns
    -------
    A list of groups (same structure as ``topological_order``)::

        [["s1"], ["s2", "s3", "s4"], ["s5"]]

    Raises
    ------
    ValueError
        If the graph contains a cycle.
    """
    return topological_order(bead_graph)


# ---------------------------------------------------------------------------
# orchestrate — high-level convenience
# ---------------------------------------------------------------------------

def orchestrate(
    task: str,
    domains: list[str] | None = None,
    agent_map: dict | None = None,
    map_path: "Path | None" = None,
) -> dict:
    """Compute a fully-resolved, level-ordered execution plan.  Executes nothing.

    This is the single-call entry-point for callers who want a complete,
    ready-to-use plan without wiring together decompose/resolve/compose
    themselves.

    Parameters
    ----------
    task:
        Natural-language description of the task to orchestrate.
    domains:
        Optional explicit domain list (e.g. ``["backend", "frontend"]``).
        When omitted, domains are inferred from the task text.
    agent_map:
        Pre-loaded agent-map dict.  When omitted, loaded from
        ``~/.invoker/agent-map.json`` (or ``map_path`` if given).
    map_path:
        Override the default agent-map path.  Ignored when ``agent_map``
        is supplied directly.

    Returns
    -------
    A plain dict::

        {
            "pattern": <str>,           # MAS orchestration pattern
            "levels": [                 # topological level order
                [                       # each level = concurrent group
                    {
                        "node_id":    <str>,
                        "agent":      <str>,
                        "prompt":     <str>,
                        "tools":      <list>,
                        "model":      <str>,
                        "deps":       <list[str]>,
                        "annotation": <str | None>,
                    },
                    ...
                ],
                ...
            ],
            "coverage_gaps": [...],     # domains with no installed agent
        }

    Zero side effects: no network, no spawn, no token, no file writes.
    """
    # Step 1 — decompose into pattern + bead_graph.
    dr: DecomposeResult = decompose(task, domains=domains)

    # Step 2 — load agent-map if not supplied.
    if agent_map is None:
        agent_map = load_agent_map(map_path) or {"domains": {}}

    # Step 3 — build a crew-routing plan dict that resolve_plan expects.
    plan = {
        "routing": "crew",
        "steps": dr.steps,
        "pattern": dr.pattern,
        "domains": domains or [],
    }

    # Step 4 — resolve roles → installed agent names.
    resolved = resolve_plan(task, plan, agent_map)
    resolved_steps: list[dict] = resolved.get("steps", [])

    # Step 5 — build a lookup index: step number → resolved step.
    # bead_graph node ids are "s{step['step']}" (e.g. "s1", "s2").
    step_by_id: dict[str, dict] = {
        f"s{rs['step']}": rs for rs in resolved_steps
    }

    # Step 6 — flatten agent-map into a name → entry index for tools/model.
    agent_index: dict[str, dict] = {
        entry["name"]: entry
        for bucket in agent_map.get("domains", {}).values()
        for entry in bucket
        if isinstance(entry, dict) and "name" in entry
    }

    # Step 7 — enrich each bead_graph node with resolved agent data.
    enriched_nodes: dict[str, dict] = {}
    for node in dr.bead_graph.get("nodes", []):
        nid = node["id"]
        rs = step_by_id.get(nid, {})
        agent_name: str = rs.get("agent", "general-purpose")
        map_entry: dict = agent_index.get(agent_name, {})
        enriched_nodes[nid] = {
            **node,
            "agent": agent_name,
            "description": map_entry.get("description", ""),
            "tools": map_entry.get("tools", []),
            "model": map_entry.get("model", ""),
        }

    # Step 8 — topological ordering into levels.
    levels_of_ids = topological_order(dr.bead_graph)

    # Step 9 — compose each node into a full agent definition, grouped by level.
    levels_output: list[list[dict]] = []
    for level_ids in levels_of_ids:
        level_nodes = []
        for nid in level_ids:
            enriched = enriched_nodes[nid]
            agent_def = compose_agent_definition(enriched, task)
            level_nodes.append({
                "node_id": nid,
                "agent": agent_def["name"],
                "prompt": agent_def["prompt"],
                "tools": agent_def["tools"],
                "model": agent_def["model"],
                "deps": enriched.get("deps", []),
                "annotation": enriched.get("annotation"),
            })
        levels_output.append(level_nodes)

    return {
        "pattern": dr.pattern,
        "levels": levels_output,
        "coverage_gaps": resolved.get("coverage_gaps", []),
    }
