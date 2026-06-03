from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.dataset.inspect import inspect_dataset
from aeris.dataset.metadata import failure_fieldnames, metadata_fieldnames


def _write_dataset_manifest(root: Path, **overrides) -> None:
    manifest = {
        "status": "partial_success",
        "requested_n": 3,
        "attempted_n": 3,
        "succeeded_n": 2,
        "failed_n": 1,
        "sampler_id": "lhs_v1",
        "sampler_seed": 42,
    }
    manifest.update(overrides)
    (root / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def _make_metadata_row(geometry_root: Path, geometry_id: str) -> dict:
    geom_dir = geometry_root / geometry_id
    geom_dir.mkdir(parents=True, exist_ok=True)

    summary_path = geom_dir / "summary.json"
    control_points_path = geom_dir / "control_points.csv"
    planform_sections_path = geom_dir / "planform_sections.csv"
    section_3d_path = geom_dir / "section_3d.csv"

    for p in [summary_path, control_points_path, planform_sections_path, section_3d_path]:
        p.write_text("x", encoding="utf-8")

    row = {k: None for k in metadata_fieldnames()}
    row.update(
        {
            "geometry_id": geometry_id,
            "case_index": 1,
            "dataset_name": "ds1",
            "status": "success",
            "sampler_id": "lhs_v1",
            "sampler_seed": 42,
            "realization_seed": None,
            "realization_mode": "deterministic_from_sample",
            "generator_family": "bwb_segmented",
            "generator_version": "v1",
            "generator_id": "bwb_segmented_v1",
            "config_name": "baseline_cfg",
            "airfoil_name": "naca0012",
            "c1_m": 1.0,
            "c2_ratio": 0.5,
            "c3_ratio": 0.4,
            "c4_ratio": 0.2,
            "b_total_m": 3.0,
            "b3_ratio": 0.6,
            "split_ratio": 0.35,
            "sw1_deg": 10.0,
            "sw2_deg": 5.0,
            "sw3_deg": 2.0,
            "twist_b0_deg": 1.0,
            "twist_b1_deg": 0.5,
            "twist_b2_deg": 0.0,
            "twist_b3_deg": -1.0,
            "dihedral_b1_deg": 3.0,
            "dihedral_b2_deg": 2.0,
            "dihedral_b3_deg": 1.0,
            "semi_span_m": 1.5,
            "full_span_m": 3.0,
            "approx_area_m2": 1.2,
            "approx_aspect_ratio_planform": 7.5,
            "aspect_ratio_aerosandbox": 7.6,
            "num_sections": 4,
            "n_xsecs_aerosandbox": 4,
            "twist_min_deg": -1.0,
            "twist_max_deg": 1.0,
            "twist_mean_deg": 0.125,
            "dihedral_min_deg": 1.0,
            "dihedral_max_deg": 3.0,
            "dihedral_mean_deg": 2.0,
            "geometry_dir": str(geom_dir),
            "summary_path": str(summary_path),
            "control_points_path": str(control_points_path),
            "planform_sections_path": str(planform_sections_path),
            "section_3d_path": str(section_3d_path),
            "plot_path": None,
        }
    )
    return row


def _make_failure_row() -> dict:
    row = {k: None for k in failure_fieldnames()}
    row.update(
        {
            "geometry_id": "geom_00003",
            "case_index": 3,
            "dataset_name": "ds1",
            "sampler_id": "lhs_v1",
            "sampler_seed": 42,
            "realization_seed": None,
            "realization_mode": "deterministic_from_sample",
            "generator_family": "bwb_segmented",
            "generator_version": "v1",
            "generator_id": "bwb_segmented_v1",
            "error_type": "RuntimeError",
            "error_message": "boom",
        }
    )
    return row


def test_inspect_dataset_happy_path(tmp_path: Path) -> None:
    root = tmp_path / "ds1"
    root.mkdir()
    (root / "geometry").mkdir()

    _write_dataset_manifest(root)

    metadata = pd.DataFrame(
        [
            _make_metadata_row(root / "geometry", "geom_00001"),
            _make_metadata_row(root / "geometry", "geom_00002"),
        ]
    )
    metadata.to_csv(root / "metadata.csv", index=False)

    failures = pd.DataFrame([_make_failure_row()])
    failures.to_csv(root / "failures.csv", index=False)

    summary = inspect_dataset(root)

    assert summary["metadata_rows"] == 2
    assert summary["failure_rows"] == 1
    assert summary["geometry_dir_count"] == 2
    assert summary["missing_columns"] == []
    assert summary["missing_failure_columns"] == []
    assert summary["missing_file_count"] == 0
    assert summary["all_count_checks_pass"] is True


def test_inspect_dataset_detects_missing_metadata_column(tmp_path: Path) -> None:
    root = tmp_path / "ds1"
    root.mkdir()
    (root / "geometry").mkdir()
    _write_dataset_manifest(root, succeeded_n=1, failed_n=0, attempted_n=1, requested_n=1)

    row = _make_metadata_row(root / "geometry", "geom_00001")
    row.pop("summary_path")
    pd.DataFrame([row]).to_csv(root / "metadata.csv", index=False)

    summary = inspect_dataset(root)

    assert "summary_path" in summary["missing_columns"]


def test_inspect_dataset_detects_duplicate_geometry_ids(tmp_path: Path) -> None:
    root = tmp_path / "ds1"
    root.mkdir()
    (root / "geometry").mkdir()
    _write_dataset_manifest(root, succeeded_n=2, failed_n=0, attempted_n=2, requested_n=2)

    row1 = _make_metadata_row(root / "geometry", "geom_00001")
    row2 = _make_metadata_row(root / "geometry", "geom_00001")
    pd.DataFrame([row1, row2]).to_csv(root / "metadata.csv", index=False)

    summary = inspect_dataset(root)

    assert summary["duplicate_geometry_ids"] == ["geom_00001"]


def test_inspect_dataset_detects_missing_artifact_files(tmp_path: Path) -> None:
    root = tmp_path / "ds1"
    root.mkdir()
    (root / "geometry").mkdir()
    _write_dataset_manifest(root, succeeded_n=1, failed_n=0, attempted_n=1, requested_n=1)

    row = _make_metadata_row(root / "geometry", "geom_00001")
    Path(row["summary_path"]).unlink()
    pd.DataFrame([row]).to_csv(root / "metadata.csv", index=False)

    summary = inspect_dataset(root)

    assert summary["missing_file_count"] == 1
    assert summary["missing_files_preview"][0]["kind"] == "summary_path"


def test_inspect_dataset_detects_manifest_count_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "ds1"
    root.mkdir()
    (root / "geometry").mkdir()
    _write_dataset_manifest(root, requested_n=5, attempted_n=5, succeeded_n=5, failed_n=0)

    metadata = pd.DataFrame([_make_metadata_row(root / "geometry", "geom_00001")])
    metadata.to_csv(root / "metadata.csv", index=False)

    failures = pd.DataFrame([], columns=failure_fieldnames())
    failures.to_csv(root / "failures.csv", index=False)

    summary = inspect_dataset(root)

    assert summary["all_count_checks_pass"] is False
    assert summary["count_consistency"]["manifest_succeeded_matches_metadata_rows"] is False


def test_inspect_dataset_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Dataset root does not exist"):
        inspect_dataset(tmp_path / "missing_ds")

def _write_aero_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "status": "success",
        "dataset_name": "aero_ds1",
        "config_path": "configs/geometry/baseline_bwb_25.yaml",
        "requested_geometry_n": 2,
        "attempted_geometry_sweeps": 2,
        "completed_geometry_sweeps": 2,
        "successful_aero_rows": 4,
        "failed_aero_rows": 1,
        "generator_id": "bwb_segmented_v1",
        "solver": "aerosandbox_avl",
        "geometry_qc": {"passed": True},
        "aero_qc": {"passed": True, "profile": "basic"},
    }
    (root / "aero_dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    final_summary = {
        "dataset_name": "aero_ds1",
        "final_status": "success",
        "successful_aero_rows": 4,
        "failed_aero_rows": 1,
        "qc_preset": "production",
        "generator_id": "bwb_segmented_v1",
        "solver": "aerosandbox_avl",
    }
    (root / "final_run_summary.json").write_text(json.dumps(final_summary), encoding="utf-8")

    aero_rows = pd.DataFrame(
        [
            {"geometry_id": "geom_00001", "alpha_deg": -2, "velocity_mps": 28, "altitude_m": 1500, "control_input_deg": -5, "cl": 0.1, "cd": 0.02, "cm": -0.1},
            {"geometry_id": "geom_00001", "alpha_deg": 0, "velocity_mps": 28, "altitude_m": 1500, "control_input_deg": 0, "cl": 0.2, "cd": 0.03, "cm": -0.2},
            {"geometry_id": "geom_00002", "alpha_deg": -2, "velocity_mps": 28, "altitude_m": 1500, "control_input_deg": -5, "cl": 0.3, "cd": 0.04, "cm": -0.3},
            {"geometry_id": "geom_00002", "alpha_deg": 0, "velocity_mps": 28, "altitude_m": 1500, "control_input_deg": 0, "cl": 0.4, "cd": 0.05, "cm": -0.4},
        ]
    )
    aero_rows.to_csv(root / "aero_dataset.csv", index=False)

    pd.DataFrame(
        [
            {"geometry_id": "geom_00002", "alpha_deg": 4, "failure_reason": "solver_failed"},
        ]
    ).to_csv(root / "aero_failures.csv", index=False)

    aero_rows.to_csv(root / "curated_aero_dataset.csv", index=False)
    pd.DataFrame([], columns=list(aero_rows.columns) + ["rejection_reason"]).to_csv(
        root / "rejected_aero_rows.csv", index=False
    )

    curation_report = {
        "kept_rows": 4,
        "rejected_rows": 0,
        "kept_geometries": 2,
        "rejected_geometries": 0,
        "qc_preset_used": "production",
        "geometry_qc_passed": True,
        "aero_qc_passed": True,
        "promotion_ready": True,
        "promotion_blockers": [],
        "rejection_reason_counts": {},
    }
    (root / "curation_report.json").write_text(json.dumps(curation_report), encoding="utf-8")

    promotion_manifest = {
        "promotion_forced": False,
        "promotion_ready_at_time_of_promotion": True,
        "promotion_blockers": [],
        "qc_context": {
            "qc_preset_used": "production",
            "geometry_qc_passed": True,
            "aero_qc_passed": True,
        },
        "curation_context": {
            "kept_rows": 4,
            "rejected_rows": 0,
            "kept_geometries": 2,
            "rejected_geometries": 0,
        },
    }
    (root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest), encoding="utf-8")


def test_inspect_dataset_detects_and_summarizes_aero_dataset(tmp_path: Path) -> None:
    root = tmp_path / "aero_ds1"
    _write_aero_dataset(root)

    summary = inspect_dataset(root)

    assert summary["dataset_type"] == "aero"
    assert summary["aero_dataset_rows"] == 4
    assert summary["aero_failure_rows"] == 1
    assert summary["curated_rows"] == 4
    assert summary["rejected_rows"] == 0
    assert summary["unique_geometry_count"] == 2
    assert summary["manifest_status"] == "success"
    assert summary["final_status"] == "success"
    assert summary["all_count_checks_pass"] is True
    assert summary["count_consistency"]["manifest_successful_matches_aero_rows"] is True
    assert summary["count_consistency"]["curation_kept_matches_curated_rows"] is True
    assert summary["qc"]["qc_preset"] == "production"
    assert summary["curation"]["promotion_ready"] is True
    assert summary["promotion"]["exists"] is True
    assert summary["promotion"]["promotion_forced"] is False
    assert summary["flight_condition_unique_counts"]["alpha_deg"] == 2
    assert summary["target_metrics"]["cl"]["mean"] == pytest.approx(0.25)


def test_inspect_dataset_prefers_aero_manifest_when_geometry_manifest_is_also_present(tmp_path: Path) -> None:
    root = tmp_path / "mixed_ds"
    _write_aero_dataset(root)
    _write_dataset_manifest(root)

    summary = inspect_dataset(root)

    assert summary["dataset_type"] == "aero"
    assert summary["aero_dataset_rows"] == 4


def test_inspect_dataset_unrecognized_root_raises(tmp_path: Path) -> None:
    root = tmp_path / "empty_ds"
    root.mkdir()

    with pytest.raises(FileNotFoundError, match="not recognized as an AERIS geometry or aero dataset"):
        inspect_dataset(root)
