from __future__ import annotations

import json
from pathlib import Path

from aeris.dynamics.validation import validate_dynamics_run, write_dynamics_validation_report


def _write_valid_artifacts(run_dir: Path) -> None:
    dyn = run_dir / "dynamics"
    dyn.mkdir(parents=True)
    dyn.joinpath("dynamics_foundation.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2.0",
                "mass_properties": {
                    "mass_kg": 12.5,
                    "x_cg_m": 0.40,
                    "inertia": {"ixx_kg_m2": 0.8, "iyy_kg_m2": 1.5, "izz_kg_m2": 2.1},
                },
                "stability_metrics": {
                    "x_np_m": 0.55,
                    "x_cg_m": 0.40,
                    "mac_m": 0.50,
                    "static_margin": 0.30,
                    "static_margin_percent_mac": 30.0,
                    "cma": -1.0,
                },
                "state_space_preparation": {"ready_for_eigenanalysis": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    dyn.joinpath("trim_result.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2.0",
                "mode": "longitudinal_linearised_dual",
                "longitudinal": {
                    "valid": True,
                    "alpha_current_deg": 2.0,
                    "control_input_deg": 0.0,
                    "cm_current": -0.10,
                    "cma_per_rad": -2.0,
                    "cmde_per_rad": -1.0,
                    "delta_alpha_rad": -0.05,
                    "delta_alpha_deg": -2.8648,
                    "alpha_trim_deg": -0.8648,
                    "alpha_trim_in_bounds": True,
                    "delta_de_rad": -0.10,
                    "delta_de_deg": -5.7296,
                    "de_trim_deg": -5.7296,
                    "de_trim_in_bounds": True,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    eigs_long = [
        {"real": -2.0, "imag": 3.0},
        {"real": -2.0, "imag": -3.0},
        {"real": -0.1, "imag": 0.2},
        {"real": -0.1, "imag": -0.2},
    ]
    eigs_lat = [
        {"real": -4.0, "imag": 0.0},
        {"real": -0.02, "imag": 0.0},
        {"real": -0.4, "imag": 1.2},
        {"real": -0.4, "imag": -1.2},
    ]
    dyn.joinpath("state_space_result.json").write_text(
        json.dumps(
            {
                "schema_version": "state_space_result_v0.2",
                "overall_status": "completed",
                "longitudinal": {
                    "valid": True,
                    "a_matrix": [[-1, 0, 0, -9.81], [0, -2, 28, 0], [0, -1, -4, 0], [0, 0, 1, 0]],
                    "all_eigenvalues": eigs_long,
                },
                "lateral_directional": {
                    "valid": True,
                    "a_matrix": [[-1, 0, -28, 9.81], [0, -4, 0, 0], [1, 0, -1, 0], [0, 1, 0, 0]],
                    "all_eigenvalues": eigs_lat,
                },
                "linear_stability_summary": {
                    "overall_known": True,
                    "overall_linear_stable": True,
                    "total_unstable_eigenvalue_count": 0,
                    "max_real_eigenvalue": -0.02,
                },
                "limitations": ["local linear diagnostic"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_validate_dynamics_run_passes_for_consistent_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_valid_artifacts(run_dir)
    report = validate_dynamics_run(run_dir)
    assert report["passed"] is True
    assert report["error_count"] == 0
    assert report["artifacts"]["foundation"]["valid"] is True
    assert report["artifacts"]["trim"]["valid"] is True
    assert report["artifacts"]["state_space"]["valid"] is True


def test_validate_dynamics_run_catches_trim_formula_mismatch(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_valid_artifacts(run_dir)
    path = run_dir / "dynamics" / "trim_result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["longitudinal"]["delta_alpha_rad"] = 123.0
    path.write_text(json.dumps(data), encoding="utf-8")
    report = validate_dynamics_run(run_dir)
    assert report["passed"] is False
    assert any("delta_alpha_rad formula mismatch" in e for e in report["errors"])


def test_validate_dynamics_run_catches_state_space_summary_mismatch(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_valid_artifacts(run_dir)
    path = run_dir / "dynamics" / "state_space_result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["linear_stability_summary"]["total_unstable_eigenvalue_count"] = 99
    path.write_text(json.dumps(data), encoding="utf-8")
    report = validate_dynamics_run(run_dir)
    assert report["passed"] is False
    assert any("unstable eigenvalue count mismatch" in e for e in report["errors"])


def test_write_dynamics_validation_report(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_valid_artifacts(run_dir)
    report = validate_dynamics_run(run_dir)
    out = write_dynamics_validation_report(report, run_dir / "dynamics")
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["passed"] is True
