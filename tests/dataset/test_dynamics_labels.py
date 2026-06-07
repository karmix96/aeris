from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.dataset.control_derivatives import compute_control_derivatives
from aeris.dataset.dynamics_labels import compute_dynamics_labels


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


def test_compute_dynamics_labels_runs_d2_d3_and_writes_batch_report(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _write_dataset(root)

    report = compute_dynamics_labels(dataset_root=root, source="raw")

    assert report["schema_version"] == "d4_dynamics_label_batch_v1"
    assert report["overall_status"] == "completed"
    assert report["stages"]["control_derivatives"]["mode"] == "computed"
    assert report["stages"]["control_derivatives"]["computed_group_count"] == 2
    assert report["stages"]["flyability_labels"]["computed_label_count"] == 2
    assert report["label_summary"]["longitudinal_basic_flyable_true_count"] == 2
    assert report["label_summary"]["red_flag_count"] == 0

    assert (root / "control_derivatives.csv").exists()
    assert (root / "control_derivatives_report.json").exists()
    assert (root / "flyability_labels.csv").exists()
    assert (root / "flyability_labels_report.json").exists()
    assert (root / "dynamics_label_run_report.json").exists()

    saved = json.loads((root / "dynamics_label_run_report.json").read_text())
    assert saved["label_summary"]["computed_label_count"] == 2


def test_compute_dynamics_labels_can_reuse_existing_control_derivatives(tmp_path: Path) -> None:
    root = tmp_path / "reuse_dataset"
    _write_dataset(root)
    compute_control_derivatives(dataset_root=root, source="raw")

    report = compute_dynamics_labels(
        dataset_root=root,
        source="raw",
        recompute_control_derivatives=False,
    )

    assert report["stages"]["control_derivatives"]["mode"] == "reused_existing"
    assert report["stages"]["flyability_labels"]["computed_label_count"] == 2


def test_compute_dynamics_labels_requires_existing_derivatives_when_reuse_requested(tmp_path: Path) -> None:
    root = tmp_path / "missing_reuse"
    _write_dataset(root)

    try:
        compute_dynamics_labels(
            dataset_root=root,
            source="raw",
            recompute_control_derivatives=False,
        )
    except FileNotFoundError as exc:
        assert "control derivatives CSV" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError when reusing missing control derivatives")


def test_compute_dynamics_labels_reports_red_flags(tmp_path: Path) -> None:
    root = tmp_path / "red_flag_dataset"
    _write_dataset(root, cm0=-1.0, cm_slope_per_deg=-0.001)

    report = compute_dynamics_labels(dataset_root=root, source="raw")

    assert report["label_summary"]["computed_label_count"] == 2
    assert report["label_summary"]["longitudinal_basic_flyable_false_count"] == 2
    assert report["label_summary"]["red_flag_count"] == 2
