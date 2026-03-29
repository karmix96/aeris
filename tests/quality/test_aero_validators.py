from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.quality.pipeline_api import run_aero_dataset_qc


def _make_aero_dataset(dataset_root: Path, *, rows: list[dict], successful_aero_rows: int | None = None) -> None:
    dataset_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "status": "success",
        "successful_aero_rows": len(rows) if successful_aero_rows is None else successful_aero_rows,
    }
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


def test_aero_strict_fails_on_ld_sanity_while_basic_passes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    rows = _healthy_aero_rows()

    # Keep CD positive, so basic passes. But make L/D absurd so strict fails.
    rows[0]["cl"] = 4.0
    rows[0]["cd"] = 0.001

    _make_aero_dataset(dataset_root, rows=rows)

    basic_report = run_aero_dataset_qc(dataset_root, profile="basic")
    strict_report = run_aero_dataset_qc(dataset_root, profile="strict")

    assert basic_report["passed"] is True
    assert strict_report["passed"] is False
    assert any("large |L/D|" in msg for msg in strict_report["errors"])


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