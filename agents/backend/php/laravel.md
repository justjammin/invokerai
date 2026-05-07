---
name: laravel
tier: 3
domain: backend
subdomain: php
description: "Laravel-specific patterns"
---

# Laravel

Eloquent: eager load with `->with()`. Scope complex queries to named scopes, not in controller. Use `->chunk()` for large datasets.

Queues: always use for email/notification/3rd-party calls. Never in request cycle. Configure failed queue handler.

Authorization: use policies for model-level checks, gates for app-level. Not inline `if` checks in routes.

Service container: use for dependency injection. Auto-wire implementations in config.

Middleware: request transformation, validation, logging. Not business logic.

## Don'ts

- Logic in routes/web.php (move to controllers then services)
- `DB::select()` raw in controllers (use query builder or Eloquent)
- `env()` calls outside config (fetch from config in app)
- Email synchronously in request handler (use queue)
- Authorization checks in views (use policies)
