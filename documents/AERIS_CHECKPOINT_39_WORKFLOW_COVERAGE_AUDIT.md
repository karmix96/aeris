# AERIS Checkpoint 39 — Workflow Coverage Audit

## Purpose

This slice adds a formal audit for the guided-workflow contract.

AERIS is moving toward an evidence-driven workstation GUI. The GUI must not guess whether a stage can advance. It must know whether the backend command exists and whether that command can auto-record evidence into a workflow root.

The bug that triggered this slice was simple: a backend command may exist but still fail to advance workflow state if it does not support --workflow.

## Added

- src/aeris/workflow/coverage.py
- aeris workflow coverage
- tests/workflow/test_workflow_coverage.py
- tests/commands/test_workflow_cli.py
- documents/AERIS_CHECKPOINT_39_WORKFLOW_COVERAGE_AUDIT.md

## Command

Run the audit:

    aeris workflow coverage

Write JSON report:

    aeris workflow coverage --output-json workflow_coverage_report.json

Print machine-readable JSON:

    aeris workflow coverage --json

## Result

The required workflow-driving commands are covered:

- geometry_dataset
- aero_sweep
- aero_dataset
- dataset_qc
- curation
- promotion
- ml_eda
- ml_training
- model_comparison
- model_promotion
- inference_guard

The audit currently reports optional workflow gaps for:

- multifidelity_delta_dataset
- multifidelity_delta_model
- multifidelity_evaluation
- active_learning

These are not blockers for the required workflow chain.

## Coverage statuses

- covered
- missing_workflow_option
- missing_command
- standalone_only
- manual_record_only
- needs_review

## Design boundary

This slice does not add workflow auto-recording to every command.

It exposes the truth first. If the report says missing_workflow_option, the next patch should add that option and the corresponding auto-record behavior in the owning command. No GUI workaround. No fake state.

## Validation

    pytest -q tests/workflow/test_workflow_coverage.py
    pytest -q tests/commands/test_workflow_cli.py
    aeris workflow coverage --help
    aeris workflow coverage
    aeris workflow coverage --output-json workflow_coverage_report.json
