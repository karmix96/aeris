# AERIS CHECKPOINT 14 — ML Comparison Hardening

## Purpose

This checkpoint adds the layer that prevents AERIS from trusting one lucky model comparison.

Before this checkpoint, AERIS could:

- train baseline models
- compare multiple models on one fixed split
- tune one model family with the native AERIS tuner
- tune with optional Optuna backend

That is useful, but incomplete. A one-shot split can lie. A model can win once because the split was easy.

## What this checkpoint adds

### 1. Seed-stability comparison

New command:

```bash
aeris ml compare-seeds ...
```

This runs the normal `compare_models()` workflow repeatedly over multiple random seeds while preserving grouped split logic.

Outputs:

- `comparison_seed_stability_summary.json`
- `seed_stability_rows.csv`
- `model_stability_summary.json`
- `model_stability_summary.csv`
- `per_target_ranking.csv`
- `winner_report.json`

This answers:

- which model wins on average?
- which model wins most often?
- which model is stable across splits?
- which target is weakest?

### 2. Tuning-run comparison

New command:

```bash
aeris ml compare-tuning-runs ...
```

This compares already-completed tuning campaigns by reading each run's `best_trial.json` and `tuning_summary.json`.

Outputs:

- `tuning_run_comparison.json`
- `tuning_run_comparison.csv`
- `winner_report.json`

This is useful after running, for example:

- AERIS random forest tuning
- AERIS gradient boosting tuning
- Optuna ExtraTrees tuning
- Optuna GradientBoosting tuning

## Design rule

This checkpoint does not replace training or tuning. It sits above them.

The layers are now:

```text
promoted dataset
→ train
→ compare one split
→ tune one model family
→ compare across seeds
→ compare tuning campaigns
```

## Why it matters

AERIS is moving toward serious surrogate modeling. Model selection must be reproducible and defensible.

One-shot leaderboard thinking is weak. Stability analysis is stronger.
