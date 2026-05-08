"""
InvokerAI routing trace — read-only diagnostic.

Traces 3 tasks through the routing pipeline and prints README-quality output.
No log files written, no side effects.

Usage:
    python scripts/trace_example.py
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from agent_invoker.core import (
    route,
    _ROLE_DOMAIN,
    _SUBDOMAIN_TRIGGERS,
    _TIER3_TRIGGERS,
    _REPO_AGENTS_DIR,
)

TASKS = [
    "fix the null pointer in auth middleware",
    "build a FastAPI endpoint with Pydantic validation",
    "add auth, write tests, and document the API",
]

DIVIDER = "━" * 64  # ━ × 64


# ---------------------------------------------------------------------------
# Tier resolution — mirrors _load_persona without calling private functions
# ---------------------------------------------------------------------------

def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            return content[end + 4:].strip()
    return content


def _tok(text: str) -> int:
    return len(text) // 4


def _resolve_tiers(role: str, task: str) -> list[tuple[str, str, int]]:
    """
    Return list of (label, relative_path_or_status, token_count).
    label   — "Tier1" / "Tier2" / "Tier3" / "FlatFile"
    path    — relative path under agents/ or "[not found]"
    tokens  — approximate token count (0 if not found)
    """
    t = task.lower()
    results: list[tuple[str, str, int]] = []
    domain = _ROLE_DOMAIN.get(role or "")

    if domain is None:
        # Flat-file fallback
        rel = f"{role}.md"
        candidate = _REPO_AGENTS_DIR / rel
        if candidate.exists():
            body = _strip_frontmatter(candidate.read_text(encoding="utf-8"))
            results.append(("FlatFile", f"agents/{rel}", _tok(body)))
        else:
            results.append(("FlatFile", f"agents/{rel}", 0))
        return results

    # Tier 1
    tier1_rel = f"{domain}.md"
    tier1_path = _REPO_AGENTS_DIR / tier1_rel
    if tier1_path.exists():
        body = _strip_frontmatter(tier1_path.read_text(encoding="utf-8"))
        results.append(("Tier1", f"agents/{tier1_rel}", _tok(body)))
    else:
        results.append(("Tier1", f"agents/{tier1_rel}", 0))

    # Tier 2
    subdomain: str | None = None
    for d, sub, keywords in _SUBDOMAIN_TRIGGERS:
        if d == domain and any(kw in t for kw in keywords):
            subdomain = sub
            break

    if subdomain is None:
        return results

    tier2_rel = f"{domain}/{subdomain}.md"
    tier2_path = _REPO_AGENTS_DIR / tier2_rel
    if tier2_path.exists():
        body = _strip_frontmatter(tier2_path.read_text(encoding="utf-8"))
        results.append(("Tier2", f"agents/{tier2_rel}", _tok(body)))
    else:
        results.append(("Tier2", f"agents/{tier2_rel} [not found]", 0))

    # Tier 3
    for d, sub, specialist, keywords in _TIER3_TRIGGERS:
        if d == domain and sub == subdomain and any(kw in t for kw in keywords):
            tier3_rel = f"{domain}/{subdomain}/{specialist}.md"
            tier3_path = _REPO_AGENTS_DIR / tier3_rel
            if tier3_path.exists():
                body = _strip_frontmatter(tier3_path.read_text(encoding="utf-8"))
                results.append(("Tier3", f"agents/{tier3_rel}", _tok(body)))
            else:
                results.append(("Tier3", f"agents/{tier3_rel} [not found]", 0))
            break

    return results


# ---------------------------------------------------------------------------
# Tools formatting
# ---------------------------------------------------------------------------

def _format_tools(tools: list[str]) -> str:
    lean_prefix = "mcp__lean-ctx__"
    lean = [t for t in tools if t.startswith(lean_prefix)]
    rest = [t for t in tools if not t.startswith(lean_prefix)]

    parts = [", ".join(rest)] if rest else []
    if lean:
        parts.append(f"mcp__lean-ctx__ (×{len(lean)})")
    return ", ".join(parts) if parts else "(none)"


# ---------------------------------------------------------------------------
# Block renderers
# ---------------------------------------------------------------------------

def _render_route_line(result) -> str:
    display_routing = "direct" if result.spawn_count == 1 else "orchestrate"
    return (
        f"ROUTE    routing={display_routing}"
        f"  role={result.role or '(none)'}"
        f"  confidence={result.confidence}"
        f"  source={result.source}"
        f"  pattern={result.pattern or '(none)'}"
    )


def _render_persona(tiers: list[tuple[str, str, int]]) -> list[str]:
    lines = []
    total_tok = sum(tok for _, _, tok in tiers)
    label_w = max(len(label) for label, _, _ in tiers) if tiers else 5

    for i, (label, path, tok) in enumerate(tiers):
        prefix = "PERSONA  " if i == 0 else "         "
        found = "[not found]" not in path
        tok_str = f"→ {tok:>5} tok" if found else "→ [not found]"
        lines.append(f"{prefix}{label:<8} {path:<40} {tok_str}")

    lines.append(f"         total: {total_tok} tok  (cap: 6 000 chars)")
    return lines


def _render_steps(result) -> list[str]:
    if result.spawn_count == 1:
        return ["STEPS    (none — spawn_count=1 → direct)"]

    lines = ["STEPS"]
    header = f"         {'step':>4}  {'role':<28}  {'action':<35}  parallel"
    lines.append(header)
    lines.append("         " + "-" * (len(header) - 9))
    for step in result.steps:
        parallel_flag = "yes" if step.get("parallel") else "no"
        lines.append(
            f"         {step['step']:>4}  {step['role']:<28}  {step['action']:<35}  {parallel_flag}"
        )
    return lines


def _render_bundle_direct(result) -> list[str]:
    fragment = result.persona.get("system_prompt_fragment", "")
    snippet = fragment[:200] + ("..." if len(fragment) > 200 else "")
    # Indent continuation lines to align under opening """
    indented = snippet.replace("\n", "\n         " + " " * 9)

    lines = [
        "BUNDLE   role=" + (result.role or "(none)"),
        f"         tools=[{_format_tools(result.tools)}]",
        f'         fragment="""',
    ]
    for raw_line in snippet.split("\n"):
        lines.append(f"         {raw_line}")
    lines.append('         """')
    return lines


def _render_bundle_orchestrate(result) -> list[str]:
    return [
        "BUNDLE   role=" + (result.role or "(none)"),
        f"         spawn_count={result.spawn_count}",
        f"         pattern={result.pattern or '(none)'}",
        f"         tools=[{_format_tools(result.tools)}]",
    ]


# ---------------------------------------------------------------------------
# Per-task block
# ---------------------------------------------------------------------------

def trace_task(task: str) -> None:
    print(DIVIDER)
    print(f'INPUT    "{task}"')
    print()

    result = route(task, log=False)

    # ROUTE
    print(_render_route_line(result))
    print()

    # PERSONA
    tiers = _resolve_tiers(result.role or "", task)
    for line in _render_persona(tiers):
        print(line)
    print()

    # STEPS
    for line in _render_steps(result):
        print(line)
    print()

    # BUNDLE
    if result.spawn_count == 1:
        for line in _render_bundle_direct(result):
            print(line)
    else:
        for line in _render_bundle_orchestrate(result):
            print(line)

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    today = datetime.date.today().isoformat()
    print(f"InvokerAI — routing trace  ({today})")
    print()

    for task in TASKS:
        trace_task(task)

    print(DIVIDER)


if __name__ == "__main__":
    main()
