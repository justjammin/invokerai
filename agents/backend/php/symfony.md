---
name: symfony
tier: 3
domain: backend
subdomain: php
description: "Symfony-specific patterns"
---

# Symfony

Services: autowired by default, constructor injection, type hints for dependencies. No service locator in business logic.

Messenger: async handlers for side effects (email, webhooks, analytics). Failed transport configured for retry.

Doctrine: repositories for query logic, never EntityManager in controllers. Use Query builder in repositories.

Controllers: thin, delegate to services. Return response (view or JSON).

Events: dispatch for domain events (user created, order shipped). Listeners for side effects.

DependencyInjection: build container in compilation, not at runtime. All services configured in services.yaml.

## Don'ts

- `$container->get()` in business logic (inject via constructor)
- Fat controllers (keep <30 lines)
- Twig logic that belongs in service layer
- Doctrine lazy loading (N+1), use explicit joins
- Direct database calls outside repositories
