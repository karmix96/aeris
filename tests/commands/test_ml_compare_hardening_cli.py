from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()

FEATURES = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "ml_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8"]):
        for alpha in [-2.0, 0.0, 2.0, 4.0]:
            for ctrl in [-5.0, 0.0, 5.0]:
                rows.append(
                    {
                        "geometry_id": geom_id,
                        "c1_m": 1.5 + 0.01 * geom_idx,
                        "b_total_m": 1.6 + 0.01 * geom_idx,
                        "sw1_deg": 35.0 + 0.5 * geom_idx,
                        "alpha_deg": alpha,
                        "velocity_mps": 28.0,
                        "altitude_m": 1500.0,
                        "control_input_deg": ctrl,
                        "cl": 0.1 * alpha + 0.002 * ctrl + 0.01 * geom_idx,
                        "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0002 * abs(ctrl) + 0.0001 * geom_idx,
                        "cm": -0.05 * alpha - 0.004 * ctrl + 0.005 * geom_idx,
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
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest), encoding="utf-8")
    return dataset_root


def test_ml_compare_seeds_cli_runs(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "cli_compare_seeds"

    result = runner.invoke(
        app,
        [
            "ml", "compare-seeds",
            "--dataset", str(dataset_root),
            "--features", FEATURES,
            "--targets", "cl,cd,cm",
            "--models", "linear_regression,ridge",
            "--seeds", "11,22",
            "--split-method", "grouped",
            "--group-column", "geometry_id",
            "--output-dir", str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "ML seed-stability comparison completed" in result.stdout
    assert "winner_by_mean_test_rmse" in result.stdout
    assert (output_dir / "comparison_seed_stability_summary.json").exists()
    assert (output_dir / "winner_report.json").exists()


def _write_fake_tuning_run(root: Path, *, model_type: str, score: float) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "best_trial.json").write_text(
        json.dumps({"trial_id": "trial_0000", "model_type": model_type, "model_params": {}, "selection_score": score}),
        encoding="utf-8",
    )
    (root / "tuning_summary.json").write_text(
        json.dumps({"model_type": model_type, "strategy": "grid", "n_trials": 1, "n_successful_trials": 1, "n_failed_trials": 0}),
        encoding="utf-8",
    )
    return root


def test_ml_compare_tuning_runs_cli_runs(tmp_path: Path) -> None:
    run_a = _write_fake_tuning_run(tmp_path / "tune_a", model_type="random_forest", score=0.02)
    run_b = _write_fake_tuning_run(tmp_path / "tune_b", model_type="extra_trees", score=0.01)
    output_dir = tmp_path / "cli_compare_tuning"

    result = runner.invoke(
        app,
        [
            "ml", "compare-tuning-runs",
            "--runs", f"{run_a},{run_b}",
            "--selection-metric", "val.rmse_mean",
            "--minimize",
            "--output-dir", str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "ML tuning-run comparison completed" in result.stdout
    assert "winner_model_type" in result.stdout
    assert (output_dir / "tuning_run_comparison.json").exists()
    assert (output_dir / "winner_report.json").exists()
