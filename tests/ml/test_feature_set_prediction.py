from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.feature_sets import get_feature_set
from aeris.ml.inference_guard import check_inference_inputs
from aeris.ml.predict import predict_with_trained_model
from aeris.ml.train import train_baseline_model

TARGET_COLUMNS = ["cl", "cd", "cm"]
RAW_COLUMNS = [
    "c1_m",
    "b_total_m",
    "sw1_deg",
    "alpha_deg",
    "velocity_mps",
    "altitude_m",
    "control_input_deg",
]


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "feature_set_prediction_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
        for alpha in [-2.0, 0.0, 4.0]:
            for control in [-5.0, 0.0, 5.0]:
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
        "qc_context": {"qc_preset_used": "production", "geometry_qc_passed": True, "aero_qc_passed": True},
        "artifacts": {
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest, indent=2), encoding="utf-8")
    return dataset_root


def _train_physics_model(tmp_path: Path) -> Path:
    dataset = _build_dataset(tmp_path)
    fs = get_feature_set("bwb_control_physics_v1")
    out = tmp_path / "physics_model"
    train_baseline_model(
        dataset_path=dataset,
        feature_columns=list(fs.columns),
        target_columns=TARGET_COLUMNS,
        model_type="linear_regression",
        split_method="grouped",
        group_column="geometry_id",
        random_seed=123,
        output_dir=out,
        feature_set_name=fs.name,
    )
    return out


def test_predict_applies_feature_set_to_raw_input(tmp_path: Path) -> None:
    model_run = _train_physics_model(tmp_path)
    input_csv = tmp_path / "raw_candidates.csv"
    train_rows = pd.read_csv(model_run / "test_rows.csv")
    train_rows[["geometry_id", *RAW_COLUMNS, *TARGET_COLUMNS]].head(5).to_csv(input_csv, index=False)

    result = predict_with_trained_model(
        model_run_dir=model_run,
        input_csv=input_csv,
        output_dir=tmp_path / "predictions",
        feature_set_name="bwb_control_physics_v1",
    )

    summary = result["summary"]
    artifacts = result["artifacts"]
    assert summary["feature_set_name"] == "bwb_control_physics_v1"
    assert summary["trained_feature_set_name"] == "bwb_control_physics_v1"
    assert summary["feature_set_applied"] is True
    assert artifacts.materialized_input_csv_path is not None
    assert artifacts.materialized_input_csv_path.exists()
    assert "alpha_deg_sq" in result["predictions_df"].columns
    assert "pred__cl" in result["predictions_df"].columns


def test_predict_rejects_feature_set_mismatch_by_default(tmp_path: Path) -> None:
    model_run = _train_physics_model(tmp_path)
    input_csv = tmp_path / "raw_candidates.csv"
    pd.read_csv(model_run / "test_rows.csv")[["geometry_id", *RAW_COLUMNS, *TARGET_COLUMNS]].head(3).to_csv(input_csv, index=False)

    with pytest.raises(ValueError, match="Feature-set mismatch"):
        predict_with_trained_model(
            model_run_dir=model_run,
            input_csv=input_csv,
            output_dir=tmp_path / "bad_predictions",
            feature_set_name="bwb_control_raw",
        )


def test_inference_guard_applies_feature_set_before_range_checks(tmp_path: Path) -> None:
    model_run = _train_physics_model(tmp_path)
    input_csv = tmp_path / "raw_candidates.csv"
    pd.read_csv(model_run / "train_rows.csv")[["geometry_id", *RAW_COLUMNS]].head(5).to_csv(input_csv, index=False)

    train_rows = pd.read_csv(model_run / "train_rows.csv")
    feature_columns = json.loads((model_run / "train_config.json").read_text(encoding="utf-8"))["feature_columns"]
    feature_ranges = {
        col: {"min": float(train_rows[col].min()), "max": float(train_rows[col].max())}
        for col in feature_columns
    }
    (model_run / "training_envelope.json").write_text(
        json.dumps({"feature_ranges": feature_ranges}, indent=2),
        encoding="utf-8",
    )

    result = check_inference_inputs(
        model_run_dir=model_run,
        input_csv=input_csv,
        output_dir=tmp_path / "guard",
        require_promoted_model_gate=False,
        feature_set_name="bwb_control_physics_v1",
    )

    assert result.passed is True
    assert result.report["feature_set_name"] == "bwb_control_physics_v1"
    assert result.report["feature_set_applied"] is True
    assert "alpha_deg_sq" in result.report["feature_reports"]
