from __future__ import annotations

from aeris.workflow.coverage import WORKFLOW_COVERAGE_SPEC, build_workflow_coverage_report
from aeris.workflow.spine import DEFAULT_STAGE_DEFINITIONS


def test_dynamics_workflow_stages_are_declared_optional() -> None:
    stages = {stage["name"]: stage for stage in DEFAULT_STAGE_DEFINITIONS}
    assert stages["dynamics_batch_labels"]["required"] is False
    assert stages["flyability_ml_dataset"]["required"] is False


def test_dynamics_commands_are_in_workflow_coverage_and_covered() -> None:
    pairs = {(spec.command_group, spec.command_name) for spec in WORKFLOW_COVERAGE_SPEC}
    assert ("dynamics", "batch-labels") in pairs
    assert ("dynamics", "build-ml-dataset") in pairs

    report = build_workflow_coverage_report()
    by_command = {(entry["command_group"], entry["command_name"]): entry for entry in report["entries"]}
    assert by_command[("dynamics", "batch-labels")]["coverage_status"] == "covered"
    assert by_command[("dynamics", "build-ml-dataset")]["coverage_status"] == "covered"
