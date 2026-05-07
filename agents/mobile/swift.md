---
name: swift
tier: 2
domain: mobile
description: "Swift-specific patterns for mobile"
---

# Swift

Concurrency: Swift `async/await` + actors for shared mutable state. No DispatchQueue unless wrapping legacy code.

Memory: `[weak self]` in closures capturing self. Avoid retain cycles.

SwiftUI: `@StateObject` for owned models, `@ObservedObject` for injected, `@EnvironmentObject` sparingly (implicit dependency).

Codable for JSON: manual `Codable` conformance only when decoding JSON schema differs from Swift model.

Value types (struct) by default, class only for reference semantics. Immutability preferred.

## Don'ts

- Force unwrap `!` on optionals that can be nil
- Blocking main thread (use `Task` or `DispatchQueue.global()`)
- Mix UIKit and SwiftUI without clear boundary
- `@ObservedObject` in environment (causes extra subscriptions)
- Mutable capture in closures without `[weak self]`
