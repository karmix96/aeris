from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.predict import predict_with_trained_model
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


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "ml_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
        for alpha in [-2.0, 0.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.01 * geom_idx,
                    "sw1_deg": 40.0,
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": 0.0,
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
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
    (dataset_root / "promotion_manifest.json").write_text(
        json.dumps(promotion_manifest, indent=2),
        encoding="utf-8",
    )

    return dataset_root


def test_predict_with_trained_model_writes_predictions_and_summary(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    model_run_dir = tmp_path / "linear_run"

    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="linear_regression",
        split_method="grouped",
        random_seed=123,
        output_dir=model_run_dir,
    )

    input_csv = tmp_path / "predict_input.csv"
    df = pd.read_csv(dataset_root / "curated_aero_dataset.csv")
    df.to_csv(input_csv, index=False)

    output_dir = tmp_path / "predict_out"
    result = predict_with_trained_model(
        model_run_dir=model_run_dir,
        input_csv=input_csv,
        output_dir=output_dir,
    )

    assert (output_dir / "predictions.csv").exists()
    assert (output_dir / "prediction_summary.json").exists()

    pred_df = pd.read_csv(output_dir / "predictions.csv")
    assert "pred__cl" in pred_df.columns
    assert "pred__cd" in pred_df.columns
    assert "pred__cm" in pred_df.columns
    assert "error__cl" in pred_df.columns
    assert "error__cd" in pred_df.columns
    assert "error__cm" in pred_df.columns

    summary = result["summary"]
    assert summary["model_type"] == "linear_regression"
    assert summary["truth_available"] is True
    assert summary["evaluation"] is not None


def test_predict_with_trained_model_works_without_truth_columns(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    model_run_dir = tmp_path / "rf_run"

    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="random_forest",
        split_method="grouped",
        random_seed=123,
        output_dir=model_run_dir,
    )

    input_csv = tmp_path / "predict_features_only.csv"
    df = pd.read_csv(dataset_root / "curated_aero_dataset.csv")[FEATURE_COLUMNS]
    df.to_csv(input_csv, index=False)

    output_dir = tmp_path / "predict_features_only_out"
    result = predict_with_trained_model(
        model_run_dir=model_run_dir,
        input_csv=input_csv,
        output_dir=output_dir,
    )

    pred_df = pd.read_csv(output_dir / "predictions.csv")
    assert "pred__cl" in pred_df.columns
    assert "pred__cd" in pred_df.columns
    assert "pred__cm" in pred_df.columns
    assert "error__cl" not in pred_df.columns

    summary = result["summary"]
    assert summary["truth_available"] is False
    assert summary["evaluation"] is None