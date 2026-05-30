from __future__ import annotations

from pathlib import Path

import pandas as pd

from aeris.ml.multifidelity.delta_model import predict_with_delta_model, train_delta_model


def _delta_dataset(path: Path) -> Path:
    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
        for alpha in [0.0, 2.0, 4.0]:
            lf_cl = 0.10 + 0.04 * alpha + 0.005 * geom_idx
            lf_cd = 0.020 + 0.001 * alpha**2 + 0.0002 * geom_idx
            lf_cm = -0.050 - 0.010 * alpha + 0.001 * geom_idx
            dcl = 0.01 + 0.001 * alpha + 0.0005 * geom_idx
            dcd = 0.002 + 0.0001 * alpha
            dcm = -0.004 + 0.0002 * geom_idx
            rows.append({
                "geometry_id": geom_id,
                "alpha_deg": alpha,
                "velocity_mps": 28.0,
                "c1_m": 1.5 + 0.01 * geom_idx,
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
    df = pd.DataFrame(rows)
    csv = path / "delta_dataset.csv"
    df.to_csv(csv, index=False)
    return csv


def test_train_delta_model_and_predict(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    out_dir = tmp_path / "delta_model"
    features = ["c1_m", "alpha_deg", "velocity_mps", "lf__cl", "lf__cd", "lf__cm"]

    result = train_delta_model(
        delta_dataset=csv,
        feature_columns=features,
        base_targets=["cl", "cd", "cm"],
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=out_dir,
    )

    artifacts = result["artifacts"]
    assert artifacts.model_path.exists()
    assert artifacts.metrics_path.exists()
    assert artifacts.train_config_path.exists()
    assert artifacts.manifest_path.exists()
    assert (out_dir / "diagnostics" / "test_corrected_predictions.csv").exists()
    assert "corrected" in result["metrics"]["test"]

    pred = predict_with_delta_model(
        model_run_dir=out_dir,
        input_csv=artifacts.test_rows_path,
        output_dir=tmp_path / "delta_pred",
    )
    pred_df = pd.read_csv(pred["artifacts"].predictions_csv)
    assert "pred__delta__cl" in pred_df.columns
    assert "pred_corrected__cl" in pred_df.columns
    assert pred["summary"]["truth_available"] is True
    assert pred["summary"]["evaluation"] is not None
