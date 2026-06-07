from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from aeris.dataset.control_derivatives import compute_control_derivatives


def _write_dataset(root: Path, rows: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(root / "aero_dataset.csv", index=False)
    (root / "aero_dataset_manifest.json").write_text(
        json.dumps({"control_input_values": [-5.0, 0.0, 5.0]}, indent=2),
        encoding="utf-8",
    )


def _rows(*, include_alias: bool = True) -> list[dict]:
    rows: list[dict] = []
    for alpha in [0.0, 4.0]:
        for delta in [-5.0, 0.0, 5.0]:
            row = {
                "geometry_id": "geom_00001",
                "alpha_deg": alpha,
                "beta_deg": 0.0,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "p_rad_s": 0.0,
                "q_rad_s": 0.0,
                "r_rad_s": 0.0,
                "control_input_deg": delta,
                "delta_a_diff_deg": 0.0,
                "cl": 0.4 + 0.02 * alpha + 0.001 * delta,
                "cd": 0.02 + 0.0001 * delta * delta,
                "cm": -0.05 + 0.002 * delta,
                "cy": 0.0,
                "cl_roll": 0.0,
                "cn": 0.0,
            }
            if include_alias:
                row["delta_e_sym_deg"] = delta
            rows.append(row)
    return rows


def test_compute_control_derivatives_writes_csv_and_report(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _write_dataset(root, _rows(include_alias=True))

    report = compute_control_derivatives(dataset_root=root, source="raw")

    assert report["source"] == "raw"
    assert report["control_column"] == "delta_e_sym_deg"
    assert report["used_legacy_control_alias"] is False
    assert report["group_count"] == 2
    assert report["computed_group_count"] == 2
    assert report["skipped_group_count"] == 0
    assert Path(report["output_csv"]).exists()
    assert Path(report["output_report"]).exists()

    out = pd.read_csv(root / "control_derivatives.csv")
    assert len(out) == 2
    assert set(out["status"]) == {"computed"}
    assert math.isclose(out["CL_delta_e_per_rad"].iloc[0], 0.001 / math.radians(1.0), rel_tol=1e-9)
    assert math.isclose(out["Cm_delta_e_per_rad"].iloc[0], 0.002 / math.radians(1.0), rel_tol=1e-9)
    assert bool(out["pitch_authority_adequate"].iloc[0]) is True


def test_compute_control_derivatives_uses_legacy_control_alias(tmp_path: Path) -> None:
    root = tmp_path / "legacy_aero_dataset"
    _write_dataset(root, _rows(include_alias=False))

    report = compute_control_derivatives(dataset_root=root, source="raw")

    assert report["control_column"] == "control_input_deg"
    assert report["used_legacy_control_alias"] is True
    out = pd.read_csv(root / "control_derivatives.csv")
    assert set(out["status"]) == {"computed"}


def test_compute_control_derivatives_prefers_curated_when_auto(tmp_path: Path) -> None:
    root = tmp_path / "curated_aero_dataset"
    _write_dataset(root, _rows(include_alias=True))
    pd.DataFrame(_rows(include_alias=True)).to_csv(root / "curated_aero_dataset.csv", index=False)

    report = compute_control_derivatives(dataset_root=root, source="auto")

    assert report["source"] == "curated"
    assert "curated_aero_dataset.csv" in report["source_csv"]


def test_compute_control_derivatives_skips_missing_symmetric_pair(tmp_path: Path) -> None:
    root = tmp_path / "bad_aero_dataset"
    rows = [row for row in _rows(include_alias=True) if row["delta_e_sym_deg"] >= 0.0]
    _write_dataset(root, rows)

    report = compute_control_derivatives(dataset_root=root, source="raw")

    assert report["computed_group_count"] == 0
    assert report["skipped_group_count"] == 2
    out = pd.read_csv(root / "control_derivatives.csv")
    assert set(out["status"]) == {"skipped"}
    assert set(out["skip_reason"]) == {"missing_symmetric_positive_negative_control_pair"}


def test_compute_control_derivatives_reports_differential_reserved(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _write_dataset(root, _rows(include_alias=True))

    report = compute_control_derivatives(dataset_root=root, source="raw")

    diff = report["differential_elevon"]
    assert diff["column_present"] is True
    assert diff["unique_values"] == [0.0]
    assert diff["varies"] is False
    assert diff["status"] == "not_computed_reserved_for_future_solver_wiring"
