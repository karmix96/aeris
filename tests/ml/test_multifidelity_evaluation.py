from __future__ import annotations

from pathlib import Path

import pandas as pd

from aeris.ml.multifidelity.delta_model import train_delta_model
from aeris.ml.multifidelity.evaluation import evaluate_delta_model_run, evaluate_multifidelity_predictions


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
    csv = path / "delta_dataset.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    return csv


def test_evaluate_multifidelity_predictions_detects_improvement() -> None:
    df = pd.DataFrame({
        "lf__cl": [1.0, 1.0],
        "hf__cl": [1.1, 1.1],
        "pred_corrected__cl": [1.09, 1.11],
    })
    report = evaluate_multifidelity_predictions(df, base_targets=["cl"])
    assert report["overall"]["status"] == "improved"
    assert report["per_target"]["cl"]["corrected_rmse"] < report["per_target"]["cl"]["lf_rmse"]


def test_evaluate_delta_model_run_writes_report(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    run_dir = tmp_path / "delta_model"
    train_delta_model(
        delta_dataset=csv,
        feature_columns=["c1_m", "alpha_deg", "velocity_mps", "lf__cl", "lf__cd", "lf__cm"],
        base_targets=["cl", "cd", "cm"],
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=run_dir,
    )
    result = evaluate_delta_model_run(model_run_dir=run_dir, output_dir=tmp_path / "eval")
    assert result.report_json.exists()
    assert result.report_csv.exists()
    assert "winner_report" in result.report
    assert result.report["winner_report"]["status"] in {"improved", "worse", "tied"}
