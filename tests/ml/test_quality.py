from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app
from aeris.ml.model_promotion import promote_model_run
from aeris.ml.quality import audit_model, predict_with_confidence
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
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8"]):
        for alpha in [-2.0, 0.0, 4.0, 6.0]:
            for control in [-5.0, 0.0, 5.0]:
                rows.append(
                    {
                        "geometry_id": geom_id,
                        "c1_m": 1.5 + 0.01 * geom_idx,
                        "b_total_m": 1.6 + 0.01 * geom_idx,
                        "sw1_deg": 40.0 + 0.1 * geom_idx,
                        "alpha_deg": alpha,
                        "velocity_mps": 28.0,
                        "altitude_m": 1500.0,
                        "control_input_deg": control,
                        "cl": 0.1 * alpha + 0.005 * control + 0.01 * geom_idx,
                        "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0001 * (control ** 2) + 0.0001 * geom_idx,
                        "cm": -0.05 * alpha - 0.01 * control + 0.005 * geom_idx,
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


def _train_and_promote(tmp_path: Path) -> Path:
    dataset_root = _build_dataset(tmp_path)
    model_run_dir = tmp_path / "model_run"
    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        model_params={"n_estimators": 30},
        output_dir=model_run_dir,
    )
    result = promote_model_run(
        model_run_dir=model_run_dir,
        max_test_rmse_mean=1.0,
        min_test_r2_mean=-10.0,
    )
    assert result.passed is True
    return model_run_dir


def test_audit_model_writes_quality_report_and_residual_audit(tmp_path: Path) -> None:
    model_run_dir = _train_and_promote(tmp_path)
    output_dir = tmp_path / "quality_audit"

    result = audit_model(
        model_run_dir=model_run_dir,
        output_dir=output_dir,
        max_test_rmse_mean=1.0,
        min_test_r2_mean=-10.0,
    )

    assert result.passed is True
    assert result.status == "passed"
    assert (output_dir / "model_quality_report.json").exists()
    assert (output_dir / "residual_audit.csv").exists()
    assert result.report["partition_summaries"]["test"]["overall"]["rmse_mean"] >= 0.0


def test_predict_with_confidence_writes_confidence_outputs(tmp_path: Path) -> None:
    model_run_dir = _train_and_promote(tmp_path)
    input_csv = tmp_path / "input.csv"
    pd.read_csv(model_run_dir / "test_rows.csv").to_csv(input_csv, index=False)
    output_dir = tmp_path / "confidence"

    result = predict_with_confidence(
        model_run_dir=model_run_dir,
        input_csv=input_csv,
        output_dir=output_dir,
        require_promoted_model_gate=True,
    )

    assert (output_dir / "prediction_confidence.csv").exists()
    assert (output_dir / "prediction_confidence_report.json").exists()
    assert "confidence_status" in result.output_df.columns
    assert "uncertainty__cl" in result.output_df.columns
    assert result.report["n_rows"] == len(result.output_df)
    assert result.report["uncertainty"]["supported"] is True


def test_quality_cli_commands(tmp_path: Path) -> None:
    model_run_dir = _train_and_promote(tmp_path)
    input_csv = tmp_path / "input.csv"
    pd.read_csv(model_run_dir / "test_rows.csv").to_csv(input_csv, index=False)

    runner = CliRunner()
    audit_out = tmp_path / "audit_cli"
    audit_result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "ml",
            "audit-model",
            "--model-run-dir",
            str(model_run_dir),
            "--output-dir",
            str(audit_out),
            "--max-test-rmse-mean",
            "1.0",
            "--min-test-r2-mean",
            "-10.0",
        ],
    )
    assert audit_result.exit_code == 0, audit_result.output
    assert "ML model-quality audit completed" in audit_result.output
    assert (audit_out / "model_quality_report.json").exists()

    conf_out = tmp_path / "confidence_cli"
    confidence_result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "ml",
            "predict-with-confidence",
            "--model-run-dir",
            str(model_run_dir),
            "--input-csv",
            str(input_csv),
            "--output-dir",
            str(conf_out),
        ],
    )
    assert confidence_result.exit_code == 0, confidence_result.output
    assert "ML prediction with confidence completed" in confidence_result.output
    assert (conf_out / "prediction_confidence.csv").exists()
