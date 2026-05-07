---
name: ml
tier: 1
description: "Universal ml domain rules"
---

# ML

All experiments tracked (MLflow, Weights & Biases): no unnamed runs, ever. Hyperparameters, metrics, model artifacts all logged.

Data versioned alongside model version (DVC, Pachyderm, or equivalent). Reproducibility: fixed seed, pinned deps, deterministic transforms.

Validation gate before deploy: accuracy threshold, latency benchmark, bias audit. No model to prod without gate passing.

Feature drift monitoring post-deploy: alert on distribution shift. Compare training distribution vs production.

Train/val/test splits never contaminate. Enforce via code, not convention. No data leakage from test set into training.

## Don'ts

- Train on test set
- Deploy without latency SLA measured
- Skip null/NaN handling in feature pipeline
- Use mutable global state in data transforms
- Omit metadata (dataset version, seed, environment) from model artifact
