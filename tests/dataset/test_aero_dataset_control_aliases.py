from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.dataset.aero_dataset_run import (
    _flatten_failure_row,
    _flatten_success_row,
    _unique_float_values,
)
from aeris.dataset.curate_aero import curate_aero_dataset


def test_flatten_success_row_adds_explicit_control_aliases() -> None:
    row = _flatten_success_row(
        geometry_row={"geometry_id": "geom_00001", "c1_m": "1.6"},
        sweep_case={
            "case_label": "case_ctrl_m5",
            "case_index": 0,
            "control_input_deg": -5.0,
            "flight_condition": {
                "alpha_deg": 0.0,
                "beta_deg": 0.0,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "p_rad_s": 0.0,
                "q_rad_s": 0.0,
                "r_rad_s": 0.0,
            },
        },
        aero_payload={
            "status": "success",
            "runtime_sec": 0.1,
            "scalars": {"cl": 0.4, "cd": 0.03, "cm": -0.02},
            "solver_metadata": {},
        },
    )

    assert row["control_input_deg"] == -5.0
    assert row["delta_e_sym_deg"] == -5.0
    assert row["delta_a_diff_deg"] == 0.0


def test_flatten_failure_row_adds_explicit_control_aliases() -> None:
    row = _flatten_failure_row(
        geometry_row={"geometry_id": "geom_00001"},
        geometry_id="geom_00001",
        sweep_case={
            "case_label": "case_ctrl_p5",
            "case_index": 1,
            "control_input_deg": 5.0,
            "flight_condition": {"alpha_deg": 0.0},
        },
        error_type="RuntimeError",
        error_message="solver failed",
    )

    assert row["control_input_deg"] == 5.0
    assert row["delta_e_sym_deg"] == 5.0
    assert row["delta_a_diff_deg"] == 0.0


def test_unique_float_values_reports_control_alias_values() -> None:
    rows = [
        {"delta_e_sym_deg": -5.0, "delta_a_diff_deg": 0.0},
        {"delta_e_sym_deg": 0.0, "delta_a_diff_deg": 0.0},
        {"delta_e_sym_deg": 5.0, "delta_a_diff_deg": 0.0},
        {"delta_e_sym_deg": 5.0, "delta_a_diff_deg": 0.0},
    ]

    assert _unique_float_values(rows, "delta_e_sym_deg") == [-5.0, 0.0, 5.0]
    assert _unique_float_values(rows, "delta_a_diff_deg") == [0.0]


def test_curate_aero_backfills_control_aliases_for_legacy_dataset(tmp_path: Path) -> None:
    dataset_root = tmp_path / "legacy_aero_dataset"
    dataset_root.mkdir(parents=True)

    pd.DataFrame(
        [
            {
                "geometry_id": "geom_00001",
                "control_input_deg": -5.0,
                "cl": 0.3,
                "cd": 0.03,
                "cm": -0.01,
            },
            {
                "geometry_id": "geom_00001",
                "control_input_deg": 5.0,
                "cl": 0.4,
                "cd": 0.04,
                "cm": -0.03,
            },
        ]
    ).to_csv(dataset_root / "aero_dataset.csv", index=False)

    pd.DataFrame(columns=["geometry_id", "error_type", "error_message"]).to_csv(
        dataset_root / "aero_failures.csv",
        index=False,
    )
    (dataset_root / "aero_dataset_manifest.json").write_text(json.dumps({}), encoding="utf-8")

    report = curate_aero_dataset(
        dataset_root=dataset_root,
        reject_incomplete_groups=False,
        reject_groups_with_failures=False,
        reject_control_diagnostic_failures=False,
    )

    curated = pd.read_csv(dataset_root / "curated_aero_dataset.csv")

    assert report["kept_rows"] == 2
    assert "control_input_deg" in curated.columns
    assert "delta_e_sym_deg" in curated.columns
    assert "delta_a_diff_deg" in curated.columns
    assert curated["delta_e_sym_deg"].tolist() == [-5.0, 5.0]
    assert curated["delta_a_diff_deg"].tolist() == [0.0, 0.0]
