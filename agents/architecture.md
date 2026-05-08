---
name: architecture
tier: 1
description: "Universal architecture domain rules"
---

# Roleplay Notes

- ADR: Architecture Decision Record for every structural decision
- ADR contents: context, options considered, decision, consequences
- ADR location: `docs/adr/NNNN-{slug}.md`
- Trade-offs: document rejected options and rationale (not just chosen)
- Review: revisit every 6 months
- Service boundaries: own data (no shared DB)
- Communication: async by default
- Sync usage: only when latency requires (e.g., user-facing checkout)
- Sync safety: circuit breakers on all sync calls
- Failure planning: explicit degradation strategy for each external dependency
- Failure questions: what if service X is down?
- Timeout: configured for all external calls
- Retry logic: defined
- Fallback: defined
- Evolutionary design: document constraints and assumptions for architectural change

## Don'ts

- Design for hypothetical v3 requirements — build what was asked
- Premature abstraction from one example
- Diagram only happy path
- Skip "what breaks if this service is down?" question
