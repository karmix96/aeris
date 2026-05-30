# AERIS Checkpoint 21 — Multifidelity Evaluation

This checkpoint adds the reporting layer that answers the key multifidelity question:

> Did the learned correction improve over the low-fidelity baseline?

## Added

- `src/aeris/ml/multifidelity/evaluation.py`
- `aeris ml evaluate-delta-model`
- `multifidelity_evaluation_report.json`
- `multifidelity_evaluation_rows.csv`

## Evaluation logic

For each partition and target, AERIS compares:

- LF baseline error: `lf__target` vs `hf__target`
- corrected error: `pred_corrected__target` vs `hf__target`

It reports:

- LF RMSE / MAE / R²
- corrected RMSE / MAE / R²
- absolute and percent improvement
- target-level status: `improved`, `worse`, or `tied`
- overall winner report

## Why this matters

Training a delta model is not enough. AERIS must prove whether the correction actually helps. This layer prevents multifidelity work from becoming expensive decoration.
