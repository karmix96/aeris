# AERIS Checkpoint 35 — Workflow Auto-Record Integration

## What changed

AERIS guided workflows can now be updated automatically by selected successful domain commands when the operator passes:

```bash
aeris <domain> <command> ... --workflow data/workflows/<workflow_name>
```

The workflow spine remains state-only. It still does not run solvers, datasets, QC, curation, ML, or MDAO by itself.

## New helper

```text
src/aeris/commands/_workflow_recording.py
```

This helper calls `record_stage(...)` only after the underlying command has succeeded. If `--workflow` is not supplied, behavior is unchanged.

## Commands with initial auto-record support

Dataset / trust chain:

```text
aeris dataset generate --workflow ...
aeris dataset aero-generate --workflow ...
aeris dataset qc --workflow ...
aeris dataset aero-qc --workflow ...
aeris dataset curate-aero --workflow ...
aeris dataset promote-aero --workflow ...
```

ML / model trust chain:

```text
aeris ml eda --workflow ...
aeris ml train --workflow ...
aeris ml compare --workflow ...
aeris ml compare-seeds --workflow ...
aeris ml promote-model --workflow ...
aeris ml check-inference-inputs --workflow ...
```

## Why this matters

Before this slice, the operator had to run commands and then manually call:

```bash
aeris workflow record-stage ...
```

That worked, but it was still a clipboard tax. Now the workstation state can follow the real command flow while preserving standalone CLI behavior.

## Boundary

This is not a campaign runner. It does not infer success from arbitrary folders and it does not chain commands automatically. It only records stage completion when a supported command succeeds and the operator explicitly provides `--workflow`.

## Example

```bash
aeris workflow init \
  --name bwb_training_v1_workflow \
  --output-dir data/workflows/bwb_training_v1_workflow

# Later, after an actual promoted dataset exists:
aeris ml eda \
  --dataset data/datasets/<promoted_dataset> \
  --feature-preset bwb_control \
  --targets cl,cd,cm \
  --no-plots \
  --workflow data/workflows/bwb_training_v1_workflow
```

AERIS writes:

```text
stages/ml_eda/stage_status.json
workflow_status.json
workflow_events.jsonl
```

## Validation

Focused tests:

```bash
pytest -q tests/commands/test_workflow_auto_record_cli.py
pytest -q tests/workflow/test_workflow_spine.py tests/commands/test_workflow_cli.py
```
