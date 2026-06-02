from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.compare import compare_models
from aeris.ml.feature_sets import get_feature_set
from aeris.ml.train import train_baseline_model
from aeris.ml.tune import tune_model

TARGET_COLUMNS = ["cl", "cd", "cm"]


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "feature_set_training_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    controls = [-5.0, 0.0, 5.0]
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
        for alpha in [-2.0, 0.0, 4.0]:
            for control in controls:
                rows.append(
                    {
                        "geometry_id": geom_id,
                        "c1_m": 1.5 + 0.01 * geom_idx,
                        "b_total_m": 1.6 + 0.02 * geom_idx,
                        "sw1_deg": 40.0 + geom_idx,
                        "alpha_deg": alpha,
                        "velocity_mps": 24.0 + geom_idx,
                        "altitude_m": 1000.0 + 100.0 * geom_idx,
                        "control_input_deg": control,
                        "cl": 0.1 * alpha + 0.01 * geom_idx + 0.002 * control,
                        "cd": 0.02 + 0.001 * (alpha**2) + 0.0002 * (control**2) + 0.0001 * geom_idx,
                        "cm": -0.05 * alpha + 0.005 * geom_idx - 0.01 * control,
                    }
                )

    pd.DataFrame(rows).to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
    (dataset_root / "rejected_aero_rows.csv").write_text("", encoding="utf-8")

    promotion_manifest = {
        "dataset_root": str(dataset_root),
        "promotion_forced": False,
        "promotion_ready_at_time_of_promotion": True,
        "promotion_blockers": [],
        "qc_context": {
            "qc_preset_used": "production",
            "geometry_qc_passed": True,
            "aero_qc_passed": True,
        },
        "artifacts": {
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest, indent=2), encoding="utf-8")
    return dataset_root


def test_train_baseline_model_accepts_physics_feature_set(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    feature_set = get_feature_set("bwb_control_physics_v1")
    output_dir = tmp_path / "train_physics_features"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=list(feature_set.columns),
        target_columns=TARGET_COLUMNS,
        model_type="linear_regression",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
        feature_set_name=feature_set.name,
    )

    assert result["metrics"]["model"]["model_type"] == "linear_regression"
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "feature_engineering_manifest.json").exists()
    assert (output_dir / "train_config.json").exists()
    assert (output_dir / "ml_run_manifest.json").exists()

    train_config = json.loads((output_dir / "train_config.json").read_text(encoding="utf-8"))
    assert train_config["feature_set_name"] == "bwb_control_physics_v1"
    assert train_config["feature_columns"] == list(feature_set.columns)

    manifest = json.loads((output_dir / "ml_run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["training_data"]["feature_set_name"] == "bwb_control_physics_v1"
    assert manifest["training_data"]["feature_set"]["name"] == "bwb_control_physics_v1"

    train_rows = pd.read_csv(output_dir / "train_rows.csv")
    assert "alpha_deg_sq" in train_rows.columns
    assert "re_number" in train_rows.columns


def test_compare_models_accepts_feature_set_name(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    feature_set = get_feature_set("bwb_control_physics_v1")

    result = compare_models(
        dataset_path=dataset_root,
        feature_columns=list(feature_set.columns),
        target_columns=TARGET_COLUMNS,
        model_types=["linear_regression", "ridge"],
        split_method="grouped",
        random_seed=123,
        output_dir=tmp_path / "compare_physics_features",
        feature_set_name=feature_set.name,
    )

    summary = result["summary"]
    assert summary["feature_set_name"] == "bwb_control_physics_v1"
    assert summary["feature_columns"] == list(feature_set.columns)
    assert result["comparison_summary_json"].exists()


def test_tune_model_accepts_feature_set_name(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    feature_set = get_feature_set("bwb_control_raw")

    result = tune_model(
        dataset_path=dataset_root,
        feature_columns=list(feature_set.columns),
        target_columns=TARGET_COLUMNS,
        model_type="ridge",
        param_space={"alpha": [0.1, 1.0]},
        strategy="grid",
        split_method="grouped",
        random_seed=123,
        output_dir=tmp_path / "tune_raw_features",
        feature_set_name=feature_set.name,
    )

    summary = result["summary"]
    assert summary["feature_set_name"] == "bwb_control_raw"
    assert summary["n_successful_trials"] == 2
    assert result["tuning_summary_json"].exists()
