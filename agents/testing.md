---
name: testing
tier: 1
description: "Universal testing domain rules"
---

# Testing

Pyramid: unit (fast, isolated) > integration (real deps) > e2e (critical paths only). More units than e2e.

Test behavior and observable output—not method names, not private calls. Test what the user/consumer sees.

Integration tests: real DB, real queue, no mocks of persistence layer. Test against real external service stubs if deterministic.

Flaky test = blocking bug. Fix or delete. Never skip with `@skip` or `@ignore` without ticket+owner.

Coverage: ≥80% on business logic. Exclude getters/setters/boilerplate.

CI: test suite blocks merge on failure. No bypassing (no merge button before green).

Test names describe behavior: `"returns 404 when user not found"` not `"testGetUserFail"`.

## Don'ts

- setUp() longer than test it serves
- One assertion per test when three describe one behavior
- Mock pure functions and simple value objects
- Enforce implementation order via test sequencing
- Test private methods when behavior is tested elsewhere
