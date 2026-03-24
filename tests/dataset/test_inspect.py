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