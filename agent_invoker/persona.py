from __future__ import annotations

from agent_invoker.domains import (
    _ROLE_DOMAIN,
    _SUBDOMAIN_TRIGGERS,
    _TIER3_TRIGGERS,
    _CAVEMAN_PREFIX,
    _read_agent_body,
    _resolve_agent_file,
    _normalize_role,
)


def _load_persona(role: str, task: str = "") -> dict:
    normalized = _normalize_role(role)
    domain = _ROLE_DOMAIN.get(normalized)
    t = task.lower()
    tiers: list[str] = []

    if domain:
        tier1_file = _resolve_agent_file(f"{domain}.md")
        if tier1_file:
            tiers.append(_read_agent_body(tier1_file))

            subdomain: str | None = None
            for d, sub, keywords in _SUBDOMAIN_TRIGGERS:
                if d == domain and any(kw in t for kw in keywords):
                    subdomain = sub
                    break

            if subdomain:
                tier2_file = _resolve_agent_file(f"{domain}/{subdomain}.md")
                if tier2_file:
                    tiers.append(_read_agent_body(tier2_file))

                    for d, sub, specialist, keywords in _TIER3_TRIGGERS:
                        if d == domain and sub == subdomain and any(kw in t for kw in keywords):
                            tier3_file = _resolve_agent_file(f"{domain}/{subdomain}/{specialist}.md")
                            if tier3_file:
                                tiers.append(_read_agent_body(tier3_file))
                            break

    if tiers:
        composed = "\n\n---\n\n".join(tiers)
        return {
            "resource_uri": f"agent://{role}",
            "system_prompt_fragment": _CAVEMAN_PREFIX + composed[:8000],
        }

    # Flat-file fallback (old naming convention)
    flat_file = _resolve_agent_file(f"{normalized}.md")
    if flat_file:
        return {
            "resource_uri": f"agent://{role}",
            "system_prompt_fragment": _CAVEMAN_PREFIX + _read_agent_body(flat_file)[:8000],
        }

    return {"resource_uri": f"agent://{role}"}
