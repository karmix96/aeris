from __future__ import annotations

from aeris.workflow.coverage import (
    VALID_COVERAGE_STATUSES,
    WORKFLOW_COVERAGE_SPEC,
    build_workflow_coverage_report,
)


def test_workflow_coverage_spec_contains_expected_stage_drivers() -> None:
    pairs = {(spec.command_group, spec.command_name) for spec in WORKFLOW_COVERAGE_SPEC}

    assert ("dataset", "generate") in pairs
    assert ("aero", "run") in pairs
    assert ("aero", "sweep") in pairs
    assert ("dataset", "aero-generate") in pairs
    assert ("dataset", "aero-qc") in pairs
    assert ("dataset", "curate-aero") in pairs
    assert ("dataset", "promote-aero") in pairs
    assert ("ml", "eda") in pairs
    assert ("ml", "train") in pairs
    assert ("ml", "compare") in pairs
    assert ("ml", "compare-seeds") in pairs
    assert ("ml", "promote-model") in pairs
    assert ("ml", "check-inference-inputs") in pairs
    assert ("ml", "build-delta-dataset") in pairs
    assert ("ml", "train-delta-model") in pairs
    assert ("ml", "evaluate-delta-model") in pairs
    assert ("ml", "suggest-samples") in pairs


def test_workflow_coverage_report_shape_and_status_values() -> None:
    report = build_workflow_coverage_report()

    assert report["report_type"] == "workflow_coverage_audit"
    assert report["summary"]["entry_count"] == len(WORKFLOW_COVERAGE_SPEC)
    assert report["summary"]["required_entry_count"] > 0
    assert report["entries"]

    statuses = {entry["coverage_status"] for entry in report["entries"]}
    assert statuses <= VALID_COVERAGE_STATUSES


def test_workflow_coverage_detects_registered_commands() -> None:
    report = build_workflow_coverage_report()
    by_command = {
        (entry["command_group"], entry["command_name"]): entry for entry in report["entries"]
    }

    assert by_command[("dataset", "generate")]["command_exists"] is True
    assert by_command[("aero", "sweep")]["command_exists"] is True
    assert by_command[("ml", "train")]["command_exists"] is True
    assert isinstance(by_command[("aero", "sweep")]["supports_workflow_option"], bool)
