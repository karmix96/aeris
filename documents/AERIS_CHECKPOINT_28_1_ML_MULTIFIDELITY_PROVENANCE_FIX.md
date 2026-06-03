# AERIS Checkpoint 28.1 — Multifidelity Feature-Set Provenance Fix

## Purpose

Slice 7 made multifidelity delta-model training and prediction feature-set aware, but the training run folder did not expose enough top-level provenance for operator inspection.

The computational path worked, but the evidence trail was incomplete.

## Fix

Delta-model training now writes:

```text
delta_train_config.json      # canonical delta-model config
train_config.json            # normal-ML-compatible alias
feature_engineering_manifest.json
```

`delta_model_manifest.json` now records top-level:

```text
feature_set_name
feature_columns
final_features
target_columns
lf_target_columns
hf_target_columns
```

and its `artifacts` block points to the standard config alias and feature-engineering manifest.

## Why this matters

The multifidelity trust chain is now auditable:

```text
LF/HF paired delta dataset
→ feature-set transforms during delta training
→ final delta-model feature columns
→ saved feature-engineering manifest
→ feature-set-aware delta prediction
```

This is evidence-chain hardening only. No solver execution was added to `src/aeris/ml/`.
