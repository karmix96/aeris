from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.compare import compare_models


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


def test_compare_models_writes_comparison_and_shared_split_artifacts(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "compare_run"

    result = compare_models(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_types=["linear_regression", "random_forest", "gradient_boosting"],
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert output_dir.exists()
    assert (output_dir / "comparison_summary.json").exists()
    assert (output_dir / "comparison_summary.csv").exists()

    summary = result["summary"]
    assert summary["model_types"] == ["linear_regression", "random_forest", "gradient_boosting"]
    assert len(summary["model_runs"]) == 3

    runs_by_model = {run["model_type"]: run for run in summary["model_runs"]}
    assert "linear_regression" in runs_by_model
    assert "random_forest" in runs_by_model
    assert "gradient_boosting" in runs_by_model

    lr_run = runs_by_model["linear_regression"]
    rf_run = runs_by_model["random_forest"]
    gb_run = runs_by_model["gradient_boosting"]

    assert lr_run["split"]["train_hash"] == rf_run["split"]["train_hash"] == gb_run["split"]["train_hash"]
    assert lr_run["split"]["val_hash"] == rf_run["split"]["val_hash"] == gb_run["split"]["val_hash"]
    assert lr_run["split"]["test_hash"] == rf_run["split"]["test_hash"] == gb_run["split"]["test_hash"]

    lr_dir = output_dir / "runs" / "linear_regression"
    rf_dir = output_dir / "runs" / "random_forest"
    gb_dir = output_dir / "runs" / "gradient_boosting"

    for path in [
        lr_dir / "metrics.json",
        lr_dir / "train_config.json",
        lr_dir / "train_rows.csv",
        lr_dir / "val_rows.csv",
        lr_dir / "test_rows.csv",
        lr_dir / "coefficients.json",
        lr_dir / "models" / "model.pkl",
        rf_dir / "metrics.json",
        rf_dir / "train_config.json",
        rf_dir / "train_rows.csv",
        rf_dir / "val_rows.csv",
        rf_dir / "test_rows.csv",
        rf_dir / "feature_importances.json",
        rf_dir / "models" / "model.pkl",
        gb_dir / "metrics.json",
        gb_dir / "train_config.json",
        gb_dir / "train_rows.csv",
        gb_dir / "val_rows.csv",
        gb_dir / "test_rows.csv",
        gb_dir / "feature_importances.json",
        gb_dir / "models" / "model.pkl",
    ]:
        assert path.exists(), f"Missing expected artifact: {path}"

    lr_train = pd.read_csv(lr_dir / "train_rows.csv")
    lr_val = pd.read_csv(lr_dir / "val_rows.csv")
    lr_test = pd.read_csv(lr_dir / "test_rows.csv")

    train_groups = set(lr_train["geometry_id"].unique())
    val_groups = set(lr_val["geometry_id"].unique())
    test_groups = set(lr_test["geometry_id"].unique())

    assert train_groups.isdisjoint(val_groups)
    assert train_groups.isdisjoint(test_groups)
    assert val_groups.isdisjoint(test_groups)


def test_compare_models_json_summary_contains_all_models_and_ranking_fields(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "compare_json"

    compare_models(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_types=["linear_regression", "random_forest", "gradient_boosting"],
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    payload = json.loads((output_dir / "comparison_summary.json").read_text(encoding="utf-8"))
    model_types = [run["model_type"] for run in payload["model_runs"]]

    assert model_types == ["linear_regression", "random_forest", "gradient_boosting"]
    assert payload["shared_split_hashes"]["train_hash"]
    assert payload["shared_split_hashes"]["val_hash"]
    assert payload["shared_split_hashes"]["test_hash"]

    assert payload["best_model_by_test_rmse_mean"] is not None
    assert payload["best_model_by_test_mae_mean"] is not None
    assert payload["best_model_by_test_r2_mean"] is not None

    for run in payload["model_runs"]:
        assert "rank_test_rmse_mean" in run["summary"]
        assert "rank_test_mae_mean" in run["summary"]
        assert "rank_test_r2_mean" in run["summary"]


def test_compare_models_ranking_fields_are_internally_consistent(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "compare_rankings"

    result = compare_models(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_types=["linear_regression", "random_forest", "gradient_boosting"],
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    summary = result["summary"]
    runs = summary["model_runs"]

    rmse_ranks = sorted(run["summary"]["rank_test_rmse_mean"] for run in runs)
    mae_ranks = sorted(run["summary"]["rank_test_mae_mean"] for run in runs)
    r2_ranks = sorted(run["summary"]["rank_test_r2_mean"] for run in runs)

    assert rmse_ranks == [1, 2, 3]
    assert mae_ranks == [1, 2, 3]
    assert r2_ranks == [1, 2, 3]

    best_rmse_run = next(run for run in runs if run["summary"]["rank_test_rmse_mean"] == 1)
    best_mae_run = next(run for run in runs if run["summary"]["rank_test_mae_mean"] == 1)
    best_r2_run = next(run for run in runs if run["summary"]["rank_test_r2_mean"] == 1)

    assert summary["best_model_by_test_rmse_mean"] == best_rmse_run["model_type"]
    assert summary["best_model_by_test_mae_mean"] == best_mae_run["model_type"]
    assert summary["best_model_by_test_r2_mean"] == best_r2_run["model_type"]