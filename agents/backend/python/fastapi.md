---
name: fastapi
tier: 3
domain: backend
subdomain: python
description: "FastAPI-specific patterns"
---

# FastAPI

Routers: split by domain boundary, not by HTTP method. Group related endpoints logically.

Dependencies: `Depends()` for auth, DB session, pagination—not global state. Dependency injection for testability.

Pydantic v2: `model_config` not `class Config`, `model_validate()` not `.parse_obj()`. Use validators carefully (before model init).

Background tasks: `BackgroundTasks` for fire-and-forget, Celery/RQ for reliable async (with retry, acknowledgment).

Status codes: explicit on mutation endpoints. `201` for create, `204` for delete, `200` for update.

OpenAPI: auto-generated from type hints. Exclude internal endpoints with `include_in_schema=False`.

## Don'ts

- Put business logic in route handlers (move to service layer)
- Use `response_model` to hide validation errors
- Skip `status_code` on mutation endpoints
- Block request on slow operation (use background tasks)
- Mutable default args in Pydantic models
