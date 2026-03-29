from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.dataset.curate_aero import curate_aero_dataset


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _healthy_rows() -> list[dict]:
    rows: list[dict] = []
    for geometry_id in ["geom_00001", "geom_00002"]:
        for alpha_deg in [0.0, 2.0]:
            for control_input_deg in [-5.0, 0.0, 5.0]:
                rows.append(
                    {
                        "geometry_id": geometry_id,
                        "alpha_deg": alpha_deg,
                        "beta_deg": 0.0,
                        "velocity_mps": 28.0,
                        "altitude_m": 1500.0,
                        "p_rad_s": 0.0,
                        "q_rad_s": 0.0,
                        "r_rad_s": 0.0,
                        "control_input_deg": control_input_deg,
                        "cl": 0.4 + 0.01 * control_input_deg + 0.05 * alpha_deg,
                        "cd": 0.03,
                        "cm": -0.01 * control_input_deg,
                        "diag_airplane_has_control_surfaces": True,
                        "diag_airplane_avl_has_control_blocks": True,
                        "diag_keystrokes_has_d1_command": True,
                    }
                )
    return rows


def _write_manifest(dataset_root: Path) -> None:
    manifest = {
        "alpha_values": [0.0, 2.0],
        "beta_values": [0.0],
        "velocity_values": [28.0],
        "altitude_values": [1500.0],
        "p_values": [0.0],
        "q_values": [0.0],
        "r_values": [0.0],
        "control_input_values": [-5.0, 0.0, 5.0],
    }
    (dataset_root / "aero_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def test_curate_aero_marks_promotion_ready_when_qc_passed_and_no_rejections(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_ok"
    dataset_root.mkdir(parents=True, exist_ok=True)

    _write_manifest(dataset_root)
    _write_csv(dataset_root / "aero_dataset.csv", _healthy_rows())

    (dataset_root / "aero_failures.csv").write_text("", encoding="utf-8")
    (dataset_root / "final_run_summary.json").write_text(
        json.dumps(
            {
                "qc_preset": "promotion_strict",
                "geometry_qc": {"passed": True},
                "aero_qc": {"passed": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = curate_aero_dataset(dataset_root=dataset_root)

    assert report["promotion_ready"] is True
    assert report["promotion_blockers"] == []
    assert report["geometry_qc_passed"] is True
    assert report["aero_qc_passed"] is True
    assert report["qc_preset_used"] == "promotion_strict"

    curated = pd.read_csv(dataset_root / "curated_aero_dataset.csv")
    assert "promotion_ready" in curated.columns
    assert bool(curated["promotion_ready"].all()) is True


def test_curate_aero_blocks_promotion_when_qc_failed(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_qc_failed"
    dataset_root.mkdir(parents=True, exist_ok=True)

    _write_manifest(dataset_root)
    _write_csv(dataset_root / "aero_dataset.csv", _healthy_rows())
    (dataset_root / "aero_failures.csv").write_text("", encoding="utf-8")

    (dataset_root / "final_run_summary.json").write_text(
        json.dumps(
            {
                "qc_preset": "promotion_strict",
                "geometry_qc": {"passed": False},
                "aero_qc": {"passed": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = curate_aero_dataset(dataset_root=dataset_root)

    assert report["promotion_ready"] is False
    assert "geometry_qc_failed" in report["promotion_blockers"]


def test_curate_aero_blocks_promotion_when_rows_rejected(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_rejected_rows"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = _healthy_rows()
    rows = rows[:-1]  # break one geometry group completeness

    _write_manifest(dataset_root)
    _write_csv(dataset_root / "aero_dataset.csv", rows)
    (dataset_root / "aero_failures.csv").write_text("", encoding="utf-8")

    (dataset_root / "final_run_summary.json").write_text(
        json.dumps(
            {
                "qc_preset": "promotion_strict",
                "geometry_qc": {"passed": True},
                "aero_qc": {"passed": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = curate_aero_dataset(dataset_root=dataset_root)

    assert report["promotion_ready"] is False
    assert "curation_rejected_geometries" in report["promotion_blockers"]

    rejected = pd.read_csv(dataset_root / "rejected_aero_rows.csv")
    assert "rejection_reason" in rejected.columns