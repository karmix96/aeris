from __future__ import annotations

from typer.testing import CliRunner

# Adjust this import if your cli entry object is named differently.
# Common possibilities:
# from aeris.cli import app
# from aeris.cli import main as app
from aeris.cli import app

runner = CliRunner()


def test_aero_help_runs() -> None:
    result = runner.invoke(app, ["aero", "--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "inspect" in result.stdout
    assert "sweep" in result.stdout


def test_aero_run_help_runs() -> None:
    result = runner.invoke(app, ["aero", "run", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.stdout or "--run-dir" in result.stdout
    assert "--alpha" in result.stdout
    assert "--velocity" in result.stdout
    assert "--altitude" in result.stdout


def test_aero_inspect_help_runs() -> None:
    result = runner.invoke(app, ["aero", "inspect", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--json" in result.stdout


def test_aero_sweep_help_runs() -> None:
    result = runner.invoke(app, ["aero", "sweep", "--help"])
    assert result.exit_code == 0
    assert "--alpha-values" in result.stdout
    assert "--beta-values" in result.stdout
    assert "--velocity-values" in result.stdout
    assert "--q-values" in result.stdout


def test_aero_sweep_inspect_help_runs() -> None:
    result = runner.invoke(app, ["aero", "sweep-inspect", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--json" in result.stdout


def test_aero_sweep_case_inspect_help_runs() -> None:
    result = runner.invoke(app, ["aero", "sweep-case-inspect", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--case-index" in result.stdout or "--case-label" in result.stdout
    assert "--json" in result.stdout