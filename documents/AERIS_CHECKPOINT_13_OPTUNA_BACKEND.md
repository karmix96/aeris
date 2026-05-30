# AERIS CHECKPOINT 13 — Optional Optuna Tuning Backend

## What changed

AERIS now supports two tuning backends behind the same command:

```bash
aeris ml tune --backend aeris
```

and:

```bash
aeris ml tune --backend optuna
```

## Why this matters

The original AERIS tuner remains the deterministic, simple, CI-friendly baseline. It is good for grid/random smoke campaigns and for keeping the ML stack independent of optional dependencies.

Optuna is now available as an advanced backend for larger campaigns, smarter search, resume-ready studies, and later cluster/cloud execution.

## New files

```text
src/aeris/ml/optuna_tune.py
configs/ml/tune_extra_trees_optuna_space.json
configs/ml/tune_gradient_boosting_optuna_space.json
tests/ml/test_optuna_tune.py
tests/commands/test_ml_optuna_tune_cli.py
```

## Backend policy

Use:

```text
--backend aeris
```

for small deterministic grid/random searches.

Use:

```text
--backend optuna
```

for real tuning campaigns where TPE/random search, persistent study storage, and later parallel workers matter.

## Optional dependency

Optuna is optional. If it is not installed, the normal AERIS backend still works.

Install when needed:

```bash
pip install optuna
```

Later, this should become an optional dependency group such as:

```text
ml-advanced = ["optuna"]
```

## Example

```bash
aeris ml tune \
  --backend optuna \
  --dataset data/datasets/ml_light_promoted_v1 \
  --features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg \
  --targets cl,cd,cm \
  --model-type extra_trees \
  --param-space-json configs/ml/tune_extra_trees_optuna_space.json \
  --n-trials 25 \
  --optuna-sampler tpe \
  --split-method grouped \
  --group-column geometry_id \
  --random-seed 123 \
  --selection-metric val.rmse_mean \
  --minimize \
  --output-dir data/processed/ml_runs/tune_optuna_extra_trees_light_v1
```

With persistent storage:

```bash
aeris ml tune \
  --backend optuna \
  --storage sqlite:///data/processed/ml_runs/optuna_studies/aeris.db \
  --study-name extra_trees_light_v1 \
  ...
```

## Important limitation

This does not yet add distributed execution. It prepares the seam. Parallel workers and cluster submission should be added through a future execution layer, not hacked into ML training logic.
