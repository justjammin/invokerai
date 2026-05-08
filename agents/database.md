---
name: database
tier: 1
description: "Universal database domain rules"
---

# Roleplay Notes

- Migrations: always reversible with rollback script alongside forward
- Testing: test on copy before prod
- Drops: never without deprecation (announce, wait 2+ releases)
- Indexes: cover query shape, not just column
- EXPLAIN: run before shipping, test with realistic data volume
- N+1: eager load relationships or batch queries
- Query verification: use logs/profiler to confirm optimization
- Connection pool: sized to workload with configured timeout
- Connection limits: enforced per application
- Transactions: scoped tight with explicit, tested rollback path
- Long transactions: cause lock contention — minimize
- Backup: verify via restore test (not just existence check)
- Backup testing: on non-prod environment regularly
- Schema evolution: additive first
- Deprecation: remove in separate release after deprecation period

## Don'ts

- Raw string queries (parameterized always)
- 1:1 table-to-endpoint mapping
- Migrate without rollback script
- Trust ORM to pick right index — profile and tune

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
