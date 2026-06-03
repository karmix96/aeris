# AERIS Checkpoint 34 — Guided Workflow / Stage Spine

## Purpose

This slice adds the first small backend spine for the guided AERIS workstation behavior.

It does **not** replace standalone CLI commands. It records workflow state around them.

The goal is to support the future Workbench/Fluent-style mental model:

```text
geometry dataset
→ aero dataset
→ dataset QC
→ curation
→ promotion
→ ML EDA
→ ML training/comparison
→ model promotion
→ inference guard
→ optional multifidelity / active learning
```

## Added

New package:

```text
src/aeris/workflow/
```

New core module:

```text
src/aeris/workflow/spine.py
```

New CLI group:

```bash
aeris workflow
```

New commands:

```bash
aeris workflow stages
aeris workflow init
aeris workflow status
aeris workflow next
aeris workflow inspect
aeris workflow record-stage
```

## Artifacts

A workflow root writes:

```text
workflow_manifest.json
workflow_status.json
workflow_events.jsonl
stages/<stage_name>/stage_status.json
```

## Important boundary

This slice does not run geometry, AVL, QC, ML, multifidelity, or active learning.

It only creates the evidence/status spine that future commands can write into after they complete their normal standalone work.

That is deliberate. A giant campaign runner now would be fake productivity and real architecture debt.

## Example

```bash
aeris workflow init \
  --name bwb_training_v1_workflow \
  --output-dir data/workflows/bwb_training_v1_workflow

# After a geometry dataset command succeeds:
aeris workflow record-stage \
  --workflow data/workflows/bwb_training_v1_workflow \
  --stage geometry_dataset \
  --status complete \
  --artifact data/datasets/bwb_training_v1_canary_n5 \
  --notes "geometry canary passed"

aeris workflow next --workflow data/workflows/bwb_training_v1_workflow
```

## Validation

```bash
pytest tests/workflow/test_workflow_spine.py tests/commands/test_workflow_cli.py
```

## Next slice

Wire selected production commands to optionally accept `--workflow` and automatically call `record_stage(...)` after successful completion.

Start with dataset stages only:

```text
geometry_dataset
aero_dataset
dataset_qc
curation
promotion
```

Do not wire ML and multifidelity until the dataset-side contract is proven.
