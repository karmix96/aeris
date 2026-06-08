from __future__ import annotations

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dynamics_build_ml_dataset_help() -> None:
    result = runner.invoke(app, ["dynamics", "build-ml-dataset", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--source" in result.stdout
    assert "--output-dir" in result.stdout
