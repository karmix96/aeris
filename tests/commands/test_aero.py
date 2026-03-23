"""
Tests: commands.aero

Purpose:
    Validate CLI-level behavior for aerodynamic run and sweep commands.

What is tested:
    - Help surfaces render correctly
    - Exactly one geometry source mode is required
    - Dataset mode requires geometry_id
    - Invalid sweep list input fails clearly

Why it matters:
    The aero command layer has the highest orchestration complexity
    and must fail early and clearly on bad operator input.
"""

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_aero_help_runs() -> None:
    result = runner.invoke(app, ["aero", "--help"])
    assert result.exit_code == 0


def test_aero_requires_exactly_one_source() -> None:
    result = runner.invoke(
        app,
        [
            "aero",
            "run",
            "--alpha", "4",
            "--config", "configs/geometry/baseline_bwb.yaml",
            "--run-dir", "data/runs/some_run",
        ],
    )
    assert result.exit_code != 0
    assert "Provide exactly one of" in result.output


def test_aero_dataset_requires_geometry_id() -> None:
    result = runner.invoke(
        app,
        [
            "aero",
            "run",
            "--alpha", "4",
            "--dataset", "data/datasets/some_dataset",
        ],
    )
    assert result.exit_code != 0
    assert "--dataset requires --geometry-id" in result.output


def test_aero_rejects_bad_float_list() -> None:
    result = runner.invoke(
        app,
        [
            "aero",
            "sweep",
            "--config", "configs/geometry/baseline_bwb.yaml",
            "--alpha-values", "0,foo,4",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid float value 'foo'" in result.output