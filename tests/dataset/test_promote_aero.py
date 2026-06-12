from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeris.dataset.promote_aero import promote_aero_dataset


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_promote_aero_succeeds_when_promotion_ready(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_ready"
    dataset_root.mkdir(parents=True, exist_ok=True)

    # FIX: PROM-1 requires the curated CSV to exist before promotion
    _curated = dataset_root / "curated_aero_dataset.csv"
    _curated.parent.mkdir(parents=True, exist_ok=True)
    _curated.write_text("geometry_id,cl,cd,cm\ngeom_00001,0.5,0.02,-0.01\n", encoding="utf-8")

    _write_json(
        dataset_root / "curation_report.json",
        {
            "promotion_ready": True,
            "promotion_blockers": [],
            "qc_preset_used": "production",
            "geometry_qc_passed": True,
            "aero_qc_passed": True,
            "kept_rows": 12,
            "rejected_rows": 0,
            "kept_geometries": 2,
            "rejected_geometries": 0,
            "rejection_reason_counts": {},
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    )

    _write_json(
        dataset_root / "final_run_summary.json",
        {
            "dataset_name": "dataset_ready",
            "config_path": "configs/geometry/baseline_bwb_25.yaml",
            "generator_id": "bwb_segmented_v1",
            "solver": "aerosandbox_avl",
            "final_status": "success",
            "exit_code": 0,
        },
    )

    manifest = promote_aero_dataset(dataset_root=dataset_root)

    assert manifest["promotion_ready_at_time_of_promotion"] is True
    assert manifest["promotion_forced"] is False
    assert (dataset_root / "promotion_manifest.json").exists()


def test_promote_aero_fails_when_not_promotion_ready(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_blocked"
    dataset_root.mkdir(parents=True, exist_ok=True)

    # FIX: PROM-1 validates curated CSV exists even when not promotion-ready
    _curated2 = dataset_root / "curated_aero_dataset.csv"
    _curated2.parent.mkdir(parents=True, exist_ok=True)
    _curated2.write_text("geometry_id,cl,cd,cm\ngeom_00001,0.5,0.02,-0.01\n", encoding="utf-8")

    _write_json(
        dataset_root / "curation_report.json",
        {
            "promotion_ready": False,
            "promotion_blockers": ["geometry_qc_failed", "curation_rejected_geometries"],
            "qc_preset_used": "promotion_strict",
            "geometry_qc_passed": False,
            "aero_qc_passed": True,
            "kept_rows": 10,
            "rejected_rows": 2,
            "kept_geometries": 1,
            "rejected_geometries": 1,
            "rejection_reason_counts": {"incomplete_sweep_group": 1},
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    )

    _write_json(
        dataset_root / "final_run_summary.json",
        {
            "dataset_name": "dataset_blocked",
            "config_path": "configs/geometry/baseline_bwb_25.yaml",
            "generator_id": "bwb_segmented_v1",
            "solver": "aerosandbox_avl",
            "final_status": "failed",
            "exit_code": 1,
        },
    )

    with pytest.raises(ValueError) as exc:
        promote_aero_dataset(dataset_root=dataset_root)

    assert "not promotion-ready" in str(exc.value)


def test_promote_aero_can_be_forced(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_forced"
    dataset_root.mkdir(parents=True, exist_ok=True)

    # FIX: PROM-1 validates curated CSV exists even for forced promotion
    _curated3 = dataset_root / "curated_aero_dataset.csv"
    _curated3.parent.mkdir(parents=True, exist_ok=True)
    _curated3.write_text("geometry_id,cl,cd,cm\ngeom_00001,0.5,0.02,-0.01\n", encoding="utf-8")

    _write_json(
        dataset_root / "curation_report.json",
        {
            "promotion_ready": False,
            "promotion_blockers": ["aero_qc_failed"],
            "qc_preset_used": "promotion_strict",
            "geometry_qc_passed": True,
            "aero_qc_passed": False,
            "kept_rows": 12,
            "rejected_rows": 0,
            "kept_geometries": 2,
            "rejected_geometries": 0,
            "rejection_reason_counts": {},
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    )

    _write_json(
        dataset_root / "final_run_summary.json",
        {
            "dataset_name": "dataset_forced",
            "config_path": "configs/geometry/baseline_bwb_25.yaml",
            "generator_id": "bwb_segmented_v1",
            "solver": "aerosandbox_avl",
            "final_status": "success",
            "exit_code": 0,
        },
    )

    manifest = promote_aero_dataset(dataset_root=dataset_root, force=True)

    assert manifest["promotion_ready_at_time_of_promotion"] is False
    assert manifest["promotion_forced"] is True
    assert manifest["promotion_blockers"] == ["aero_qc_failed"]