# AERIS Checkpoint 46 — DYN-2 Dynamics Batch Labels CLI

## Purpose

This checkpoint adds the DYN-2 operator bridge:

```bash
aeris dynamics batch-labels --dataset data/datasets/<promoted_aero_dataset>
```

The command turns a control-aware aero dataset into dataset-level dynamics/flyability labels for later ML and MDAO screening.

## What it does

The command reuses the existing dataset label chain instead of duplicating physics in the CLI:

```text
promoted/curated aero dataset
→ control derivative extraction
→ first-order trim/control/flyability labels
→ dynamics_label_run_report.json
```

It writes:

```text
control_derivatives.csv
control_derivatives_report.json
flyability_labels.csv
flyability_labels_report.json
dynamics_label_run_report.json
```

## Why this matters

AERIS dynamics is no longer only a single-run diagnostic. It now has a dataset-level bridge that can generate labels such as pitch authority, first-order trim feasibility, and longitudinal basic flyability for later surrogate learning.

## Boundaries

This is not full nonlinear trim.
This is not MIL-STD compliance.
This is not a 6-DOF simulation.
This is a batch evidence layer over first-order control/trim/flyability diagnostics.

## Validation

```bash
pytest -q tests/commands/test_dynamics_batch_labels_cli.py
python -m py_compile src/aeris/commands/dynamics.py
```
