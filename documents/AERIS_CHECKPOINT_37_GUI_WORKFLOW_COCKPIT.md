# AERIS Checkpoint 37 — GUI Workflow Cockpit Panel

## What this slice adds

This slice exposes the guided workflow backend in the Streamlit GUI.

New GUI page:

```text
Workflow Cockpit
```

The page gives the operator a visual cockpit for:

- workflow initialization,
- workflow status,
- next-stage guidance,
- workflow validation,
- workflow doctor checks,
- stage evidence tables,
- manual stage backfill through `record-stage`,
- inspection of manifest/status/validation/event-log artifacts.

## Design boundary

The GUI does **not** duplicate workflow business logic.

It calls and displays existing CLI/backend artifacts:

```bash
aeris workflow init
aeris workflow status
aeris workflow next
aeris workflow validate
aeris workflow doctor
aeris workflow record-stage
```

It also reads:

```text
workflow_manifest.json
workflow_status.json
workflow_validation_report.json
workflow_events.jsonl
stages/*/stage_status.json
```

This keeps the GUI as an operator cockpit, not a second workflow engine.

## Why this matters

After Slice 9D.0, AERIS had a workflow stage spine.
After Slice 9D.1, domain commands could auto-record workflow progress.
After Slice 9D.2, the workflow could validate evidence.

This slice finally makes that state visible in the workstation UI.

The operator can now see:

```text
what is complete
what is pending
what is blocked
which artifacts are missing
what the next required command is
whether dataset/model/inference evidence is still valid
```

## Validation

Static GUI regression tests verify that:

- the Workflow Cockpit page is registered,
- it is present in the dispatch table,
- it exposes the expected workflow CLI commands,
- it reads workflow validation artifacts instead of reimplementing workflow logic.

Recommended tests:

```bash
pytest -q tests/gui/test_gui_workflow_cockpit_static.py
python -m py_compile src/aeris/gui/app.py
```

Recommended manual smoke:

```bash
aeris gui run
```

Then open the **Workflow Cockpit** page and run:

```text
Initialize workflow
Validate
Doctor
```

## Boundary

This slice does not add run-stage orchestration, dataset generation logic, ML training logic, or solver execution.
Those remain in CLI/backend modules.
