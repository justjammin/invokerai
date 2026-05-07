---
name: documentation
tier: 1
description: "Universal documentation domain rules"
---

# Documentation

Getting started: must work copy-paste. Examples CI-verified on every merge (runnable tests, not pseudo-code).

API reference: every parameter typed, documented with examples, error cases covered. Response shape defined.

Changelog: behavior change described, not "various fixes and improvements". Migration path for breaking changes.

Architecture diagrams: show failure paths and degraded states, not just happy path. Label dependencies and async boundaries.

Code examples: runnable in isolation with provided context/setup. Not pseudo-code or aspirational.

READMEs: describe what the project is AND how to run it. Quick start included.

Diagrams: every major component should have one. Boxes = services/modules, arrows = communication direction.

## Don'ts

- Describe project without "how to run it"
- Leave TODO with no ticket/owner
- Document internal implementation details that belong in code comments
- Paste examples that don't work if copy-pasted
- Draw diagrams showing only happy path
