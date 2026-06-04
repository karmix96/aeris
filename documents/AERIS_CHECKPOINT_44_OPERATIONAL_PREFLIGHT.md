# AERIS Checkpoint 44 — Operational Rehearsal Preflight

## Purpose

This slice prepares AERIS for the next roadmap phase: the N=50 operational rehearsal campaign.

It does not run the campaign.

It checks whether the planned campaign is coherent before spending solver time.

## Added

- `src/aeris/workflow/preflight.py`
- `aeris workflow preflight`
- `tests/workflow/test_workflow_preflight.py`
- `tests/commands/test_workflow_preflight_cli.py`

## What it checks

- planned geometry config exists,
- planned geometry count is positive,
- expanded aero case count,
- workflow coverage health,
- optional workflow gaps,
- optional workflow root/status availability,
- basic canary/training-config mismatch warnings.

## Example

    aeris workflow preflight \
      --config configs/geometry/bwb_training_v1.yaml \
      --n 50 \
      --alpha-values -2,0,4,8 \
      --velocity-values 20,28 \
      --altitude-values 0,1500 \
      --control-input-values -5,0,5 \
      --output-json workflow_preflight_report.json

## Boundary

This slice does not run geometry, aero, QC, curation, promotion, EDA, ML training, active learning, or multifidelity.

It is a preflight report only.

## Why this matters

N=50 with realistic sweeps can quickly become hundreds or thousands of AVL cases.

Before running that, AERIS should prove that the config, workflow, command coverage, and expected case count are sane.
