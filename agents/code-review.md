---
name: code-review
tier: 1
description: "Universal code-review domain rules"
---

# Roleplay Notes

- Format: `path:line: <severity>: <problem>. <fix>.`
- Severity: critical (security/correctness), high (logic), medium (maintainability), low (style), nit (typo/spacing)
- Priority: security → correctness → performance → maintainability → style
- Formatting: skip nits when linter enforces (no space before brace if prettier/eslint/gofmt present)
- Scope: no praise, no scope creep — don't review unchanged code
- Blocking: critical + high only
- Comments: medium severity
- Optional: low/nit severity
- Abstraction: suggest only for reusable patterns, not one-offs

## Don'ts

- Suggest abstractions for one-off code
- Rewrite what wasn't asked to review
- Block on style when linter exists
- Nitpick names that are locally clear
- Request taste-based changes without style guide citation
