# AERIS CHECKPOINT 24 — ML Feature-Set Materialization

## What this slice adds

AERIS can now materialize a named ML feature set into explicit artifacts:

```bash
aeris ml feature-engineer \
  --dataset data/datasets/<promoted_dataset> \
  --feature-set bwb_control_physics_v1 \
  --targets cl,cd,cm
```

The command writes:

```text
engineered_dataset.csv
feature_engineering_manifest.json
feature_schema.json
feature_materialization_report.json
```

## Why this matters

Slice 2 allowed AERIS to validate feature sets in memory. That is useful, but not enough for serious campaigns. Slice 3 turns the selected input representation into a real data product with schema, transform manifest, row counts, validation result, and hashes.

This prevents hidden feature engineering inside training code. A model should not silently get extra columns because a function happened to run. The feature set becomes auditable before training.

## Design boundary

This slice does **not** integrate feature sets into `train`, `compare`, `tune`, or `predict` yet. That belongs in the next slice.

This slice also does **not** run AVL, CFD, XFOIL, OpenFOAM, or SU2. It consumes promoted/curated scalar data products and writes feature-engineered ML-ready data products.

## Example commands

Default output:

```bash
aeris ml feature-engineer \
  --dataset data/datasets/<promoted_dataset> \
  --feature-set bwb_control_physics_v1 \
  --targets cl,cd,cm
```

Only group/features/targets:

```bash
aeris ml feature-engineer \
  --dataset data/datasets/<promoted_dataset> \
  --feature-set bwb_control_physics_v1 \
  --targets cl,cd,cm \
  --only-feature-columns
```

Custom output:

```bash
aeris ml feature-engineer \
  --dataset data/datasets/<promoted_dataset> \
  --feature-set bwb_control_raw \
  --targets cl,cd,cm \
  --output-dir data/processed/features/bwb_control_raw_demo
```

## Next slice

Slice 4 should integrate `--feature-set` into:

```text
aeris ml train
aeris ml compare
aeris ml tune
aeris ml compare-seeds
aeris ml predict
```

The integration should consume the materialized feature schema/report where appropriate and record feature-set provenance in ML run manifests.
