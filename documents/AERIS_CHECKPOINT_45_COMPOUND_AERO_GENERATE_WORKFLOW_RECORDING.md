# AERIS Checkpoint 45 — Compound Aero-Generate Workflow Recording

## Purpose

The N=5 rehearsal exposed a workflow ergonomics bug.

`aeris dataset aero-generate --workflow ...` performs a compound operation:

- geometry dataset generation,
- aero sweeps,
- unified aero dataset assembly.

Before this checkpoint, it only auto-recorded:

- `aero_dataset`

That caused workflow stage-order gaps and required manual backfill.

## Fix

`aeris dataset aero-generate --workflow ...` now records:

- `geometry_dataset`
- `aero_sweep`
- `aero_dataset`

in that order.

Each stage records the same dataset artifact, with metadata showing:

- `compound_command: true`
- `compound_stage: <stage>`
- dataset name,
- sampler,
- seed,
- solver,
- QC preset,
- sweep values.

## Boundary

This does not change solver execution, dataset generation, QC, curation, or promotion logic.

It only records the workflow evidence correctly for a compound command.

## Validation

    python -m py_compile src/aeris/commands/dataset.py
    pytest -q tests/commands/test_dataset_aero_generate_compound_workflow_static.py
    pytest -q tests/commands/test_workflow_auto_record_cli.py
    pytest -q tests/commands/test_dataset_cli.py
