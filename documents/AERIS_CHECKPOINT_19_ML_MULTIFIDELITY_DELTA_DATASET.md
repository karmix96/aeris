# AERIS Checkpoint 19 — ML Multifidelity Delta Dataset Foundation

This checkpoint adds the first multifidelity ML foundation layer.

## Added

- `src/aeris/ml/multifidelity/`
- `build_delta_dataset(...)`
- `aeris ml build-delta-dataset`
- `delta_dataset.csv`
- `delta_dataset_report.json`

## What it does

Given a low-fidelity scalar CSV and a high-fidelity scalar CSV, the tool:

1. validates required pairing keys and target columns,
2. rejects duplicate pair keys,
3. pairs matching LF/HF rows,
4. computes delta targets:

```text
delta__target = hf__target - lf__target
```

5. writes an ML-ready `delta_dataset.csv`,
6. writes a traceable report with row counts, unmatched rows, delta statistics, and file hashes.

## What it does not do

This does not run AVL, XFOIL, CFD, OpenFOAM, or SU2.
Solver execution remains outside the ML folder.

## Purpose

This creates the data product required for delta learning:

```text
low-fidelity prediction + learned correction ≈ high-fidelity result
```

Later slices can train models on `delta__cl`, `delta__cd`, and `delta__cm` using the normal AERIS ML train/tune/compare/promote pipeline.
