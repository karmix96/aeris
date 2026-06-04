# AERIS Checkpoint 41 — Workflow Templates

## Purpose

This slice adds named workflow initialization templates so the guided workstation can start from a clear operating mode instead of a single generic workflow.

Templates are still evidence/state presets only. They do not run geometry, solvers, QC, ML, multifidelity, active learning, or MDAO.

## Added

```text
src/aeris/workflow/templates.py
aeris workflow templates
aeris workflow init --template <name>
tests/workflow/test_workflow_templates.py
```

## Built-in templates

```text
canary
production
multifidelity
active_learning
```

## Commands

List templates:

```bash
aeris workflow templates
```

Inspect one template:

```bash
aeris workflow templates --name canary
```

Initialize a workflow from a template:

```bash
aeris workflow init \
  --name bwb_canary \
  --template canary \
  --output-dir data/workflows/bwb_canary
```

## Boundary

This slice does not add a campaign runner and does not duplicate domain logic. The CLI/domain commands remain the execution surface. The template only records the intended workflow shape and guidance.
