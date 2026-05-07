---
name: typescript
tier: 2
domain: frontend
description: "TypeScript-specific patterns for frontend (client-side)"
---

# TypeScript Frontend

`strict: true` in tsconfig. Use `unknown` for external data, narrow via guards.

Avoid `as` casts. Use type guards or discriminated unions.

DOM types: prefer `HTMLElement` specifics over generic `Element` (e.g., `HTMLInputElement` not `Element`).

Event types: use React's synthetic event types (`React.ChangeEvent<T>`) not native DOM events.

Return types on all public functions.

Generic constraints with `extends` to avoid inference complexity.

Avoid `React.FC`—prefer explicit return type annotation: `const Component = (): JSX.Element => { ... }`.

## Don'ts

- `any` type
- Non-null assertion `!` on values that could be null
- `enum` declarations (use `as const` objects)
- Loose equality `==`
- Accessing DOM types without narrowing (e.g., `(e.target as HTMLInputElement).value`)
