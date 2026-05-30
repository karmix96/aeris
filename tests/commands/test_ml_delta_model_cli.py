from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


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


def test_ml_train_and_predict_delta_model_cli(tmp_path: Path) -> None:
    csv = _delta_dataset(tmp_path)
    run_dir = tmp_path / "delta_model"
    train = runner.invoke(app, [
        "ml", "train-delta-model",
        "--delta-dataset", str(csv),
        "--features", "c1_m,alpha_deg,velocity_mps,lf__cl,lf__cd,lf__cm",
        "--base-targets", "cl,cd,cm",
        "--model-type", "extra_trees",
        "--split-method", "grouped",
        "--output-dir", str(run_dir),
    ])
    assert train.exit_code == 0, train.stdout
    assert "ML multifidelity delta model trained" in train.stdout
    assert (run_dir / "models" / "model.pkl").exists()
    assert (run_dir / "delta_model_manifest.json").exists()

    pred = runner.invoke(app, [
        "ml", "predict-delta-model",
        "--model-run-dir", str(run_dir),
        "--input-csv", str(run_dir / "test_rows.csv"),
        "--output-dir", str(tmp_path / "delta_pred"),
    ])
    assert pred.exit_code == 0, pred.stdout
    assert "ML multifidelity delta prediction completed" in pred.stdout
    assert (tmp_path / "delta_pred" / "delta_predictions.csv").exists()
