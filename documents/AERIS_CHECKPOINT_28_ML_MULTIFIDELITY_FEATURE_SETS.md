# AERIS Checkpoint 28 — Multifidelity Feature-Set Integration

## What changed

This slice hardens the scalar multifidelity delta-learning path so it uses the same feature-set trust chain as normal ML training and prediction.

## Added behavior

`aeris ml train-delta-model` now supports:

```bash
aeris ml train-delta-model \
  --delta-dataset data/processed/multifidelity/delta_v1 \
  --feature-set bwb_control_physics_v1 \
  --base-targets cl,cd,cm
```

When a feature set is used, AERIS:

1. validates that required raw source columns exist in the delta dataset,
2. applies the declared feature-engineering transforms,
3. uses the feature-set final columns as geometry/condition inputs,
4. automatically appends `lf__<target>` columns as correction inputs,
5. records feature-set provenance in `delta_train_config.json` and `delta_model_manifest.json`.

`aeris ml predict-delta-model` now supports:

```bash
aeris ml predict-delta-model \
  --model-run-dir data/processed/ml_runs/delta_et_v1 \
  --input-csv raw_delta_candidates.csv \
  --feature-set bwb_control_physics_v1
```

Prediction can receive raw candidate rows plus LF target columns and materialize engineered columns before correction.

## Mismatch protection

By default, delta prediction rejects a requested feature set that differs from the feature set recorded during delta-model training. Use `--allow-feature-set-mismatch` only for deliberate debugging or migration.

## Boundary

This slice still does not run AVL, XFOIL, CFD, OpenFOAM, or SU2. Multifidelity remains a scalar LF/HF data-product layer inside `ml/`, not a solver runner.
