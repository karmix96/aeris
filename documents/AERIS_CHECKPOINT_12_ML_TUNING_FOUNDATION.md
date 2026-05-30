# AERIS CHECKPOINT 12 — ML Tuning Foundation

## What was added

AERIS now has a first production-oriented hyperparameter tuning layer.

New core file:

```text
src/aeris/ml/tune.py
```

New CLI command:

```bash
aeris ml tune
```

New config examples:

```text
configs/ml/tune_gradient_boosting_space.json
configs/ml/tune_random_forest_space.json
```

## What it does

The tuning layer runs deterministic parameter trials for one model family using the existing promoted-dataset and training pipeline.

For each trial it writes a full normal ML training run under:

```text
<tuning_output>/trials/trial_0000/
```

The tuning root writes:

```text
tuning_summary.json
tuning_trials.csv
best_trial.json
```

## Why this matters

This enables honest model development:

- same dataset
- same split
- explicit hyperparameter space
- tracked trial outputs
- best-trial selection by validation metric
- resumable / cluster-ready directory structure later

This is the correct bridge toward large model comparison, repeated-seed stability studies, and future cluster tuning.

## What this is not yet

This is not yet Optuna, Ray Tune, Dask, SLURM, Bayesian optimization, or distributed tuning.

That comes later.

Current goal: robust local deterministic tuning first.

## Typical command

```bash
aeris ml tune \
  --config configs/ml/tabular_baseline.yaml \
  --param-space-json configs/ml/tune_gradient_boosting_space.json \
  --output-dir data/processed/ml_tuning/gb_baseline_tune
```

Or explicit CLI:

```bash
aeris ml tune \
  --dataset data/datasets/<promoted_dataset> \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --model-type gradient_boosting \
  --param-space-json configs/ml/tune_gradient_boosting_space.json \
  --split-method grouped \
  --group-column geometry_id \
  --output-dir data/processed/ml_tuning/gb_explicit_tune
```

## Next slice

Next logical slice: repeated-seed/self-comparison and tuning-comparison reports:

```text
model A vs model A across seeds
model A vs model A across hyperparameters
model A vs model B after tuning
```

After that: multi-fidelity delta learning.
