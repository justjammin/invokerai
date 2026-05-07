---
name: go
tier: 2
domain: backend
description: "Go-specific patterns for backend"
---

# Go Backend

Errors: always return and check, never `_` an error from a fallible function. Wrap errors with `fmt.Errorf("operation: %w", err)` for context.

Goroutines: always have an exit strategy. Use `context.Context` for cancellation and timeouts. Defer cleanup logic (channels, timers).

Interfaces: define at consumer, small (1-3 methods), not at producer. `io.Reader`, `io.Writer` pattern.

No global mutable state. Pass dependencies explicitly. Makes testing and reasoning easier.

`defer` for cleanup, but never `defer` in loops—defer on exit only. Use explicit resource cleanup in loops.

Struct methods: avoid large receivers. Pass pointers for methods that modify, values otherwise.

## Don'ts

- `panic` in library code (return error instead)
- `init()` with side effects
- Naked returns in long functions (explicit return statements)
- Ignoring race conditions in tests (use `-race` flag)
- Unbounded goroutine creation (always rate-limit)
