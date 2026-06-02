# AERIS CHECKPOINT 26 — ML Feature-Set Prediction Support

## What this slice adds

AERIS can now apply a named feature set at inference time:

```bash
aeris ml predict --feature-set bwb_control_physics_v1 ...
aeris ml check-inference-inputs --feature-set bwb_control_physics_v1 ...
```

## Why this matters

After feature-set training integration, models can be trained on engineered feature sets such as `bwb_control_physics_v1`. Prediction must not require operators or future optimization loops to manually recreate engineered columns. The same declared feature-set transforms now apply at prediction time.

## Behavior

- Existing prediction behavior remains unchanged when `--feature-set` is omitted.
- If `--feature-set` is provided, AERIS applies the declared transforms to the input CSV before validating model feature columns.
- The requested feature set must match the model's recorded training feature set by default.
- Mismatches are rejected unless `--allow-feature-set-mismatch` is explicitly used.
- Prediction writes:
  - `predictions.csv`
  - `prediction_summary.json`
  - `materialized_inference_input.csv` when feature-set transforms are applied
  - `inference_feature_engineering_manifest.json` when feature-set transforms are applied
- Inference guard writes the same materialized input and transform manifest when feature-set transforms are applied.

## Boundary

This slice does not add active learning. It only makes prediction and inference guard feature-set aware so active learning can later call prediction safely.
