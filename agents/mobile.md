---
name: mobile
tier: 1
description: "Universal mobile domain rules"
---

# Roleplay Notes

- Frame rate: 60fps target (profile with Android Profiler, Instruments before optimizing)
- Startup: cold start <2s, time-to-interactive <3s
- Network profiling: on 4G (not ideal conditions)
- Offline-first: conflict resolution strategy defined before sync code
- Sync logic: handle user edits while offline then coming online
- Push notifications: handle foreground, background, killed app states
- User consent: opt-in and opt-out clear
- App store compliance: review guidelines before build (iOS HIG, Android Material Design)
- Rejection: don't learn this way — review proactively
- Deep links: invalid/expired links handled gracefully (error or fallback UI)

## Don'ts

- Block main thread with sync IO
- Assume network always available
- Skip platform UX guidelines (HIG for iOS, Material for Android)
- Use deprecated APIs without migration plan
- Store sensitive data in plain SharedPreferences/UserDefaults

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
