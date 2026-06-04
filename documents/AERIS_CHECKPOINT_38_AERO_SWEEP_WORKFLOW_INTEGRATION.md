# AERIS Checkpoint 38 — Aero Sweep Workflow Integration

## Purpose

This slice fixes a workflow-cockpit usability gap: running `aeris aero sweep` manually did not update workflow state.

That was confusing because the guided workflow includes an aero setup/sweep domain before unified aero dataset generation. The cockpit could track dataset and ML commands, but not standalone aero sweeps.

## What changed

- Added a required `aero_sweep` workflow stage between `geometry_dataset` and `aero_dataset`.
- Added `--workflow` to `aeris aero run`.
- Added `--workflow` to `aeris aero sweep`.
- Successful aero runs/sweeps now auto-record the `aero_sweep` stage.
- Aero sweep auto-record only marks the stage complete when all expanded sweep cases succeed.
- CLI help regression tests now verify the new `--workflow` option exists for aero run/sweep.

## Important operator behavior

The workflow cockpit cannot know about terminal commands unless the command is connected to the workflow root:

```bash
aeris aero sweep ... --workflow data/workflows/<workflow_name>
```

If the operator runs `aeris aero sweep` without `--workflow`, the solver run still works, but the cockpit state will not update. That is intentional: workflow state must be explicit and traceable, not guessed by scanning random folders.

## New expected flow

```text
geometry_dataset
→ aero_sweep
→ aero_dataset
→ dataset_qc
→ curation
→ promotion
→ ml_eda
→ ml_training
→ model_comparison
→ model_promotion
→ inference_guard
```

## Boundary

This does not turn `aeris aero sweep` into a unified dataset generator. The sweep verifies aero setup and raw sweep execution. The `aero_dataset` stage is still completed by `aeris dataset aero-generate`.
