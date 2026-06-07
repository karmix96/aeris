from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _write_fake_run(root: Path) -> Path:
    run_dir = root / "run"
    (run_dir / "geometry").mkdir(parents=True)
    (run_dir / "aero_result.json").write_text(
        json.dumps(
            {
                "schema_version": "aero_result_v1",
                "status": "success",
                "solver_id": "fake_avl",
                "scalars": {"cl": 0.38, "cd": 0.045, "cm": -0.08, "x_np": 0.55},
                "stability_axis_derivatives": {
                    "CLa": 5.2,
                    "Cma": -0.9,
                    "Cmq": -8.0,
                    "CYb": -0.25,
                    "Clb": -0.06,
                    "Cnb": 0.09,
                    "Clp": -0.42,
                    "Cnp": -0.02,
                    "Clr": 0.04,
                    "Cnr": -0.15,
                },
                "solver_metadata": {
                    "flight_condition": {"alpha_deg": 2.0, "velocity_mps": 28.0, "altitude_m": 1500.0}
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "geometry" / "geometry_summary.json").write_text(
        json.dumps(
            {"reference_values": {"area_m2": 0.72, "span_m": 3.2, "mean_aerodynamic_chord_m": 0.55}}
        ),
        encoding="utf-8",
    )
    return run_dir


def _write_mass_config(root: Path) -> Path:
    path = root / "mass.yaml"
    path.write_text(
        """
mass_properties:
  mass_kg: 12.5
  x_cg_m: 0.40
  y_cg_m: 0.0
  z_cg_m: 0.0
  ixx_kg_m2: 0.80
  iyy_kg_m2: 1.50
  izz_kg_m2: 2.10
""".strip(),
        encoding="utf-8",
    )
    return path


def test_dynamics_state_space_help_runs() -> None:
    result = runner.invoke(app, ["dynamics", "state-space", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--mass-config" in result.stdout
    assert "state-space" in result.stdout.lower()


def test_dynamics_state_space_cli_writes_report(tmp_path: Path) -> None:
    run_dir = _write_fake_run(tmp_path)
    mass_config = _write_mass_config(tmp_path)
    result = runner.invoke(app, ["dynamics", "state-space", "--run-dir", str(run_dir), "--mass-config", str(mass_config)])
    assert result.exit_code == 0, result.stdout
    out = run_dir / "dynamics" / "state_space_result.json"
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["overall_status"] == "completed"
    assert "linear_stability_summary" in payload
    assert "linear_stability" in result.stdout


def test_dynamics_state_space_inspect_cli_reads_report(tmp_path: Path) -> None:
    run_dir = _write_fake_run(tmp_path)
    mass_config = _write_mass_config(tmp_path)
    runner.invoke(app, ["dynamics", "state-space", "--run-dir", str(run_dir), "--mass-config", str(mass_config)])
    result = runner.invoke(app, ["dynamics", "state-space-inspect", "--run-dir", str(run_dir)])
    assert result.exit_code == 0, result.stdout
    assert "State-Space Inspection" in result.stdout
    assert "Linear stability" in result.stdout
    assert "Longitudinal valid" in result.stdout
