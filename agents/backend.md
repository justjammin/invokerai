---
name: backend
tier: 1
description: "Universal backend domain rules"
---

# Backend

HTTP semantics: use correct verbs (GET read-only, POST create, PATCH partial update, PUT replace, DELETE remove). Status codes: 200 success, 201 created, 204 no content, 400 bad request, 401 unauthorized, 403 forbidden, 404 not found, 409 conflict, 429 rate limit, 500 server error. Idempotency: POST/PATCH/PUT must be safe to retry.

API versioning strategy chosen and documented. Pagination shape consistent: `limit/offset` or `cursor`, never `page/size`. Standardized error response: `{error: {code, message, details}}` — code is machine-readable slug.

Auth/authz: implement RBAC (roles assigned, permissions checked per resource). Token lifecycle enforced: expiry set, refresh rotation, revocation immediate. Never roll own crypto — use platform libraries (libsodium, cryptography, etc).

Input validation: validate at boundary only — shape, type, length checks. Reject before processing.

Structured logging on every request: log level, timestamp, correlation ID (trace all related calls), service name, request path/method, response status, duration. Correlation IDs passed downstream in headers.

Connection pooling: size to workload (not default). Test pool saturation under load.

Async for heavy operations: queue-based (Celery, Sidekiq, Bull), don't block request thread.

Rate limiting: per endpoint, per auth principal. Define clearly: requests/window, burst allowance.

Integration tests: hit real DB—no mocking persistence layer. Real cache if cache used.

## Don'ts

- Generic variable names: `$data`, `$result`, `$response`, `$output`
- Verbs in endpoints: `POST /createUser` → `POST /users`
- 1:1 schema-to-endpoint mapping
- Silently swallow exceptions: `catch (Exception $e) { return null; }`
- Log error at catch site AND re-throw (double log upstream)
- Wrap every catch in custom exception for no reason
- `if ($thing === true)` instead of `if ($thing)`
- `count($arr) > 0` instead of `!empty($arr)`
- `array_push($arr, $val)` instead of `$arr[] = $val`
