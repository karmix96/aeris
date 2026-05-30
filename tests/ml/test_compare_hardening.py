from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.compare_hardening import compare_models_across_seeds, compare_tuning_runs

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
        "qc_context": {
            "qc_preset_used": "production",
            "geometry_qc_passed": True,
            "aero_qc_passed": True,
        },
        "artifacts": {
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(
        json.dumps(promotion_manifest, indent=2),
        encoding="utf-8",
    )
    return dataset_root


def test_compare_models_across_seeds_writes_stability_outputs(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "seed_stability"

    result = compare_models_across_seeds(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_types=["linear_regression", "ridge"],
        seeds=[11, 22],
        split_method="grouped",
        group_column="geometry_id",
        output_dir=output_dir,
    )

    assert (output_dir / "comparison_seed_stability_summary.json").exists()
    assert (output_dir / "seed_stability_rows.csv").exists()
    assert (output_dir / "model_stability_summary.csv").exists()
    assert (output_dir / "model_stability_summary.json").exists()
    assert (output_dir / "per_target_ranking.csv").exists()
    assert (output_dir / "winner_report.json").exists()

    summary = result["summary"]
    assert summary["seeds"] == [11, 22]
    assert summary["model_types"] == ["linear_regression", "ridge"]
    assert len(summary["model_stability"]) == 2
    assert summary["winner_report"]["winner_by_mean_test_rmse"] in {"linear_regression", "ridge"}

    rows = pd.read_csv(output_dir / "seed_stability_rows.csv")
    assert set(rows["seed"]) == {11, 22}
    assert set(rows["model_type"]) == {"linear_regression", "ridge"}

    target_rows = pd.read_csv(output_dir / "per_target_ranking.csv")
    assert set(target_rows["target"]) == set(TARGET_COLUMNS)
    assert "rank_target_test_rmse" in target_rows.columns


def _write_fake_tuning_run(root: Path, *, model_type: str, score: float, params: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "best_trial.json").write_text(
        json.dumps(
            {
                "trial_id": "trial_0000",
                "model_type": model_type,
                "model_params": params,
                "selection_score": score,
                "selection_metric": "val.rmse_mean",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "tuning_summary.json").write_text(
        json.dumps(
            {
                "model_type": model_type,
                "strategy": "grid",
                "n_trials": 2,
                "n_successful_trials": 2,
                "n_failed_trials": 0,
                "selection_metric": "val.rmse_mean",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


def test_compare_tuning_runs_ranks_best_trials(tmp_path: Path) -> None:
    gb = _write_fake_tuning_run(tmp_path / "tune_gb", model_type="gradient_boosting", score=0.02, params={"n_estimators": 100})
    rf = _write_fake_tuning_run(tmp_path / "tune_rf", model_type="random_forest", score=0.01, params={"n_estimators": 50})
    output_dir = tmp_path / "tuning_compare"

    result = compare_tuning_runs(
        tuning_run_dirs=[gb, rf],
        selection_metric="val.rmse_mean",
        minimize=True,
        output_dir=output_dir,
    )

    assert (output_dir / "tuning_run_comparison.json").exists()
    assert (output_dir / "tuning_run_comparison.csv").exists()
    assert (output_dir / "winner_report.json").exists()
    assert result["summary"]["winner_report"]["winner_model_type"] == "random_forest"

    rows = pd.read_csv(output_dir / "tuning_run_comparison.csv")
    assert len(rows) == 2
    assert int(rows.loc[rows["model_type"] == "random_forest", "rank"].iloc[0]) == 1
