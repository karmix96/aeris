from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd
from sklearn.exceptions import ConvergenceWarning

from aeris.ml.train import train_baseline_model


FEATURE_COLUMNS = [
    "c1_m",
    "b_total_m",
    "sw1_deg",
    "alpha_deg",
    "velocity_mps",
    "altitude_m",
    "control_input_deg",
]
TARGET_COLUMNS = ["cl", "cd", "cm"]


def _write_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "ml_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8"]):
        for alpha in [-2.0, 0.0, 2.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "c1_m": 1.5 + 0.02 * geom_idx,
                    "b_total_m": 1.6 + 0.01 * geom_idx,
                    "sw1_deg": 35.0 + geom_idx,
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": 0.0,
                    "cl": 0.12 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0001 * geom_idx,
                    "cm": -0.04 * alpha + 0.004 * geom_idx,
                }
            )
    pd.DataFrame(rows).to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
    (dataset_root / "rejected_aero_rows.csv").write_text("", encoding="utf-8")
    (dataset_root / "promotion_manifest.json").write_text(
        json.dumps(
            {
                "dataset_root": str(dataset_root),
                "promotion_forced": False,
                "promotion_ready_at_time_of_promotion": True,
                "promotion_blockers": [],
                "artifacts": {
                    "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
                    "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return dataset_root


def test_training_monitor_marks_tree_model_non_iterative(tmp_path: Path) -> None:
    dataset_root = _write_dataset(tmp_path)
    output_dir = tmp_path / "extra_trees_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        model_params={"n_estimators": 5},
        output_dir=output_dir,
    )

    artifacts = result["artifacts"]
    assert artifacts.training_monitor_report_path is not None
    assert artifacts.training_monitor_report_path.exists()
    assert artifacts.training_history_path is None

    report = json.loads(artifacts.training_monitor_report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "aeris.training_monitor.v1"
    assert report["monitor_status"] == "non_iterative_model"
    assert report["history_available"] is False
    assert "learning-curves" in report["recommended_next_diagnostic"]

    manifest = json.loads((output_dir / "ml_run_manifest.json").read_text(encoding="utf-8"))
    assert "training_monitor_report_path" in manifest["artifacts"]


def test_training_monitor_extracts_sklearn_mlp_loss_history(tmp_path: Path) -> None:
    dataset_root = _write_dataset(tmp_path)
    output_dir = tmp_path / "neural_mlp_run"

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        result = train_baseline_model(
            dataset_path=dataset_root,
            feature_columns=FEATURE_COLUMNS,
            target_columns=TARGET_COLUMNS,
            model_type="neural_mlp",
            split_method="grouped",
            random_seed=123,
            model_params={
                "hidden_layer_sizes": [8],
                "max_iter": 12,
                "early_stopping": False,
                "tol": 0.0,
            },
            output_dir=output_dir,
        )

    artifacts = result["artifacts"]
    assert artifacts.training_monitor_report_path is not None
    assert artifacts.training_monitor_report_path.exists()
    assert artifacts.training_history_path is not None
    assert artifacts.training_history_path.exists()

    report = json.loads(artifacts.training_monitor_report_path.read_text(encoding="utf-8"))
    assert report["monitor_status"] == "iterative_history_available"
    assert report["history_available"] is True
    assert report["n_history_rows"] >= 1

    history_text = artifacts.training_history_path.read_text(encoding="utf-8")
    assert "epoch" in history_text
    assert "train_loss" in history_text
