---
name: frontend
tier: 1
description: "Universal frontend domain rules"
---

# Frontend

Component = single responsibility. No god components mixing layout, logic, and data fetching.

State: lowest possible owner. Lift only when genuinely shared. Pass down via props explicitly. Avoid context for transient/frequently-changing state.

Accessibility: ARIA roles when semantic HTML insufficient. Keyboard navigation required (Tab, Enter, Escape, arrows where applicable). Color contrast min 4.5:1 for text, 3:1 for graphics.

Core Web Vitals: LCP <2.5s, CLS <0.1, INP <200ms. Measure on real devices/networks, not lab only. Profile before optimizing.

XSS: never `dangerouslySetInnerHTML` with user data. Sanitize all user-rendered content. Validate on server too—client validation is UX only.

Bundle: lazy load routes, tree shake unused code. Avoid barrel imports in hot paths (e.g., component files). Code-split at route boundaries.

Test behavior, not implementation detail. Test observable output: DOM, routing, API calls. Skip testing method names or private function calls.

## Don'ts

- `any` in TypeScript when type is determinable
- Unused imports
- `console.log` in committed code
- Optional-chain values that are guaranteed to exist
- Wrap function ref: `() => doThing()` instead of `doThing`
- Inline objects/arrays in JSX props (new ref every render)
