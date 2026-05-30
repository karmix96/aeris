from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

pytest.importorskip("optuna")

from aeris.cli import app

runner = CliRunner()

FEATURES = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"


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
        "qc_context": {"qc_preset_used": "production", "geometry_qc_passed": True, "aero_qc_passed": True},
        "artifacts": {
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest, indent=2), encoding="utf-8")
    return dataset_root


def test_ml_tune_cli_runs_optuna_backend(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "cli_optuna_tune"
    param_space = tmp_path / "ridge_optuna_space.json"
    param_space.write_text(
        json.dumps(
            {
                "params": {
                    "alpha": {"type": "float", "low": 0.01, "high": 10.0, "log": True},
                    "fit_intercept": [True, False],
                }
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "ml", "tune",
            "--backend", "optuna",
            "--dataset", str(dataset_root),
            "--features", FEATURES,
            "--targets", "cl,cd,cm",
            "--model-type", "ridge",
            "--param-space-json", str(param_space),
            "--n-trials", "2",
            "--optuna-sampler", "random",
            "--split-method", "grouped",
            "--output-dir", str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "ML tuning completed" in result.stdout
    assert "backend: optuna" in result.stdout
    assert "best_trial" in result.stdout
    assert "best_params" in result.stdout
    assert (output_dir / "tuning_summary.json").exists()
    assert (output_dir / "tuning_trials.csv").exists()
    assert (output_dir / "best_trial.json").exists()
