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
    assert status["next_required_stage"]["name"] == "aero_dataset"
