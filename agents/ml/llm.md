---
name: llm
tier: 2
domain: ml
description: "LLM-specific patterns"
---

# LLM

Prompt versioning: prompts in version control, not hardcoded strings. Tag releases with prompt version.

RAG: chunk size and overlap tuned per retrieval task—not defaults. Test retrieval quality.

Evals: every prompt change has eval suite. Never ship blind. Baseline behavior documented.

Token costs tracked per request. Alert on spike (indicates prompt or model change).

System prompt: included in every production call. Defines model behavior, not optional.

Temperature: lower for deterministic tasks (classification), higher for creative tasks (brainstorming). Test both.

## Don'ts

- Concatenate user input directly into prompts (injection risk)
- Use same prompt for all models (behavior differs)
- Skip system prompt in production calls
- Ignore token count limits (test near boundary)
- Omit prompt version from logging
