"""
Tests: commands.geometry

Purpose:
    Validate basic CLI behavior for geometry commands.

What is tested:
    - Geometry command help renders
    - Geometry generate help renders

Why it matters:
    Confirms the command group is wired correctly into the root CLI.
"""

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_geometry_help_runs() -> None:
    result = runner.invoke(app, ["geometry", "--help"])
    assert result.exit_code == 0


def test_geometry_generate_help_runs() -> None:
    result = runner.invoke(app, ["geometry", "generate", "--help"])
    assert result.exit_code == 0