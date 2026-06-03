from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.multifidelity.delta_model import predict_with_delta_model, train_delta_model


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


def test_train_delta_model_with_feature_set_and_predict_from_raw_input(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    out_dir = tmp_path / "delta_model_feature_set"

    result = train_delta_model(
        delta_dataset=csv,
        feature_set_name="bwb_control_physics_v1",
        base_targets=["cl", "cd", "cm"],
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=out_dir,
    )

    assert result["manifest"]["feature_set_name"] == "bwb_control_physics_v1"
    assert "alpha_deg_sq" in result["manifest"]["features"]
    assert "lf__cl" in result["manifest"]["features"]

    raw_input = _raw_delta_input_from_partition(
        result["artifacts"].test_rows_path,
        tmp_path / "raw_delta_candidates.csv",
    )
    pred = predict_with_delta_model(
        model_run_dir=out_dir,
        input_csv=raw_input,
        output_dir=tmp_path / "delta_pred_feature_set",
        feature_set_name="bwb_control_physics_v1",
    )

    summary = pred["summary"]
    assert summary["feature_set_name"] == "bwb_control_physics_v1"
    assert summary["feature_set_applied"] is True
    assert Path(summary["materialized_delta_inference_input_csv"]).exists()
    assert Path(summary["feature_engineering_manifest_json"]).exists()
    pred_df = pd.read_csv(pred["artifacts"].predictions_csv)
    assert "pred_corrected__cl" in pred_df.columns
    assert pred["summary"]["truth_available"] is True


def test_predict_delta_model_rejects_feature_set_mismatch(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    out_dir = tmp_path / "delta_model_feature_set"
    result = train_delta_model(
        delta_dataset=csv,
        feature_set_name="bwb_control_physics_v1",
        base_targets=["cl", "cd", "cm"],
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=out_dir,
    )
    raw_input = _raw_delta_input_from_partition(result["artifacts"].test_rows_path, tmp_path / "raw.csv")

    with pytest.raises(ValueError, match="Feature-set mismatch"):
        predict_with_delta_model(
            model_run_dir=out_dir,
            input_csv=raw_input,
            output_dir=tmp_path / "bad",
            feature_set_name="bwb_control_raw",
        )



def test_delta_feature_set_training_writes_complete_provenance(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    out_dir = tmp_path / "delta_model_feature_set_provenance"

    result = train_delta_model(
        delta_dataset=csv,
        feature_set_name="bwb_control_physics_v1",
        base_targets=["cl", "cd", "cm"],
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=out_dir,
    )

    manifest = result["manifest"]
    assert manifest["feature_set_name"] == "bwb_control_physics_v1"
    assert manifest["feature_columns"] == manifest["features"]
    assert manifest["final_features"] == manifest["features"]
    assert manifest["target_columns"] == ["delta__cl", "delta__cd", "delta__cm"]
    assert manifest["lf_target_columns"] == ["lf__cl", "lf__cd", "lf__cm"]
    assert manifest["hf_target_columns"] == ["hf__cl", "hf__cd", "hf__cm"]
    assert "alpha_deg_sq" in manifest["feature_columns"]
    assert "lf__cl" in manifest["feature_columns"]

    # Canonical delta config and normal-ML-compatible alias both exist.
    assert (out_dir / "delta_train_config.json").exists()
    assert (out_dir / "train_config.json").exists()
    assert (out_dir / "feature_engineering_manifest.json").exists()

    config = __import__("json").loads((out_dir / "train_config.json").read_text())
    assert config["feature_set_name"] == "bwb_control_physics_v1"
    assert config["feature_columns"] == manifest["feature_columns"]
    assert config["final_features"] == manifest["final_features"]
    assert config["target_columns"] == manifest["target_columns"]

    fem = __import__("json").loads((out_dir / "feature_engineering_manifest.json").read_text())
    applied = {item["key"] for item in fem.get("transforms_applied", [])}
    assert "alpha_sq" in applied
    assert "re_number" in applied

    artifacts = manifest["artifacts"]
    assert artifacts["standard_train_config_json"].endswith("train_config.json")
    assert artifacts["feature_engineering_manifest_json"].endswith("feature_engineering_manifest.json")
