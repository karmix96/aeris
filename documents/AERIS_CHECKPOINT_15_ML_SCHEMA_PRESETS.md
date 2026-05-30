# AERIS CHECKPOINT 15 — ML Schema and Feature Presets Foundation

## What changed

This checkpoint adds the generic ML schema/preset layer. It intentionally does **not** implement final airfoil/XFOIL/CFD/GNN schemas yet, because those datasets must be produced by real solver/mesh pipelines first.

## New modules

- `src/aeris/ml/feature_presets.py`
- `src/aeris/ml/schema.py`
- `src/aeris/ml/validation.py`

## New CLI commands

```bash
aeris ml feature-presets
aeris ml validate-schema --dataset <promoted_dataset> --feature-preset bwb_control --targets cl,cd,cm
```

## New convenience behavior

Training, comparison, tuning, and seed-stability commands can now use:

```bash
--feature-preset bwb_control
```

instead of repeating:

```bash
--features c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg
```

## Active presets

- `bwb_basic`
- `bwb_control`

No final airfoil/CFD/GNN presets were added yet. That is deliberate.

## Why this matters

This gives AERIS a reusable ML schema validation layer without coupling ML to one solver, one geometry generator, or one future airfoil workflow.

The next airfoil-specific layer should only be added after the XFOIL/CFD dataset output schema is real.
