---
name: devops
tier: 1
description: "Universal devops domain rules"
---

# Roleplay Notes

- Docker: multi-stage builds (build ≠ runtime image)
- Container users: run as non-root UID, never root
- Image size: minimize layers
- Secrets: vault/secrets manager only
- No secrets: in env files, image layers, or commits
- Secrets injection: at runtime
- Health checks: endpoint required before load balancer registration
- Liveness: can restart?, readiness: can handle traffic?
- Metrics: Prometheus endpoint, standard format
- Alerts: on error rate, p95 latency, saturation (CPU, memory, connections)
- Baselines: establish before alerting
- Deployment: blue-green or canary for stateful changes
- Hard cutover: never
- Rollback: tested and ready
- Graceful shutdown: drain in-flight requests
- SIGTERM: handler present with timeout (e.g., 30s drain then SIGKILL)
- Resource limits: CPU cores and memory on every container
- Constraint: Request <= Limit (Request > Limit is error)
- Load testing: required for all resource configurations

## Don'ts

- `latest` tag in prod manifests
- Hardcoded IPs/hostnames
- Skip liveness/readiness distinction
- Expose debug endpoints in prod

## Code Quality

Generate code, then score 0–100. Do not output until score ≥ 90.

| Score | Meaning |
|-------|---------|
| 90–100 | Indistinguishable from senior human in this codebase |
| 70–89 | Mostly natural, minor AI tells remain |
| 50–69 | Still reads AI-generated |
| < 50 | Clearly AI — re-run pipeline |

Pipeline (run in order, stop when ≥ 90):

1. **Strip obvious comments** — remove any comment restating adjacent code, empty TODOs, section dividers. Keep: non-obvious WHY, workaround refs, public API docblocks.
2. **Collapse needless helpers** — inline single-use fns ≤5L where name isn't a domain term and it's not an async boundary or named test fixture.
3. **Deflate names** — remove type/role tokens: `userData` → `user`, `handleClickEvent` → `onClick`, `UserDataManager` → `Users`. As short as call site makes unambiguous.
4. **Remove defensive noise** — drop null checks on type-guaranteed non-null, try/catch on code that cannot throw, unreachable else. Keep guards at public API boundaries.
5. **Match surrounding style** — infer quote style, semicolons, trailing commas, brace style from 2–3 files the human owns. Not the linter config.
6. **Intentional slop** — drop redundant parens where precedence obvious, collapse `x ? true : false` → `!!x`, drop `return undefined` at end of void fns. Equivalent rewrites only — never change semantics.
