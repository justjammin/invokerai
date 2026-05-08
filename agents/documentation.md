---
name: documentation
tier: 1
description: "Universal documentation domain rules"
---

# Roleplay Notes

- Getting started: copy-paste runnable
- Examples: CI-verified on every merge (runnable tests, no pseudo-code)
- API reference: every parameter typed with docs, examples, error cases, response shape
- Changelog: describe behavior changes (not "various fixes")
- Breaking changes: migration path documented
- Architecture diagrams: show failure paths and degraded states
- Happy path: not sufficient — diagram degradation
- Dependencies: labeled in diagrams
- Async boundaries: labeled in diagrams
- Code examples: runnable in isolation with provided setup
- No pseudo-code: all examples aspirational-free
- READMEs: describe what the project is AND how to run it
- Quick start: included in README
- Diagrams: every major component
- Diagram elements: boxes = services/modules, arrows = communication direction

## Don'ts

- Describe project without "how to run it"
- Leave TODO with no ticket/owner
- Document internal implementation details that belong in code comments
- Paste examples that don't work if copy-pasted
- Draw diagrams showing only happy path
