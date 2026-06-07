from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _write_state_space_result(run_dir: Path) -> None:
    dyn = run_dir / "dynamics"
    dyn.mkdir(parents=True)
    (dyn / "state_space_result.json").write_text(
        json.dumps(
            {
                "schema_version": "state_space_result_v0.2",
                "overall_status": "completed",
                "linear_stability_summary": {
                    "overall_linear_stable": False,
                    "total_unstable_eigenvalue_count": 1,
                    "max_real_eigenvalue": 0.05,
                },
                "longitudinal": {
                    "valid": True,
                    "short_period": {"eigenvalue_real": -4.0, "eigenvalue_imag": 10.0, "stable": True},
                    "phugoid": {"eigenvalue_real": -0.1, "eigenvalue_imag": 0.0, "stable": True},
                    "all_eigenvalues": [
                        {"real": -4.0, "imag": 10.0},
                        {"real": -4.0, "imag": -10.0},
                        {"real": -0.1, "imag": 0.0},
                        {"real": -0.2, "imag": 0.0},
                    ],
                },
                "lateral_directional": {
                    "valid": True,
                    "roll_subsidence": {"eigenvalue_real": -20.0, "eigenvalue_imag": 0.0, "stable": True},
                    "spiral": {"eigenvalue_real": 0.05, "eigenvalue_imag": 0.0, "stable": False},
                    "dutch_roll": {"eigenvalue_real": -0.2, "eigenvalue_imag": 1.0, "stable": True},
                    "all_eigenvalues": [
                        {"real": -20.0, "imag": 0.0},
                        {"real": -0.2, "imag": 1.0},
                        {"real": -0.2, "imag": -1.0},
                        {"real": 0.05, "imag": 0.0},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def test_dynamics_plot_state_space_help_runs() -> None:
    result = runner.invoke(app, ["dynamics", "plot-state-space", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--plot" in result.stdout


def test_dynamics_plot_state_space_cli_writes_plots(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_state_space_result(run_dir)

    result = runner.invoke(app, ["dynamics", "plot-state-space", "--run-dir", str(run_dir), "--plot", "all", "--dpi", "90"])

    assert result.exit_code == 0, result.stdout
    assert "State-space plots generated" in result.stdout
    manifest_path = run_dir / "dynamics" / "plots" / "state_space_plot_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["plot_count"] == 2
    assert Path(manifest["artifacts"]["eigenvalues_png"]).exists()
    assert Path(manifest["artifacts"]["mode_summary_png"]).exists()
