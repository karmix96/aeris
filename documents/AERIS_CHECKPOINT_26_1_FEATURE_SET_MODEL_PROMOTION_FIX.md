# AERIS Checkpoint 26.1 — Feature-Set Model Promotion Fix

## Purpose

Slice 5 exposed an integration gap: models trained with engineered feature sets could train and predict correctly, but `aeris ml promote-model` still validated the original promoted dataset as if engineered columns had to physically exist in `curated_aero_dataset.csv`.

That was wrong. Engineered feature-set columns are explicit, auditable transforms over raw promoted dataset columns. They are not raw solver outputs.

## Fix

Model promotion now:

- detects `feature_set_name` from `train_config.json` / ML manifest,
- validates the source promoted dataset through `validate_promoted_dataset_feature_set(...)` when a feature set is recorded,
- keeps legacy direct-column validation when no feature set is recorded,
- records `feature_set_name` in `model_promotion_manifest.json` and `model_card.json`.

## Why this matters

The trust chain is now consistent:

```text
promoted raw dataset
→ feature-set transforms during training
→ model promotion validates the feature-set source columns + transforms
→ training envelope is built from engineered train_rows.csv
→ guarded prediction can recreate the same transforms at inference time
```

No solver execution was added to `ml/`.
