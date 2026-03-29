from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.quality.pipeline_api import (
    run_aero_dataset_qc,
    run_geometry_dataset_qc,
)


def _touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return str(path)


def _make_geometry_dataset(dataset_root: Path, *, rows: list[dict], succeeded_n: int | None = None) -> None:
    dataset_root.mkdir(parents=True, exist_ok=True)

    (dataset_root / "configs").mkdir(exist_ok=True)
    (dataset_root / "configs" / "input_config.yaml").write_text("name: test\n", encoding="utf-8")

    manifest = {
        "status": "success",
        "requested_n": len(rows),
        "attempted_n": len(rows),
        "succeeded_n": len(rows) if succeeded_n is None else succeeded_n,
        "failed_n": 0,
    }
    (dataset_root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(dataset_root / "metadata.csv", index=False)


def _healthy_geometry_row(dataset_root: Path, geometry_id: str = "geom_00001") -> dict:
    geom_root = dataset_root / "geometry" / geometry_id
    ar = (3.2 ** 2) / 1.7
    return {
        "geometry_id": geometry_id,
        "c1_m": 1.60,
        "c2_ratio": 0.60,
        "c3_ratio": 0.45,
        "c4_ratio": 0.20,
        "b_total_m": 1.60,
        "b3_ratio": 0.50,
        "split_ratio": 0.45,
        "sw1_deg": 40.0,
        "sw2_deg": 25.0,
        "sw3_deg": 10.0,
        "semi_span_m": 1.60,
        "full_span_m": 3.20,
        "approx_area_m2": 1.70,
        "approx_aspect_ratio_planform": ar,
        "aspect_ratio_aerosandbox": ar + 0.05,
        "summary_path": _touch(geom_root / "geometry_summary.json"),
        "control_points_path": _touch(geom_root / "control_points.csv"),
        "planform_sections_path": _touch(geom_root / "planform_sections.csv"),
        "section_3d_path": _touch(geom_root / "section_3d.csv"),
    }


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
                    "cd": 0.03 + 0.002 * (alpha_deg / 2.0),
                    "cm": cm,
                    "cy": 0.0,
                    "cl_roll": 0.0,
                    "cn": 0.0,
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


def test_pipeline_api_geometry_returns_legacy_payload_with_checks(tmp_path: Path) -> None:
    dataset_root = tmp_path / "geom_dataset"
    _make_geometry_dataset(dataset_root, rows=[_healthy_geometry_row(dataset_root)])

    report = run_geometry_dataset_qc(dataset_root, profile="strict")

    assert isinstance(report, dict)
    assert "passed" in report
    assert "errors" in report
    assert "warnings" in report
    assert "metrics" in report
    assert "checks" in report

    assert report["metrics"]["profile"] == "strict"
    assert isinstance(report["checks"], list)
    assert len(report["checks"]) > 0
    assert all("validator_id" in check for check in report["checks"])


def test_pipeline_api_aero_returns_legacy_payload_with_checks(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    _make_aero_dataset(dataset_root, rows=_healthy_aero_rows())

    report = run_aero_dataset_qc(dataset_root, profile="strict")

    assert isinstance(report, dict)
    assert "passed" in report
    assert "errors" in report
    assert "warnings" in report
    assert "metrics" in report
    assert "checks" in report

    assert report["metrics"]["profile"] == "strict"
    assert isinstance(report["checks"], list)
    assert len(report["checks"]) > 0
    assert all("validator_id" in check for check in report["checks"])