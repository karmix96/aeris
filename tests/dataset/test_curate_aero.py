from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.dataset.curate_aero import curate_aero_dataset


def test_curate_aero_rejects_incomplete_group(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "geometry_id": "geom_00001",
                "cl": 0.5,
                "cd": 0.02,
                "cm": -0.01,
                "diag_airplane_has_control_surfaces": True,
                "diag_airplane_avl_has_control_blocks": True,
                "diag_keystrokes_has_d1_command": True,
            },
            {
                "geometry_id": "geom_00002",
                "cl": 0.6,
                "cd": 0.03,
                "cm": -0.02,
                "diag_airplane_has_control_surfaces": True,
                "diag_airplane_avl_has_control_blocks": True,
                "diag_keystrokes_has_d1_command": True,
            },
            {
                "geometry_id": "geom_00002",
                "cl": 0.7,
                "cd": 0.04,
                "cm": -0.03,
                "diag_airplane_has_control_surfaces": True,
                "diag_airplane_avl_has_control_blocks": True,
                "diag_keystrokes_has_d1_command": True,
            },
        ]
    ).to_csv(dataset_root / "aero_dataset.csv", index=False)

    pd.DataFrame(columns=["geometry_id", "error_type", "error_message"]).to_csv(
        dataset_root / "aero_failures.csv",
        index=False,
    )

    manifest = {
        "alpha_values": [0.0],
        "beta_values": [0.0],
        "velocity_values": [28.0],
        "altitude_values": [1500.0],
        "p_values": [0.0],
        "q_values": [0.0],
        "r_values": [0.0],
        "control_input_values": [-5.0, 5.0],
    }
    (dataset_root / "aero_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    report = curate_aero_dataset(dataset_root=dataset_root)

    curated = pd.read_csv(dataset_root / "curated_aero_dataset.csv")
    rejected = pd.read_csv(dataset_root / "rejected_aero_rows.csv")

    assert report["kept_geometries"] == 1
    assert report["rejected_geometries"] == 1
    assert set(curated["geometry_id"].unique()) == {"geom_00002"}
    assert set(rejected["geometry_id"].unique()) == {"geom_00001"}
    assert report["rejection_reason_counts"]["incomplete_sweep_group"] == 1


def test_curate_aero_rejects_nonfinite_target_group(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "geometry_id": "geom_00001",
                "cl": 0.5,
                "cd": 0.02,
                "cm": -0.01,
            },
            {
                "geometry_id": "geom_00002",
                "cl": float("nan"),
                "cd": 0.03,
                "cm": -0.02,
            },
        ]
    ).to_csv(dataset_root / "aero_dataset.csv", index=False)

    pd.DataFrame(columns=["geometry_id", "error_type", "error_message"]).to_csv(
        dataset_root / "aero_failures.csv",
        index=False,
    )

    (dataset_root / "aero_dataset_manifest.json").write_text(
        json.dumps({}),
        encoding="utf-8",
    )

    report = curate_aero_dataset(
        dataset_root=dataset_root,
        reject_incomplete_groups=False,
        reject_groups_with_failures=False,
        reject_control_diagnostic_failures=False,
    )

    curated = pd.read_csv(dataset_root / "curated_aero_dataset.csv")
    rejected = pd.read_csv(dataset_root / "rejected_aero_rows.csv")

    assert set(curated["geometry_id"].unique()) == {"geom_00001"}
    assert set(rejected["geometry_id"].unique()) == {"geom_00002"}
    assert report["rejection_reason_counts"]["nonfinite_target_values"] == 1