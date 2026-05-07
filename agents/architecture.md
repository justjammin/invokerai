---
name: architecture
tier: 1
description: "Universal architecture domain rules"
---

# Architecture

ADR (Architecture Decision Record) for every structural decision: context, options considered, decision, consequences. File in `docs/adr/NNNN-{slug}.md`.

Trade-offs documented: not just chosen option, but what was rejected and why. Revisit every 6 months.

Service boundaries: own data (no shared DB), async by default, sync only when latency requires (e.g., user-facing checkout). Circuit breakers on sync calls.

Design for failure: explicit degradation strategy for every external dependency. What happens if service X is down? Timeout configured, retry logic, fallback defined.

Evolutionary: document what must be true for architecture to change. Constraints and assumptions.

## Don'ts

- Design for hypothetical v3 requirements—build what was asked
- Premature abstraction from one example
- Diagram only happy path
- Skip "what breaks if this service is down?" question
