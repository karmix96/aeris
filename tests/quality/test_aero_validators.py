from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.quality.pipeline_api import run_aero_dataset_qc


def _make_aero_dataset(
    dataset_root: Path,
    *,
    rows: list[dict],
    successful_aero_rows: int | None = None,
    manifest_updates: dict | None = None,
) -> None:
    dataset_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "status": "success",
        "successful_aero_rows": len(rows) if successful_aero_rows is None else successful_aero_rows,
    }
    if manifest_updates:
        manifest.update(manifest_updates)
    (dataset_root / "aero_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    pd.DataFrame(rows).to_csv(dataset_root / "aero_dataset.csv", index=False)


def _healthy_aero_rows() -> list[dict]:
    rows: list[dict] = []
    geometry_id = "geom_00001"
    velocity = 28.0
    altitude = 1500.0

    for alpha_deg, cl_base in [(0.0, 0.20), (2.0, 0.40), (4.0, 0.60)]:
        for control_input_deg, cm in [(-5.0, 0.05), (0.0, 0.00), (5.0, -0.05)]:
            rows.append(
                {
                    "geometry_id": geometry_id,
                    "alpha_deg": alpha_deg,
                    "velocity_mps": velocity,
                    "altitude_m": altitude,
                    "control_input_deg": control_input_deg,
                    "cl": cl_base + 0.01 * control_input_deg,
                    "cd": 0.030 + 0.002 * (alpha_deg / 2.0),
                    "cm": cm,
                    "cy": 0.00,
                    "cl_roll": 0.00,
                    "cn": 0.00,
                    "beta_deg": 0.0,
                    "geometry_declares_controls": True,
                    "airplane_has_controls": True,
                    "diag_airplane_has_control_surfaces": True,
                    "diag_airplane_avl_has_control_blocks": True,
                    "diag_keystrokes_has_d1_command": True,
                    "diag_stdout_control_variables": 1,
                }
            )
    return rows


def test_aero_basic_profile_passes_for_healthy_dataset(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    _make_aero_dataset(dataset_root, rows=_healthy_aero_rows())

    report = run_aero_dataset_qc(dataset_root, profile="basic")

    assert report["passed"] is True
    assert report["errors"] == []
    assert report["metrics"]["profile"] == "basic"


def test_aero_strict_warns_on_ld_blowup_while_basic_passes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    rows = _healthy_aero_rows()

    # Isolate L/D semantics:
    # - CL=1.0 is inside the basic |CL| <= 3 sanity range.
    # - CD=0.001 gives L/D=1000, so strict L/D sanity should warn.
    # - Use the alpha=4, ctrl=-5 row so CL-alpha remains monotonic.
    blowup_row = next(
        row for row in rows
        if row["alpha_deg"] == 4.0 and row["control_input_deg"] == -5.0
    )
    blowup_row["cl"] = 1.0
    blowup_row["cd"] = 0.001

    _make_aero_dataset(dataset_root, rows=rows)

    basic_report = run_aero_dataset_qc(dataset_root, profile="basic")
    strict_report = run_aero_dataset_qc(dataset_root, profile="strict")

    assert basic_report["passed"] is True, (
        "This regression must isolate L/D semantics; basic QC should still pass. "
        f"errors={basic_report['errors']}"
    )

    ld_warnings = [
        msg for msg in strict_report.get("warnings", [])
        if "L/D" in msg and "500" in msg
    ]
    assert ld_warnings, (
        f"L/D blowup should trigger a strict warning. "
        f"warnings={strict_report['warnings']}, errors={strict_report['errors']}"
    )

    ld_errors = [
        msg for msg in strict_report.get("errors", [])
        if "L/D" in msg and ("large" in msg or "500" in msg)
    ]
    assert ld_errors == [], f"L/D blowup should not be a strict error anymore: {ld_errors}"


def test_aero_strict_fails_on_beta_zero_lateral_bias_while_basic_passes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    rows = _healthy_aero_rows()

    # Broadly acceptable for basic, but strict should reject this at beta = 0.
    rows[0]["cy"] = 0.40

    _make_aero_dataset(dataset_root, rows=rows)

    basic_report = run_aero_dataset_qc(dataset_root, profile="basic")
    strict_report = run_aero_dataset_qc(dataset_root, profile="strict")

    assert basic_report["passed"] is True
    assert strict_report["passed"] is False
    assert any("beta=0 lateral sanity violation" in msg for msg in strict_report["errors"])


def test_aero_profile_routing_exposes_strict_only_validator_ids(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    _make_aero_dataset(dataset_root, rows=_healthy_aero_rows())

    basic_report = run_aero_dataset_qc(dataset_root, profile="basic")
    strict_report = run_aero_dataset_qc(dataset_root, profile="strict")

    basic_ids = {check["validator_id"] for check in basic_report["checks"]}
    strict_ids = {check["validator_id"] for check in strict_report["checks"]}

    assert "aero_ld_sanity_v1" not in basic_ids
    assert "aero_beta_zero_lateral_sanity_v1" not in basic_ids
    assert "aero_target_variation_v1" not in basic_ids

    assert "aero_ld_sanity_v1" in strict_ids
    assert "aero_beta_zero_lateral_sanity_v1" in strict_ids
    assert "aero_target_variation_v1" in strict_ids

def test_aero_strict_warns_not_fails_on_negative_ld(tmp_path: Path) -> None:
    import json
    import pandas as pd

    dataset_root = tmp_path / "aero_dataset"
    dataset_root.mkdir()

    rows = []
    for alpha in [-2.0, 0.0]:
        for control in [-5.0, 0.0, 5.0]:
            cl = 0.10 * alpha + 0.01 * control
            cd = 0.02 + 0.001 * abs(control)
            cm = -0.05 - 0.01 * control
            rows.append(
                {
                    "geometry_id": "g1",
                    "alpha_deg": alpha,
                    "beta_deg": 0.0,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": control,
                    "cl": cl,
                    "cd": cd,
                    "cm": cm,
                    "cy": 0.0,
                    "cl_roll": 0.0,
                    "cn": 0.0,
                    "l_over_d": cl / cd,
                    "geometry_declares_controls": True,
                    "airplane_has_controls": True,
                    "diag_airplane_has_control_surfaces": True,
                    "diag_airplane_avl_has_control_blocks": True,
                    "diag_keystrokes_has_d1_command": True,
                    "diag_stdout_control_variables": 1,
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(dataset_root / "aero_dataset.csv", index=False)

    manifest = {
        "dataset_type": "aero",
        "status": "success",
        "successful_aero_rows": len(df),
        "failed_aero_rows": 0,
    }
    (dataset_root / "aero_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    report = run_aero_dataset_qc(dataset_root, profile="strict")

    # This regression only checks L/D semantics:
    # non-positive L/D should be a warning, not an error.
    # Other strict validators may still fail on this intentionally tiny toy dataset.
    assert any("Non-positive L/D" in msg for msg in report["warnings"])
    assert not any("Non-positive L/D" in msg for msg in report["errors"])



def _minimal_ld_rows() -> list[dict]:
    rows = []
    for alpha, cl, cd in [(0.0, 0.0, 0.0), (4.0, 1.0, 0.0)]:
        for ctrl, cm in [(-5.0, 0.05), (0.0, 0.0), (5.0, -0.05)]:
            rows.append(
                {
                    "geometry_id": "g1",
                    "alpha_deg": alpha,
                    "beta_deg": 0.0,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": ctrl,
                    "cl": cl,
                    "cd": cd,
                    "cm": cm,
                    "cy": 0.0,
                    "cl_roll": 0.0,
                    "cn": 0.0,
                    "geometry_declares_controls": True,
                    "airplane_has_controls": True,
                    "diag_airplane_has_control_surfaces": True,
                    "diag_airplane_avl_has_control_blocks": True,
                    "diag_keystrokes_has_d1_command": True,
                    "diag_stdout_control_variables": 1,
                }
            )
    return rows


def test_ld_sanity_excludes_nonfinite_ld_at_zero_lift_only(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    _make_aero_dataset(
        dataset_root,
        rows=_minimal_ld_rows(),
        manifest_updates={
            "alpha_values": [0.0, 4.0],
            "velocity_values": [28.0],
            "altitude_values": [1500.0],
            "control_input_values": [-5.0, 0.0, 5.0],
        },
    )

    report = run_aero_dataset_qc(dataset_root, profile="strict")
    ld_check = next(c for c in report["checks"] if c["validator_id"] == "aero_ld_sanity_v1")

    assert ld_check["metrics"]["ld_sanity"]["non_finite_ld_count"] == 3
    assert any("Non-finite L/D detected in 3 rows" in msg for msg in ld_check["errors"])
    assert not any("Non-finite L/D detected in 6 rows" in msg for msg in ld_check["errors"])


def test_grid_complete_uses_manifest_sweep_lists(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    rows = []
    for alpha in [-4.0, 0.0, 4.0]:
        rows.append(
            {
                "geometry_id": "g1",
                "alpha_deg": alpha,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "control_input_deg": 0.0,
                "cl": 0.2 + 0.1 * alpha,
                "cd": 0.03,
                "cm": -0.05,
                "geometry_declares_controls": True,
                "airplane_has_controls": True,
                "diag_airplane_has_control_surfaces": True,
                "diag_airplane_avl_has_control_blocks": True,
                "diag_keystrokes_has_d1_command": True,
                "diag_stdout_control_variables": 1,
            }
        )
    _make_aero_dataset(
        dataset_root,
        rows=rows,
        manifest_updates={
            "alpha_values": [-4.0, 0.0, 4.0, 8.0],
            "beta_values": [],
            "velocity_values": [28.0],
            "altitude_values": [1500.0],
            "p_values": [],
            "q_values": [],
            "r_values": [],
            "control_input_values": [0.0],
            "diff_input_values": [],
        },
    )

    report = run_aero_dataset_qc(dataset_root, profile="basic")
    grid_check = next(c for c in report["checks"] if c["validator_id"] == "aero_grid_complete_v1")

    assert grid_check["passed"] is False
    assert grid_check["metrics"]["expected_rows_source"] == "manifest"
    assert grid_check["metrics"]["expected_rows_per_geometry"] == 4
    assert grid_check["metrics"]["manifest_sweep_effective_lengths"]["beta_values"] == 1
    assert grid_check["metrics"]["manifest_sweep_effective_lengths"]["p_values"] == 1
    assert grid_check["metrics"]["manifest_sweep_effective_lengths"]["diff_input_values"] == 1
    assert any("Incomplete per-geometry sweep grid" in msg for msg in grid_check["errors"])


def test_grid_complete_falls_back_without_manifest_sweep_lists(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    rows = []
    for alpha in [-4.0, 0.0, 4.0]:
        rows.append(
            {
                "geometry_id": "g1",
                "alpha_deg": alpha,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "control_input_deg": 0.0,
                "cl": 0.2 + 0.1 * alpha,
                "cd": 0.03,
                "cm": -0.05,
                "geometry_declares_controls": True,
                "airplane_has_controls": True,
                "diag_airplane_has_control_surfaces": True,
                "diag_airplane_avl_has_control_blocks": True,
                "diag_keystrokes_has_d1_command": True,
                "diag_stdout_control_variables": 1,
            }
        )
    _make_aero_dataset(dataset_root, rows=rows)

    report = run_aero_dataset_qc(dataset_root, profile="basic")
    grid_check = next(c for c in report["checks"] if c["validator_id"] == "aero_grid_complete_v1")

    assert grid_check["passed"] is True
    assert grid_check["metrics"]["expected_rows_source"] == "observed_unique_values"
    assert any("fell back to observed unique values" in msg for msg in grid_check["warnings"])
