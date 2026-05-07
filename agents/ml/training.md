---
name: training
tier: 2
domain: ml
description: "Model training patterns"
---

# Model Training

Reproducibility: seed + environment + data version all pinned. Document in model metadata.

Checkpoints: saved at intervals, resumable. No full retrain on interruption. Track best checkpoint by metric.

Gradient: clip norm for stability (prevents exploding gradients). Log gradient/weight norms during training.

Validation loss curve: inspect every training run. Diverging loss = stop, debug.

Hyperparameter search: grid/random/Bayesian. Log all runs (MLflow). Don't cherry-pick results.

Batch size: test impact on convergence (larger batch = noisy estimates, harder to escape local minima).

## Don'ts

- Train without validation loss curve
- Leak test labels into training (contamination)
- Use mutable augmentation state across workers
- Skip early stopping (train forever is waste)
- Omit dataset version from artifact metadata
