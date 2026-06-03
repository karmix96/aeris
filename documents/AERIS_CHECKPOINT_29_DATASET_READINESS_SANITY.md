# AERIS Checkpoint 29 — Dataset-Readiness Sanity Cleanup

## What changed

This slice prepares AERIS for real training-data campaigns before active learning.

Added:

- LightGBM feature-name warning cleanup in `model_registry.py`.
- `src/aeris/aero/cm_sanity.py`.
- `aeris aero cm-sanity`.
- Unit and CLI regression tests.

## Why this matters

The previous ML/multifidelity slices proved the trust chain on a small smoke dataset. Before producing larger datasets, two issues needed cleanup:

1. LightGBM emitted noisy sklearn feature-name warnings during operator runs.
2. Cm/Cma sign convention needed a cheap sanity gate before trusting stability, trim, or Cm surrogate outputs.

## Command

```bash
aeris aero cm-sanity \
  --dataset data/datasets/<aero_dataset> \
  --output-dir data/processed/aero_sanity/<name>
```

For direct CSV input:

```bash
aeris aero cm-sanity \
  --csv data/datasets/<dataset>/curated_aero_dataset.csv \
  --fail-on-violation
```

## Boundary

This slice does not generate the production dataset and does not run solvers. It only adds pre-campaign sanity tooling and warning hygiene.
