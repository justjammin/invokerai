---
name: django
tier: 3
domain: backend
subdomain: python
description: "Django-specific patterns"
---

# Django

ORM: `select_related()` for FK, `prefetch_related()` for M2M. Always check query count in tests (assert no N+1). Use `django-debug-toolbar` in dev.

Signals: avoid—use explicit service layer calls instead. Signals make flow non-obvious, hard to test.

Migrations: squash regularly (merge multiple migrations). Never edit applied migrations. Always reversible.

Managers: put query logic here, not in views. Use `QuerySet.as_manager()` for chainable queries.

Middleware: use sparingly. Clear request/response manipulation layer. Avoid data mutation.

## Don'ts

- Business logic in models (use services)
- Fat views (keep <50 lines, move logic to services)
- `objects.all()` without pagination
- Raw SQL without `params=` for user data
- Signals for business logic
