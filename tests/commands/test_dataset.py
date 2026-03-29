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

def test_dataset_generate_help_mentions_qc_preset() -> None:
    result = runner.invoke(app, ["dataset", "generate", "--help"])
    assert result.exit_code == 0
    assert "--qc-preset" in result.stdout
    assert "production" in result.stdout
    assert "promotion_strict" in result.stdout


def test_dataset_aero_generate_help_mentions_qc_preset() -> None:
    result = runner.invoke(app, ["dataset", "aero-generate", "--help"])
    assert result.exit_code == 0
    assert "--qc-preset" in result.stdout
    assert "production" in result.stdout
    assert "promotion_strict" in result.stdout

def test_dataset_aero_generate_help_mentions_override_behavior() -> None:
    result = runner.invoke(app, ["dataset", "aero-generate", "--help"])
    assert result.exit_code == 0
    assert "overrides" in result.stdout.lower()

def test_dataset_curate_aero_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "curate-aero", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--reject-incomple" in result.stdout or "incomplete." in result.stdout

def test_dataset_aero_generate_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "aero-generate", "--help"])
    assert result.exit_code == 0
    assert "Generate a geometry dataset and enrich it with aero/control sweeps" in result.stdout