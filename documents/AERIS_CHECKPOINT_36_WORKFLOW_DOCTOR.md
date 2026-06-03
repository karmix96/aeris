# AERIS Checkpoint 36 — Workflow Doctor / Evidence Validator

## What this slice adds

AERIS workflow tracking can now validate its own evidence trail.

New workflow commands:

```bash
aeris workflow validate --workflow data/workflows/<workflow>
aeris workflow doctor --workflow data/workflows/<workflow>
aeris workflow summary --workflow data/workflows/<workflow>
```

`validate` and `doctor` write:

```text
workflow_validation_report.json
```

## Why this matters

Slice 9D.0 added the workflow spine. Slice 9D.1 connected successful domain commands to workflow auto-recording.

This slice asks the uncomfortable but necessary question:

```text
The workflow says a stage is complete. Is the evidence still actually there and trustworthy?
```

Without this layer, the workflow cockpit could become a nice-looking checklist that lies by accident. That is exactly what AERIS must avoid.

## Validation checks

The validator checks:

- manifest/status structure,
- required-stage completion progress,
- recorded artifact existence,
- stage-order gaps,
- dataset promotion evidence,
- model promotion evidence,
- inference-guard evidence,
- explicit failed/blocked stages,
- blocker/warning counts.

The report classifies workflow health as:

```text
healthy
incomplete
blocked
inconsistent
```

## Trust artifact checks

Stage-specific checks include:

### Dataset promotion

For the `promotion` stage, AERIS looks for:

```text
promotion_manifest.json
```

and checks promotion readiness and blockers.

### Model promotion

For the `model_promotion` stage, AERIS looks for:

```text
model_promotion_manifest.json
```

and checks approval/readiness and blockers.

### Inference guard

For the `inference_guard` stage, AERIS looks for:

```text
inference_guard_report.json
```

and checks `passed=True` and no errors.

## Boundary

This slice does not run geometry, aero, QC, ML, promotion, or inference.

It validates recorded evidence only. The workflow remains a guided state/evidence layer, not a hidden campaign runner.

## Example

```bash
aeris workflow validate \
  --workflow data/workflows/bwb_training_v1_canary_existing_dataset
```

Compact operator view:

```bash
aeris workflow summary \
  --workflow data/workflows/bwb_training_v1_canary_existing_dataset
```

Doctor alias:

```bash
aeris workflow doctor \
  --workflow data/workflows/bwb_training_v1_canary_existing_dataset
```

## Next slice

The next logical slice is workflow-aware GUI surfacing:

```text
workflow selector
→ status/next-stage display
→ doctor report viewer
→ artifact links
→ blockers/warnings panel
```

The backend now has enough truth-checking to support that without turning the GUI into decorative nonsense.
