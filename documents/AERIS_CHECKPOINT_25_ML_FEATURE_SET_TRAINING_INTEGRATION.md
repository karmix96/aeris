# AERIS CHECKPOINT 25 — ML Feature-Set Training Integration

## What this slice adds

AERIS ML can now use named feature sets directly in training/comparison/tuning commands:

```bash
aeris ml train --feature-set bwb_control_raw ...
aeris ml train --feature-set bwb_control_physics_v1 ...
aeris ml compare --feature-set bwb_control_raw ...
aeris ml tune --feature-set bwb_control_raw ...
```

## What changed

- `train_baseline_model(...)` accepts `feature_set_name`.
- Feature-set training loads only required raw source columns from the promoted curated dataset.
- Declared feature-set transforms are applied before splitting.
- Feature-set validation runs before model fitting.
- `train_config.json` records `feature_set_name` and the feature-set schema.
- `ml_run_manifest.json` records feature-set provenance under `training_data`.
- `compare_models(...)`, `tune_model(...)`, and `tune_model_optuna(...)` pass feature-set provenance through to training runs.
- CLI commands `train`, `compare`, and `tune` support `--feature-set`.

## Boundary

This slice does not add prediction-time feature-set materialization and does not change solver execution. Solver work stays outside `src/aeris/ml/`.

## Why this matters

AERIS can now compare raw and physics-engineered input representations without hiding engineered columns inside one-off CLI strings. Feature representation becomes an explicit, auditable part of the ML run evidence chain.
