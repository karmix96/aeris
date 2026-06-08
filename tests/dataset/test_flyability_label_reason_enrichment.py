from __future__ import annotations

from pathlib import Path

import pandas as pd

from aeris.dataset.control_derivatives import compute_control_derivatives
from aeris.dataset.flyability_labels import compute_flyability_labels


def _write_trim_failure_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for delta in [-5.0, 0.0, 5.0]:
        rows.append(
            {
                "geometry_id": "geom_00001",
                "alpha_deg": 0.0,
                "beta_deg": 0.0,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "p_rad_s": 0.0,
                "q_rad_s": 0.0,
                "r_rad_s": 0.0,
                "delta_e_sym_deg": delta,
                "control_input_deg": delta,
                "cm": -0.30 - 0.003 * delta,
                "cl": 0.40 + 0.001 * delta,
                "cd": 0.02 + 0.0001 * abs(delta),
            }
        )
    pd.DataFrame(rows).to_csv(root / "aero_dataset.csv", index=False)


def test_flyability_labels_include_explicit_failure_reasons(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    _write_trim_failure_dataset(root)
    compute_control_derivatives(dataset_root=root, source="raw")

    report = compute_flyability_labels(
        dataset_root=root,
        source="raw",
        max_abs_trim_delta_e_deg=25.0,
    )

    df = pd.read_csv(root / "flyability_labels.csv")
    row = df.iloc[0]

    assert report["red_flag_count"] == 1
    assert report["red_flag_reason_counts"]["trim_delta_e_required_exceeds_limit"] == 1
    assert row["red_flag"] in (True, "True", 1)
    assert row["trim_failure_reason"] == "trim_delta_e_required_exceeds_limit"
    assert "trim_delta_e_required_exceeds_limit" in row["red_flag_reasons"]
    assert row["label_failure_stage"] == "trim"
    assert "trim_delta_e_limit_deg" in df.columns


def test_flyability_labels_report_stage_counts(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    _write_trim_failure_dataset(root)
    compute_control_derivatives(dataset_root=root, source="raw")

    report = compute_flyability_labels(dataset_root=root, source="raw")

    assert report["label_failure_stage_counts"]["trim"] == 1
    assert report["trim_failure_reason_counts"]["trim_delta_e_required_exceeds_limit"] == 1
