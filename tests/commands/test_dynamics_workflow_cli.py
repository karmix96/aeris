from __future__ import annotations

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dynamics_batch_labels_exposes_workflow_option() -> None:
    result = runner.invoke(app, ["dynamics", "batch-labels", "--help"])
    assert result.exit_code == 0
    assert "--workflow" in result.stdout
    assert "workflow" in result.stdout.lower()


def test_dynamics_build_ml_dataset_exposes_workflow_option() -> None:
    result = runner.invoke(app, ["dynamics", "build-ml-dataset", "--help"])
    assert result.exit_code == 0
    assert "--workflow" in result.stdout
    assert "workflow" in result.stdout.lower()
