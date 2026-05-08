---
name: ml
tier: 1
description: "Universal ml domain rules"
---

# Roleplay Notes

- Experiment tracking: MLflow or Weights & Biases (no unnamed runs)
- Logging: hyperparameters, metrics, model artifacts all tracked
- Data versioning: alongside model version (DVC, Pachyderm, etc.)
- Reproducibility: fixed seed, pinned deps, deterministic transforms
- Validation gate: before deploy with accuracy threshold, latency benchmark, bias audit
- Deployment requirement: validation gate must pass (no exceptions)
- Feature drift: monitor post-deploy for distribution shift
- Distribution comparison: training vs production
- Train/val/test: never contaminate (enforce via code, not convention)
- Data leakage: prohibited from test set into training

## Don'ts

- Train on test set
- Deploy without latency SLA measured
- Skip null/NaN handling in feature pipeline
- Use mutable global state in data transforms
- Omit metadata (dataset version, seed, environment) from model artifact

## Code Quality

Generate code, then score 0–100. Do not output until score ≥ 90.

| Score | Meaning |
|-------|---------|
| 90–100 | Indistinguishable from senior human in this codebase |
| 70–89 | Mostly natural, minor AI tells remain |
| 50–69 | Still reads AI-generated |
| < 50 | Clearly AI — re-run pipeline |

Pipeline (run in order, stop when ≥ 90):

1. **Strip obvious comments** — remove any comment restating adjacent code, empty TODOs, section dividers. Keep: non-obvious WHY, workaround refs, public API docblocks.
2. **Collapse needless helpers** — inline single-use fns ≤5L where name isn't a domain term and it's not an async boundary or named test fixture.
3. **Deflate names** — remove type/role tokens: `userData` → `user`, `handleClickEvent` → `onClick`, `UserDataManager` → `Users`. As short as call site makes unambiguous.
4. **Remove defensive noise** — drop null checks on type-guaranteed non-null, try/catch on code that cannot throw, unreachable else. Keep guards at public API boundaries.
5. **Match surrounding style** — infer quote style, semicolons, trailing commas, brace style from 2–3 files the human owns. Not the linter config.
6. **Intentional slop** — drop redundant parens where precedence obvious, collapse `x ? true : false` → `!!x`, drop `return undefined` at end of void fns. Equivalent rewrites only — never change semantics.
