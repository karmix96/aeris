from __future__ import annotations

import json
from pathlib import Path

from aeris.dynamics.models import InertiaPlaceholders, MassProperties
from aeris.dynamics.state_space_run import compute_state_space_result, write_state_space_result


def _write_fake_run(root: Path, *, omit_cma: bool = False) -> Path:
    run_dir = root / "run"
    (run_dir / "geometry").mkdir(parents=True)
    sad = {
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
        "CYp": 0.0,
        "CYr": 0.0,
    }
    if omit_cma:
        sad.pop("Cma")
    (run_dir / "aero_result.json").write_text(
        json.dumps(
            {
                "schema_version": "aero_result_v1",
                "status": "success",
                "solver_id": "fake_avl",
                "scalars": {"cl": 0.38, "cd": 0.045, "cm": -0.08, "x_np": 0.55},
                "stability_axis_derivatives": sad,
                "solver_metadata": {
                    "flight_condition": {
                        "alpha_deg": 2.0,
                        "velocity_mps": 28.0,
                        "altitude_m": 1500.0,
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "geometry" / "geometry_summary.json").write_text(
        json.dumps(
            {
                "reference_values": {
                    "area_m2": 0.72,
                    "span_m": 3.2,
                    "mean_aerodynamic_chord_m": 0.55,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return run_dir


def _mass() -> MassProperties:
    return MassProperties(
        mass_kg=12.5,
        x_cg_m=0.4,
        y_cg_m=0.0,
        z_cg_m=0.0,
        inertia=InertiaPlaceholders(ixx_kg_m2=0.8, iyy_kg_m2=1.5, izz_kg_m2=2.1),
    )


def test_compute_state_space_result_completed(tmp_path: Path) -> None:
    run_dir = _write_fake_run(tmp_path)
    result = compute_state_space_result(run_dir=run_dir, mass_properties=_mass())
    assert result["schema_version"] == "state_space_result_v0.2"
    assert result["overall_status"] == "completed"
    assert result["input_summary"]["missing_inputs"] == []
    assert result["longitudinal"]["valid"] is True
    assert result["lateral_directional"]["valid"] is True
    assert len(result["longitudinal"]["all_eigenvalues"]) == 4
    assert len(result["lateral_directional"]["all_eigenvalues"]) == 4
    assert result["longitudinal"]["a_matrix"] is not None
    assert result["lateral_directional"]["a_matrix"] is not None

    summary = result["linear_stability_summary"]
    assert summary["method"] == "full_eigenvalue_real_part_scan"
    assert summary["overall_known"] is True
    assert summary["valid_section_count"] == 2
    assert summary["sections"]["longitudinal"]["eigenvalue_count"] == 4
    assert summary["sections"]["lateral_directional"]["eigenvalue_count"] == 4
    assert isinstance(summary["sections"]["longitudinal"]["has_unstable_eigenvalue"], bool)


def test_compute_state_space_result_blocks_when_missing_required_derivative(tmp_path: Path) -> None:
    run_dir = _write_fake_run(tmp_path, omit_cma=True)
    result = compute_state_space_result(run_dir=run_dir, mass_properties=_mass())
    assert result["overall_status"] == "blocked_missing_inputs"
    assert "Cma" in result["input_summary"]["missing_inputs"]
    assert result["longitudinal"]["valid"] is False
    assert result["linear_stability_summary"]["overall_known"] is False
    assert result["linear_stability_summary"]["overall_linear_stable"] is None


def test_write_state_space_result(tmp_path: Path) -> None:
    run_dir = _write_fake_run(tmp_path)
    result = compute_state_space_result(run_dir=run_dir, mass_properties=_mass())
    path = write_state_space_result(result, run_dir / "dynamics")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["overall_status"] == "completed"
    assert "linear_stability_summary" in payload
