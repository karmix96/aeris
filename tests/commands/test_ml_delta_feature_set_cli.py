from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _delta_dataset(path: Path) -> Path:
    rows = []
    controls = [-5.0, 0.0, 5.0]
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
        for alpha_idx, alpha in enumerate([0.0, 2.0, 4.0]):
            control = controls[alpha_idx]
            lf_cl = 0.10 + 0.04 * alpha + 0.005 * geom_idx + 0.001 * control
            lf_cd = 0.020 + 0.001 * alpha**2 + 0.0002 * geom_idx + 0.00005 * control**2
            lf_cm = -0.050 - 0.010 * alpha + 0.001 * geom_idx - 0.002 * control
            dcl = 0.01 + 0.001 * alpha + 0.0005 * geom_idx
            dcd = 0.002 + 0.0001 * alpha
            dcm = -0.004 + 0.0002 * geom_idx
            rows.append({
                "geometry_id": geom_id,
                "c1_m": 1.5 + 0.01 * geom_idx,
                "b_total_m": 1.6 + 0.02 * geom_idx,
                "sw1_deg": -40.0 + geom_idx,
                "alpha_deg": alpha,
                "velocity_mps": 26.0 + geom_idx,
                "altitude_m": 1000.0 + 50.0 * geom_idx,
                "control_input_deg": control,
                "lf__cl": lf_cl,
                "lf__cd": lf_cd,
                "lf__cm": lf_cm,
                "hf__cl": lf_cl + dcl,
                "hf__cd": lf_cd + dcd,
                "hf__cm": lf_cm + dcm,
                "delta__cl": dcl,
                "delta__cd": dcd,
                "delta__cm": dcm,
            })
    csv = path / "delta_dataset.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    return csv


def _raw_delta_input_from_partition(partition_csv: Path, output_csv: Path) -> Path:
    df = pd.read_csv(partition_csv)
    engineered = {
        "alpha_deg_sq", "abs_alpha_deg", "control_input_deg_sq", "alpha_x_control",
        "velocity_sq", "ar_proxy", "sw1_x_alpha", "re_number",
    }
    keep = [column for column in df.columns if column not in engineered]
    df[keep].to_csv(output_csv, index=False)
    return output_csv


def test_ml_delta_model_cli_accepts_feature_set_for_train_and_predict(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    run_dir = tmp_path / "delta_model_feature_set_cli"

    train = runner.invoke(app, [
        "ml", "train-delta-model",
        "--delta-dataset", str(csv),
        "--feature-set", "bwb_control_physics_v1",
        "--base-targets", "cl,cd,cm",
        "--model-type", "extra_trees",
        "--split-method", "grouped",
        "--output-dir", str(run_dir),
    ])
    assert train.exit_code == 0, train.output
    assert "feature_set: bwb_control_physics_v1" in train.output
    assert (run_dir / "delta_model_manifest.json").exists()

    raw_input = _raw_delta_input_from_partition(run_dir / "test_rows.csv", tmp_path / "raw_delta_candidates.csv")
    pred_dir = tmp_path / "delta_pred_feature_set_cli"
    pred = runner.invoke(app, [
        "ml", "predict-delta-model",
        "--model-run-dir", str(run_dir),
        "--input-csv", str(raw_input),
        "--feature-set", "bwb_control_physics_v1",
        "--output-dir", str(pred_dir),
    ])
    assert pred.exit_code == 0, pred.output
    assert "feature_set_applied: True" in pred.output
    assert (pred_dir / "delta_predictions.csv").exists()
    assert (pred_dir / "materialized_delta_inference_input.csv").exists()


def test_ml_train_delta_model_rejects_mixed_feature_inputs(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    result = runner.invoke(app, [
        "ml", "train-delta-model",
        "--delta-dataset", str(csv),
        "--features", "c1_m,alpha_deg,lf__cl,lf__cd,lf__cm",
        "--feature-set", "bwb_control_raw",
        "--base-targets", "cl,cd,cm",
        "--output-dir", str(tmp_path / "bad"),
    ])
    assert result.exit_code != 0
    assert "Use only one of feature_columns or feature_set_name" in result.output
