from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _write_minimal_foundation(run_dir: Path, *, bad_static_margin: bool = False) -> None:
    dyn = run_dir / "dynamics"
    dyn.mkdir(parents=True)
    dyn.joinpath("dynamics_foundation.json").write_text(
        json.dumps(
            {
                "mass_properties": {"mass_kg": 12.5, "x_cg_m": 0.40, "inertia": {}},
                "stability_metrics": {
                    "x_np_m": 0.55,
                    "x_cg_m": 0.40,
                    "mac_m": 0.50,
                    "static_margin": 999.0 if bad_static_margin else 0.30,
                    "static_margin_percent_mac": 30.0,
                    "cma": -1.0,
                },
                "state_space_preparation": {"ready_for_eigenanalysis": False},
            }
        ),
        encoding="utf-8",
    )


def test_dynamics_validate_help_runs() -> None:
    result = runner.invoke(app, ["dynamics", "validate", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--fail-on-error" in result.stdout


def test_dynamics_validate_cli_writes_report(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_minimal_foundation(run_dir)
    result = runner.invoke(app, ["dynamics", "validate", "--run-dir", str(run_dir)])
    assert result.exit_code == 0, result.stdout
    assert "Dynamics validation completed" in result.stdout
    report = run_dir / "dynamics" / "dynamics_validation_report.json"
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is True


def test_dynamics_validate_cli_fail_on_error_exits_nonzero(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_minimal_foundation(run_dir, bad_static_margin=True)
    result = runner.invoke(app, ["dynamics", "validate", "--run-dir", str(run_dir), "--fail-on-error"])
    assert result.exit_code == 1
    payload = json.loads((run_dir / "dynamics" / "dynamics_validation_report.json").read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert any("static_margin mismatch" in e for e in payload["errors"])
