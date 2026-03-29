from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.quality.pipeline_api import run_geometry_dataset_qc


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

    df = pd.DataFrame(rows)
    df.to_csv(dataset_root / "metadata.csv", index=False)


def _healthy_geometry_row(dataset_root: Path, geometry_id: str = "geom_00001") -> dict:
    geom_root = dataset_root / "geometry" / geometry_id
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
        "approx_aspect_ratio_planform": (3.20 ** 2) / 1.70,
        "aspect_ratio_aerosandbox": (3.20 ** 2) / 1.70 + 0.10,
        "summary_path": _touch(geom_root / "geometry_summary.json"),
        "control_points_path": _touch(geom_root / "control_points.csv"),
        "planform_sections_path": _touch(geom_root / "planform_sections.csv"),
        "section_3d_path": _touch(geom_root / "section_3d.csv"),
    }


def test_geometry_basic_profile_passes_for_healthy_dataset(tmp_path: Path) -> None:
    dataset_root = tmp_path / "geom_dataset"
    rows = [_healthy_geometry_row(dataset_root)]
    _make_geometry_dataset(dataset_root, rows=rows)

    report = run_geometry_dataset_qc(dataset_root, profile="basic")

    assert report["passed"] is True
    assert report["errors"] == []
    assert report["metrics"]["profile"] == "basic"


def test_geometry_strict_fails_on_ar_consistency_while_basic_passes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "geom_dataset"
    row = _healthy_geometry_row(dataset_root)
    row["approx_aspect_ratio_planform"] = 99.0  # basic does not check this; strict should
    _make_geometry_dataset(dataset_root, rows=[row])

    basic_report = run_geometry_dataset_qc(dataset_root, profile="basic")
    strict_report = run_geometry_dataset_qc(dataset_root, profile="strict")

    assert basic_report["passed"] is True
    assert strict_report["passed"] is False
    assert any("Aspect-ratio recompute mismatch" in msg for msg in strict_report["errors"])


def test_geometry_strict_fails_on_non_monotonic_taper_while_basic_passes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "geom_dataset"
    row = _healthy_geometry_row(dataset_root)
    row["c2_ratio"] = 0.50
    row["c3_ratio"] = 0.70  # non-monotonic taper
    _make_geometry_dataset(dataset_root, rows=[row])

    basic_report = run_geometry_dataset_qc(dataset_root, profile="basic")
    strict_report = run_geometry_dataset_qc(dataset_root, profile="strict")

    assert basic_report["passed"] is True
    assert strict_report["passed"] is False
    assert any("non_monotonic_taper" in msg for msg in strict_report["errors"])


def test_geometry_profile_routing_exposes_strict_only_validator_ids(tmp_path: Path) -> None:
    dataset_root = tmp_path / "geom_dataset"
    rows = [_healthy_geometry_row(dataset_root)]
    _make_geometry_dataset(dataset_root, rows=rows)

    basic_report = run_geometry_dataset_qc(dataset_root, profile="basic")
    strict_report = run_geometry_dataset_qc(dataset_root, profile="strict")

    basic_ids = {check["validator_id"] for check in basic_report["checks"]}
    strict_ids = {check["validator_id"] for check in strict_report["checks"]}

    assert "geometry_scalar_consistency_v1" not in basic_ids
    assert "geometry_chord_ratio_sanity_v1" not in basic_ids
    assert "geometry_planform_parameter_sanity_v1" not in basic_ids

    assert "geometry_scalar_consistency_v1" in strict_ids
    assert "geometry_chord_ratio_sanity_v1" in strict_ids
    assert "geometry_planform_parameter_sanity_v1" in strict_ids