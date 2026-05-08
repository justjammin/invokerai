---
name: testing
tier: 1
description: "Universal testing domain rules"
---

# Roleplay Notes

- Test pyramid: unit (fast, isolated) > integration (real deps) > e2e (critical paths only)
- Volume: more units than e2e
- Behavior testing: observable output only — not method names or private calls
- Test perspective: what user/consumer sees
- Integration tests: real DB, real queue (no mock persistence layer)
- External stubs: test against real stubs if deterministic
- Flaky tests: blocking bug — fix or delete immediately
- Skip avoidance: `@skip` or `@ignore` requires ticket + owner
- Coverage target: ≥80% on business logic
- Coverage exclusions: getters, setters, boilerplate
- CI requirement: test suite blocks merge on failure (no bypass)
- Test naming: describe behavior — `"returns 404 when user not found"` not `"testGetUserFail"`

## Don'ts

- setUp() longer than test it serves
- One assertion per test when three describe one behavior
- Mock pure functions and simple value objects
- Enforce implementation order via test sequencing
- Test private methods when behavior is tested elsewhere

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
