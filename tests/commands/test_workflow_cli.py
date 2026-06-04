from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_workflow_help_runs() -> None:
    result = runner.invoke(app, ["workflow", "--help"])
    assert result.exit_code == 0


def test_workflow_init_status_next_record_stage_cli(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "wf_cli"

    init_result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "init", "--name", "cli_demo", "--output-dir", str(workflow_dir)],
    )
    assert init_result.exit_code == 0, init_result.output
    assert "Workflow initialized" in init_result.output
    assert (workflow_dir / "workflow_manifest.json").exists()
    assert (workflow_dir / "workflow_status.json").exists()

    next_result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "next", "--workflow", str(workflow_dir), "--json"],
    )
    assert next_result.exit_code == 0, next_result.output
    next_payload = json.loads(next_result.output)
    assert next_payload["next_required_stage"]["name"] == "geometry_dataset"

    record_result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "workflow",
            "record-stage",
            "--workflow",
            str(workflow_dir),
            "--stage",
            "geometry_dataset",
            "--status",
            "complete",
            "--artifact",
            "data/datasets/demo_geom",
            "--notes",
            "passed canary",
        ],
    )
    assert record_result.exit_code == 0, record_result.output
    assert "Workflow stage recorded" in record_result.output
    assert (workflow_dir / "stages" / "geometry_dataset" / "stage_status.json").exists()

    status_result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "status", "--workflow", str(workflow_dir), "--json"],
    )
    assert status_result.exit_code == 0, status_result.output
    status = json.loads(status_result.output)
    assert status["stages"]["geometry_dataset"]["status"] == "complete"
    assert status["next_required_stage"]["name"] == "aero_sweep"


def test_workflow_validate_summary_doctor_cli(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "wf_validate_cli"
    init_result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "init", "--name", "cli_validate", "--output-dir", str(workflow_dir)],
    )
    assert init_result.exit_code == 0, init_result.output

    summary_result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "summary", "--workflow", str(workflow_dir)],
    )
    assert summary_result.exit_code == 0, summary_result.output
    assert "Workflow summary" in summary_result.output
    assert "validation_health: incomplete" in summary_result.output

    validate_result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "validate", "--workflow", str(workflow_dir)],
    )
    assert validate_result.exit_code == 0, validate_result.output
    assert "Workflow validation" in validate_result.output
    assert (workflow_dir / "workflow_validation_report.json").exists()

    doctor_result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "doctor", "--workflow", str(workflow_dir), "--json"],
    )
    assert doctor_result.exit_code == 0, doctor_result.output
    payload = json.loads(doctor_result.output)
    assert payload["schema_version"] == "aeris.workflow_validation.v1"
    assert payload["health"] == "incomplete"


def test_workflow_coverage_help_runs() -> None:
    result = runner.invoke(app, ["workflow", "coverage", "--help"])
    assert result.exit_code == 0, result.output
    assert "coverage" in result.output.lower()


def test_workflow_coverage_runs() -> None:
    result = runner.invoke(app, ["--no-check-writable", "workflow", "coverage"])
    assert result.exit_code == 0, result.output
    assert "Workflow coverage audit" in result.output
    assert "aeris aero sweep" in result.output


def test_workflow_coverage_json_output(tmp_path: Path) -> None:
    output_json = tmp_path / "workflow_coverage_report.json"
    result = runner.invoke(
        app,
        ["--no-check-writable", "workflow", "coverage", "--output-json", str(output_json), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert output_json.exists()
    data = json.loads(output_json.read_text(encoding="utf-8"))
    assert data["report_type"] == "workflow_coverage_audit"
    assert data["entries"]
    assert data["summary"]["entry_count"] == len(data["entries"])


def test_workflow_templates_command_runs() -> None:
    result = runner.invoke(app, ["--no-check-writable", "workflow", "templates"])
    assert result.exit_code == 0, result.output
    assert "canary" in result.output
    assert "production" in result.output


def test_workflow_templates_named_command_runs() -> None:
    result = runner.invoke(app, ["--no-check-writable", "workflow", "templates", "--name", "canary"])
    assert result.exit_code == 0, result.output
    assert '"name": "canary"' in result.output


def test_workflow_init_accepts_template(tmp_path: Path) -> None:
    out = tmp_path / "wf_canary"
    result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "workflow",
            "init",
            "--name",
            "demo_canary",
            "--template",
            "canary",
            "--output-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "template: canary" in result.output
    assert (out / "workflow_template.json").exists()
