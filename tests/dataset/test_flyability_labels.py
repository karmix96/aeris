from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from aeris.dataset.control_derivatives import compute_control_derivatives
from aeris.dataset.flyability_labels import compute_flyability_labels


def _write_dataset(root: Path, *, include_alias: bool = True, cm0: float = -0.05, cm_slope_per_deg: float = -0.003) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for alpha in [0.0, 2.0]:
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
                "cd": 0.02,
                "cm": cm0 + cm_slope_per_deg * delta,
            }
            if include_alias:
                row["delta_e_sym_deg"] = delta
            rows.append(row)
    pd.DataFrame(rows).to_csv(root / "aero_dataset.csv", index=False)
    (root / "aero_dataset_manifest.json").write_text(json.dumps({}), encoding="utf-8")


def test_compute_flyability_labels_writes_csv_and_report(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _write_dataset(root)
    compute_control_derivatives(dataset_root=root, source="raw")

    report = compute_flyability_labels(dataset_root=root, source="raw")

    assert report["source"] == "raw"
    assert report["control_column"] == "delta_e_sym_deg"
    assert report["label_row_count"] == 2
    assert report["computed_label_count"] == 2
    assert report["skipped_label_count"] == 0
    assert Path(report["output_csv"]).exists()
    assert Path(report["output_report"]).exists()

    out = pd.read_csv(root / "flyability_labels.csv")
    assert len(out) == 2
    assert set(out["status"]) == {"computed"}
    assert bool(out["pitch_authority_adequate"].iloc[0]) is True
    assert bool(out["pitch_control_sign_ok"].iloc[0]) is True
    assert bool(out["trim_delta_e_feasible"].iloc[0]) is True
    assert bool(out["label_longitudinal_basic_flyable"].iloc[0]) is True

    expected_cmde = cmde = -0.003 / math.radians(1.0)
    expected_trim = math.degrees(-(-0.05) / cmde)
    assert math.isclose(out["Cm_delta_e_per_rad"].iloc[0], expected_cmde, rel_tol=1e-9)
    assert math.isclose(out["trim_delta_e_required_deg"].iloc[0], expected_trim, rel_tol=1e-9)


def test_compute_flyability_labels_uses_legacy_control_alias(tmp_path: Path) -> None:
    root = tmp_path / "legacy_dataset"
    _write_dataset(root, include_alias=False)
    compute_control_derivatives(dataset_root=root, source="raw")

    report = compute_flyability_labels(dataset_root=root, source="raw")

    assert report["control_column"] == "control_input_deg"
    assert report["used_legacy_control_alias"] is True
    out = pd.read_csv(root / "flyability_labels.csv")
    assert set(out["status"]) == {"computed"}


def test_compute_flyability_labels_flags_insufficient_trim_authority(tmp_path: Path) -> None:
    root = tmp_path / "insufficient_trim"
    _write_dataset(root, cm0=-1.0, cm_slope_per_deg=-0.001)
    compute_control_derivatives(dataset_root=root, source="raw")

    report = compute_flyability_labels(dataset_root=root, source="raw", max_abs_trim_delta_e_deg=25.0)

    assert report["computed_label_count"] == 2
    out = pd.read_csv(root / "flyability_labels.csv")
    assert bool(out["trim_delta_e_feasible"].iloc[0]) is False
    assert bool(out["label_longitudinal_basic_flyable"].iloc[0]) is False


def test_compute_flyability_labels_requires_control_derivatives_first(tmp_path: Path) -> None:
    root = tmp_path / "missing_derivatives"
    _write_dataset(root)

    try:
        compute_flyability_labels(dataset_root=root, source="raw")
    except FileNotFoundError as exc:
        assert "compute-control-derivatives" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError when control_derivatives.csv is missing")
