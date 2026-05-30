# AERIS Checkpoint 18 — ML Inference Guard

This checkpoint adds an inference-envelope guard for promoted models.

## Added

- `src/aeris/ml/inference_guard.py`
- `aeris ml check-inference-inputs`
- `aeris ml predict --enforce-envelope`
- `inference_guard_report.json`

## Purpose

Model promotion certifies that a model was trained from a promoted dataset and passed threshold checks.
The inference guard adds a second protection layer at prediction time:

- validate required feature columns
- detect non-numeric / non-finite feature values
- compare input feature ranges against `training_envelope.json`
- optionally fail prediction if inputs are outside the training envelope

## Important behavior

The training envelope is based on `train_rows.csv`, not the entire curated dataset. Therefore, held-out validation/test rows can legitimately lie outside the training envelope. This is intentional: the guard measures whether new inference inputs are inside the range actually seen during fitting.
