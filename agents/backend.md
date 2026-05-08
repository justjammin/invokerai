---
name: backend
tier: 1
description: "Universal backend domain rules"
---

# Roleplay Notes

- HTTP verbs: GET read-only, POST create, PATCH partial, PUT replace, DELETE remove
- Status codes: 200 OK, 201 created, 204 no content, 400 bad req, 401 unauth, 403 forbidden, 404 not found, 409 conflict, 429 rate limit, 500 server error
- POST/PATCH/PUT: idempotent — safe to retry
- API versioning: strategy chosen and documented
- Pagination: `limit/offset` or `cursor` only, never `page/size`
- Error response: `{error: {code, message, details}}` — code is slug
- RBAC: roles assigned, permissions checked per resource
- Token lifecycle: expiry set, refresh rotation, revocation immediate
- Crypto: never roll own — use platform libraries (libsodium, cryptography, etc.)
- Input validation: boundary only — shape, type, length. Reject before processing
- Structured logging: level, timestamp, correlation ID, service name, req path/method, status, duration
- Correlation IDs: passed downstream in headers (trace all related calls)
- Connection pooling: size to workload, test saturation under load
- Async ops: queue-based (Celery, Sidekiq, Bull), don't block request thread
- Rate limiting: per endpoint, per auth principal with defined window + burst
- Integration tests: hit real DB (no mock persistence), real cache if used

## Don'ts

- Verbs in endpoints: `POST /createUser` → `POST /users`
- 1:1 schema-to-endpoint mapping
- Silently swallow exceptions: `catch (Exception $e) { return null; }`
- Log error at catch site AND re-throw (double log upstream)
- Wrap every catch in custom exception for no reason

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
