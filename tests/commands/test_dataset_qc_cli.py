from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dataset_qc_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "qc", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--profile" in result.stdout


def test_dataset_aero_qc_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "aero-qc", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--profile" in result.stdout