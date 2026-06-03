# AERIS Checkpoint 31 — ML EDA Feature-Set Support

## What changed

`aeris ml eda` now supports named feature sets:

```bash
aeris ml eda \
  --dataset data/datasets/<promoted_aero_dataset> \
  --feature-set bwb_control_physics_v1 \
  --targets cl,cd,cm \
  --no-plots
```

## Behavior

- EDA accepts exactly one of `--features`, `--feature-preset`, or `--feature-set`.
- Feature-set mode validates raw source columns against the promoted curated dataset.
- Declared feature-engineering transforms are applied in memory before EDA.
- Correlation, nonlinearity, feature stats, and optional plots use the materialized feature frame.
- `eda_report.json` records row/column counts, raw source columns, engineered columns, final feature columns, transform manifest, and validation provenance.

## Boundary

This slice does not train models, split data, run solvers, or write a reusable engineered training dataset. It is an operator/reporting improvement only.

## Why this matters

Feature-set-aware training already existed, so EDA lagging behind was a trust-chain gap. Now the pre-training audit can inspect the same engineered representation used by train/compare/tune/predict.
