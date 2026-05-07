---
name: code-review
tier: 1
description: "Universal code-review domain rules"
---

# Code Review

Format: `path:line: <severity>: <problem>. <fix>.`

Severity levels: `critical` (security/correctness bug) | `high` (logic error) | `medium` (maintainability) | `low` (style preference) | `nit` (typo/spacing).

Priority order: security → correctness → performance → maintainability → style.

Skip formatting nits when linter already enforces them. No "add space before brace" comments if prettier/eslint/gofmt exists.

No praise, no scope creep. Don't review what wasn't changed.

Block on critical + high. Comment on medium. Note low/nit as optional.

## Don'ts

- Suggest abstractions for one-off code
- Rewrite what wasn't asked to review
- Block on style when linter exists
- Nitpick names that are locally clear
- Request changes that are taste-based without style guide citation
