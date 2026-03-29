from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.quality.pipeline_api import run_geometry_dataset_qc


def _touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return str(path)


def _make_geometry_dataset(dataset_root: Path, *, rows: list[dict]) -> None:
    dataset_root.mkdir(parents=True, exist_ok=True)

    (dataset_root / "configs").mkdir(exist_ok=True)
    (dataset_root / "configs" / "input_config.yaml").write_text("name: absurd_sweep_fixture\n", encoding="utf-8")

    manifest = {
        "status": "success",
        "requested_n": len(rows),
        "attempted_n": len(rows),
        "succeeded_n": len(rows),
        "failed_n": 0,
    }
    (dataset_root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    pd.DataFrame(rows).to_csv(dataset_root / "metadata.csv", index=False)


def _healthy_row(dataset_root: Path, geometry_id: str = "geom_00001") -> dict:
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
        "sw1_deg": -40.0,
        "sw2_deg": -25.0,
        "sw3_deg": -10.0,
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


@pytest.mark.integration
def test_promotion_strict_rejects_absurd_signed_sweep(tmp_path: Path) -> None:
    dataset_root = tmp_path / "absurd_sweep_dataset"

    row = _healthy_row(dataset_root)
    row["sw2_deg"] = -120.0  # signed but absurd

    _make_geometry_dataset(dataset_root, rows=[row])

    basic_report = run_geometry_dataset_qc(dataset_root, profile="basic")
    strict_report = run_geometry_dataset_qc(dataset_root, profile="strict")

    assert basic_report["passed"] is True
    assert strict_report["passed"] is False
    assert any("sweep_out_of_bounds" in msg for msg in strict_report["errors"])

    strict_validator_ids = {check["validator_id"] for check in strict_report["checks"]}
    assert "geometry_planform_parameter_sanity_v1" in strict_validator_ids