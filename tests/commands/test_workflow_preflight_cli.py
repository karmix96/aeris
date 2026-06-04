from __future__ import annotations

import json

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_workflow_preflight_help_runs() -> None:
    result = runner.invoke(app, ["workflow", "preflight", "--help"])
    assert result.exit_code == 0, result.output
    assert "--config" in result.output
    assert "--alpha-values" in result.output
    assert "--output-json" in result.output


def test_workflow_preflight_runs_and_writes_json(tmp_path) -> None:
    output_json = tmp_path / "workflow_preflight_report.json"

    result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "workflow",
            "preflight",
            "--config",
            "configs/geometry/bwb_training_v1.yaml",
            "--n",
            "50",
            "--output-json",
            str(output_json),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "estimated_aero_case_count" in result.output
    assert output_json.exists()

    data = json.loads(output_json.read_text(encoding="utf-8"))
    assert data["report_type"] == "workflow_operational_preflight"
    assert data["estimated_aero_case_count"] == 50 * 4 * 1 * 2 * 2 * 3
