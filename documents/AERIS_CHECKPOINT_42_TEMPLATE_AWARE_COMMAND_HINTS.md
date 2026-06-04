# AERIS Checkpoint 42 — Template-Aware Workflow Command Hints

## Purpose

This slice fixes a small but important operator-guidance mismatch.

After workflow templates were added, `aeris workflow init --template canary` correctly initialized a canary workflow, but the first command hint still recommended the broader training design-space config:

```text
configs/geometry/bwb_training_v1.yaml
```

For canary workflows, that is not ideal. Canary means proof of plumbing, so the safer default is:

```text
configs/geometry/baseline_bwb_25.yaml
```

## What changed

- Added `apply_template_status_hints(...)`.
- `aeris workflow init --template canary` now rewrites only the operator command hint for the first `geometry_dataset` stage.
- The workflow evidence/state model remains unchanged.
- No stages are marked complete.
- No solver, dataset, or ML commands are run.

## Boundary

This is guidance-only. It does not change workflow truth, evidence validation, auto-recording, or GUI business logic.

## Validation

```bash
pytest -q tests/workflow/test_workflow_templates.py
pytest -q tests/commands/test_workflow_cli.py
python -m py_compile src/aeris/workflow/templates.py src/aeris/commands/workflow.py

aeris workflow init --name demo_canary --template canary --output-dir data/workflows/demo_canary --force
aeris workflow status --workflow data/workflows/demo_canary
```
