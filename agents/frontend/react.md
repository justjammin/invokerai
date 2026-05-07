---
name: react
tier: 2
domain: frontend
description: "React-specific patterns for frontend"
---

# React

Hooks: no logic in `useEffect` that belongs in event handlers. `useEffect` is for sync, not for onClick cleanup.

`useMemo`/`useCallback` only when profiling proves benefit—not preemptively. Profile before optimizing.

Keys: stable IDs, never array index for dynamic lists. Unique per sibling, consistent across renders.

Server state: React Query, SWR, or Tanstack Query—not `useEffect` + `useState`. Declarative, automatic caching.

Controlled components: single source of truth. Form library (React Hook Form, Formik) for complex forms.

Props: pass only what's needed. Avoid prop drilling (use context when genuinely shared).

## Don'ts

- Derive state from props in `useEffect` (use `useDerivedState` or recalculate in render)
- Mutate state directly (e.g., `state.push()`)
- Create new objects/arrays in render as props (new ref every render)
- Missing dependency array entries in `useEffect`
- Circular dependencies between components
