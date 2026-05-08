---
name: frontend
tier: 1
description: "Universal frontend domain rules"
---

# Roleplay Notes

- Components: single responsibility — no god components mixing layout, logic, data fetching
- State: lowest possible owner, lift only when genuinely shared
- Props: pass down explicitly, avoid context for transient/frequently-changing state
- Accessibility: ARIA roles when semantic HTML insufficient
- Keyboard navigation: Tab, Enter, Escape, arrows where applicable
- Color contrast: min 4.5:1 for text, 3:1 for graphics
- Core Web Vitals: LCP <2.5s, CLS <0.1, INP <200ms
- Measure: real devices/networks (not lab only), profile before optimizing
- XSS: never `dangerouslySetInnerHTML` with user data
- Content sanitization: all user-rendered content sanitized
- Server validation: required (client validation is UX only)
- Bundle optimization: lazy load routes, tree shake unused code
- Imports: avoid barrel imports in hot paths (component files)
- Code-splitting: at route boundaries
- Testing: behavior not implementation — test DOM, routing, API calls, not method names

## Don'ts

- `any` in TypeScript when type is determinable
- Unused imports
- `console.log` in committed code
- Inline objects/arrays in JSX props (new ref every render)
- Verify optional chains point to guaranteed-to-exist values

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
