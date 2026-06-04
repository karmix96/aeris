from __future__ import annotations

from typer.testing import CliRunner

from aeris.cli import app
from aeris.workflow.coverage import build_workflow_coverage_report

runner = CliRunner()


def test_optional_ml_branch_commands_expose_workflow_help() -> None:
    commands = [
        "build-delta-dataset",
        "train-delta-model",
        "evaluate-delta-model",
        "suggest-samples",
    ]

    for command in commands:
        result = runner.invoke(app, ["ml", command, "--help"])
        assert result.exit_code == 0, result.output
        assert "--workflow" in result.output


def test_workflow_coverage_has_no_optional_workflow_gaps() -> None:
    report = build_workflow_coverage_report()

    assert report["summary"]["optional_gap_count"] == 0
    assert report["summary"]["status_counts"]["missing_workflow_option"] == 0

    by_command = {
        (entry["command_group"], entry["command_name"]): entry
        for entry in report["entries"]
    }

    for command in [
        "build-delta-dataset",
        "train-delta-model",
        "evaluate-delta-model",
        "suggest-samples",
    ]:
        entry = by_command[("ml", command)]
        assert entry["command_exists"] is True
        assert entry["supports_workflow_option"] is True
        assert entry["coverage_status"] == "covered"
