---
name: orchestration
tier: 1
description: "Universal orchestration and multi-agent coordination rules"
---

# Roleplay Notes

- Treat every agent invocation as a typed function call: input schema in, output contract out
- Decompose before dispatching: map objective → inputs → tool/retrieval needs → output contract before spawning any agent
- One agent, one concern: don't bundle unrelated tasks in a single spawn
- Parallel only when outputs are truly independent: shared state dependencies must serialize
- Failure is the expected case: every orchestration step needs explicit success criteria and a fallback
- Spawn count is a cost signal: minimize steps, not maximize thoroughness
- Context window is finite: pass only what the specialist needs, not the full conversation
- Stateless by default: don't assume agent memory across separate spawns

## Prompt Engineering

Treat prompts as interfaces, not instructions. A prompt defines task boundaries, input/output contracts, and failure handling expectations — not writing style.

Working mode:
- Map objective, input context, tool/retrieval usage, and required output contract before writing
- Identify ambiguity, instruction conflict, or missing constraints that cause unstable behavior
- Propose the smallest prompt-level change that improves reliability, not the most thorough rewrite
- Validate with three scenarios: one normal case, one edge case, one failure case

Focus on:
- Instruction hierarchy: conflicts cause non-deterministic output — resolve them explicitly
- Output schema: machine- and human-consumable formats reduce post-processing errors
- Grounding constraints: specify when citations, tool calls, or retrieval are required vs optional
- Scope boundaries: explicit role + decision criteria = fewer hallucinated expansions
- Refusal surface: define what is out-of-scope so the agent refuses clearly, not silently
- Token budget: critical guidance survives compression; stylistic guidance does not
- Evaluation: compare prompt variants on a stable scenario set, not a single demo case

Quality checks:
- Revisions must map to concrete failure patterns — not preference or aesthetics
- Output contract must be verifiable: if you can't test the output, tighten the schema
- Check over-compliance (does too much) and under-compliance (ignores constraints) separately
- Call out when the fix requires orchestration/system changes, not prompt edits alone

Do not optimize for a single demo case at the expense of general reliability.

## Don'ts

- Spawn agents without a defined output contract
- Pass the full conversation context when a summary suffices
- Chain agents sequentially when they can run in parallel
- Retry a failed agent with the same prompt (diagnose first)
- Use orchestration to paper over a poorly scoped task (fix the scope)
