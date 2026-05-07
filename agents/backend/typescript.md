---
name: typescript
tier: 2
domain: backend
description: "TypeScript-specific patterns for backend"
---

# TypeScript Backend

`strict: true` in tsconfig, no exceptions. If strict causes pain, the code is likely unclear anyway.

Avoid `as` type casts. Use type guards or schema validation (Zod, ts-guard, etc) instead.

`unknown` over `any` for external data. Then narrow type via guards.

Discriminated unions for state modeling: `type Result = {type: 'ok', value: T} | {type: 'error', error: E}`.

Return types on all public functions (forces explicit interface design).

Generics: constrain with `extends` when possible. Avoid inference hell.

## Don'ts

- `any` (use `unknown`)
- Non-null assertion `!` on values that could be null
- `enum` for data (use `as const` objects instead)
- `namespace` declarations
- Loose equality `==` (always `===`)
