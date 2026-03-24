"""
Tests: commands.dataset

Purpose:
    Validate basic CLI behavior for dataset commands.

What is tested:
    - Dataset command help renders
    - Dataset generate help renders
    - Dataset inspect help renders

Why it matters:
    Confirms dataset command registration and operator entrypoints work.
"""

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dataset_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "--help"])
    assert result.exit_code == 0


def test_dataset_generate_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "generate", "--help"])
    assert result.exit_code == 0


def test_dataset_inspect_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "inspect", "--help"])
    assert result.exit_code == 0