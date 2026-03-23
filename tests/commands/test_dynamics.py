"""
Tests: commands.dynamics

Purpose:
    Validate CLI-level behavior for dynamics utilities.

What is tested:
    - Help surfaces render correctly
    - CG sweep rejects invalid ranges
    - CG sweep rejects meaningless point counts

Why it matters:
    These commands are operator-facing and should reject bad inputs
    before deeper analysis code is invoked.
"""

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dynamics_help_runs() -> None:
    result = runner.invoke(app, ["dynamics", "--help"])
    assert result.exit_code == 0


def test_cg_sweep_rejects_reversed_range() -> None:
    result = runner.invoke(
        app,
        [
            "dynamics",
            "cg-sweep",
            "--run-dir", ".",
            "--mass-kg", "10",
            "--cg-min-m", "2.0",
            "--cg-max-m", "1.0",
        ],
    )
    assert result.exit_code != 0
    assert "--cg-min-m must be <=" in result.output


def test_cg_sweep_rejects_too_few_points() -> None:
    result = runner.invoke(
        app,
        [
            "dynamics",
            "cg-sweep",
            "--run-dir", ".",
            "--mass-kg", "10",
            "--cg-min-m", "0.1",
            "--cg-max-m", "0.2",
            "--n", "1",
        ],
    )
    assert result.exit_code != 0
    assert "--n must be >=" in result.output