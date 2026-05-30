# AERIS Checkpoint 20 — ML Multifidelity Delta Model

This checkpoint turns the delta dataset product into a usable delta-learning model.

## Added

- `src/aeris/ml/multifidelity/delta_model.py`
- `aeris ml train-delta-model`
- `aeris ml predict-delta-model`
- `delta_model_manifest.json`
- corrected-output diagnostics

## Concept

Given a paired delta dataset:

```text
LF scalar result + learned delta ≈ HF scalar result
```

The model trains on:

```text
features -> delta__cl, delta__cd, delta__cm
```

During prediction it writes:

```text
pred__delta__cl
pred_corrected__cl = lf__cl + pred__delta__cl
```

and equivalent columns for all base targets.

## Important boundary

This slice does not run CFD, XFOIL, AVL, OpenFOAM, or SU2. It only consumes scalar LF/HF data products and trains a correction model.
