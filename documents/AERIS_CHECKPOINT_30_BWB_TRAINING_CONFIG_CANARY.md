# AERIS Checkpoint 30 — BWB Training Design-Space Config and Canary Plan

## Purpose

This checkpoint adds the first non-degenerate BWB training design-space config:

```text
configs/geometry/bwb_training_v1.yaml
```

The previous operator smoke config, `baseline_bwb_25.yaml`, is intentionally near-fixed. It is excellent for CLI smoke tests and regression checks, but it is not appropriate for design-space ML training because it does not provide real geometry variation.

## What changed

- Added `configs/geometry/bwb_training_v1.yaml`.
- The config keeps the current generator: `bwb_segmented_v1`.
- The config keeps production-relevant control surfaces: a symmetric trailing-edge elevon.
- Plotting is disabled by default.
- AeroSandbox geometry construction is enabled by default because downstream aero runs require it.
- Added a regression test proving the training config is not near-fixed like the baseline smoke config.

## Intended workflow

Run a small canary before any expensive campaign:

```bash
aeris dataset aero-generate \
  -c configs/geometry/bwb_training_v1.yaml \
  --n 5 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --name bwb_training_v1_canary_n5 \
  --no-save-plot \
  --build-aerosandbox \
  --alpha-values -2,0,4,8 \
  --beta-values 0 \
  --velocity-values 20,28 \
  --altitude-values 0,1500 \
  --p-values 0 \
  --q-values 0 \
  --r-values 0 \
  --control-input-values -5,0,5 \
  --solver aerosandbox_avl \
  --avl-command avl \
  --timeout-sec 180 \
  --spanwise-resolution 4 \
  --chordwise-resolution 8 \
  --spanwise-spacing equal \
  --chordwise-spacing cosine \
  --qc-preset production \
  --retain-aero-runs failures_only \
  --keep-geometry-dataset
```

Expected case count:

```text
5 geometries × 4 alpha × 2 velocity × 2 altitude × 3 control = 240 aero cases
```

Only after the canary passes should a larger N=50 training campaign be run.

## Boundary

This checkpoint does not change solver execution, ML training, active learning, or candidate-pool generation. It only adds the real training design-space config and its regression guard.
