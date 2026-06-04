# AERIS Checkpoint 40 — Evidence-Driven GUI Workstation Refactor

## Purpose

This slice refactors the GUI toward an evidence-driven workstation.

The GUI must behave like an operator cockpit over real backend state, not as a second backend and not as a simulation of success.

## Added

```text
src/aeris/gui/evidence.py
tests/gui/test_gui_evidence_workstation_static.py
documents/AERIS_CHECKPOINT_40_EVIDENCE_DRIVEN_GUI_WORKSTATION.md
```

## Patched

```text
src/aeris/gui/app.py
```

## What changed

The GUI now has reusable evidence helpers that read:

```text
workflow_manifest.json
workflow_status.json
workflow_validation_report.json
workflow_events.jsonl
stages/*/stage_status.json
```

It also surfaces the backend workflow coverage audit in the Workflow Cockpit.

Mission Control now shows the newest workflow root and its backend-owned evidence summary.

The Workflow Cockpit now shows:

- workflow coverage audit summary,
- required blockers,
- optional workflow gaps,
- selected workflow evidence summary,
- backend next required stage,
- backend recommended command,
- an “Open next domain” navigation button.

## Boundary

This slice does not run solvers, create datasets, train ML models, promote artifacts, or infer stage success in Streamlit.

The GUI reads evidence and launches existing CLI/backend commands only.

## Validation

```bash
pytest -q tests/gui/test_gui_workflow_cockpit_static.py
pytest -q tests/gui/test_gui_evidence_workstation_static.py
python -m py_compile src/aeris/gui/app.py src/aeris/gui/evidence.py
```

Manual smoke:

```bash
aeris gui run
```

Open:

```text
Home
Workflow Cockpit
```

Confirm that workflow evidence is read from real workflow artifacts and that coverage audit truth is visible.
