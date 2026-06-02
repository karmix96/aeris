from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()

RAW_COLUMNS = [
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
    dataset_root = tmp_path / "feature_set_prediction_cli_dataset"
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


def _train_model_cli(tmp_path: Path) -> tuple[Path, Path]:
    dataset = _build_dataset(tmp_path)
    model_dir = tmp_path / "physics_model_cli"
    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_physics_v1",
            "--targets",
            "cl,cd,cm",
            "--model-type",
            "linear_regression",
            "--split-method",
            "grouped",
            "--output-dir",
            str(model_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    return dataset, model_dir


def test_ml_predict_cli_accepts_feature_set_for_raw_candidates(tmp_path: Path) -> None:
    _dataset, model_dir = _train_model_cli(tmp_path)
    input_csv = tmp_path / "raw_candidates.csv"
    pd.read_csv(model_dir / "test_rows.csv")[["geometry_id", *RAW_COLUMNS, *TARGET_COLUMNS]].head(4).to_csv(input_csv, index=False)
    out = tmp_path / "prediction_output"

    result = runner.invoke(
        app,
        [
            "ml",
            "predict",
            "--model-run-dir",
            str(model_dir),
            "--input-csv",
            str(input_csv),
            "--feature-set",
            "bwb_control_physics_v1",
            "--output-dir",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "feature_set_applied: True" in result.output
    summary = json.loads((out / "prediction_summary.json").read_text(encoding="utf-8"))
    assert summary["feature_set_name"] == "bwb_control_physics_v1"
    assert summary["feature_set_applied"] is True
    assert (out / "materialized_inference_input.csv").exists()
    predictions = pd.read_csv(out / "predictions.csv")
    assert "alpha_deg_sq" in predictions.columns
    assert "pred__cl" in predictions.columns


def test_ml_check_inference_inputs_cli_accepts_feature_set(tmp_path: Path) -> None:
    _dataset, model_dir = _train_model_cli(tmp_path)
    input_csv = tmp_path / "raw_candidates.csv"
    pd.read_csv(model_dir / "train_rows.csv")[["geometry_id", *RAW_COLUMNS]].head(4).to_csv(input_csv, index=False)

    train_config = json.loads((model_dir / "train_config.json").read_text(encoding="utf-8"))
    train_rows = pd.read_csv(model_dir / "train_rows.csv")
    feature_ranges = {
        col: {"min": float(train_rows[col].min()), "max": float(train_rows[col].max())}
        for col in train_config["feature_columns"]
    }
    (model_dir / "training_envelope.json").write_text(json.dumps({"feature_ranges": feature_ranges}, indent=2), encoding="utf-8")
    out = tmp_path / "guard_output"

    result = runner.invoke(
        app,
        [
            "ml",
            "check-inference-inputs",
            "--model-run-dir",
            str(model_dir),
            "--input-csv",
            str(input_csv),
            "--feature-set",
            "bwb_control_physics_v1",
            "--no-require-promoted-model",
            "--output-dir",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "feature_set_applied: True" in result.output
    report = json.loads((out / "inference_guard_report.json").read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["feature_set_name"] == "bwb_control_physics_v1"
    assert "alpha_deg_sq" in report["feature_reports"]


def test_ml_predict_cli_rejects_feature_set_mismatch(tmp_path: Path) -> None:
    _dataset, model_dir = _train_model_cli(tmp_path)
    input_csv = tmp_path / "raw_candidates.csv"
    pd.read_csv(model_dir / "test_rows.csv")[["geometry_id", *RAW_COLUMNS, *TARGET_COLUMNS]].head(4).to_csv(input_csv, index=False)

    result = runner.invoke(
        app,
        [
            "ml",
            "predict",
            "--model-run-dir",
            str(model_dir),
            "--input-csv",
            str(input_csv),
            "--feature-set",
            "bwb_control_raw",
            "--output-dir",
            str(tmp_path / "bad_prediction"),
        ],
    )

    assert result.exit_code != 0
    assert "Feature-set mismatch" in result.output
