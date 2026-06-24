from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd
from sklearn.exceptions import DataConversionWarning

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

    df = pd.DataFrame(rows)
    df.to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
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


def test_train_linear_regression_grouped(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "linear_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="linear_regression",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert output_dir.exists()
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "train_config.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "coefficients.json").exists()

    split = result["split"]
    train_groups = set(split.train_df["geometry_id"].unique())
    val_groups = set(split.val_df["geometry_id"].unique())
    test_groups = set(split.test_df["geometry_id"].unique())

    assert train_groups.isdisjoint(val_groups)
    assert train_groups.isdisjoint(test_groups)
    assert val_groups.isdisjoint(test_groups)

    metrics = result["metrics"]
    assert metrics["model"]["model_type"] == "linear_regression"
    assert metrics["model"]["family_name"] == "linear_model"
    assert metrics["model"]["explainability_artifact_type"] == "coefficients"


def test_train_random_forest_random_split(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "rf_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="random_forest",
        split_method="random",
        random_seed=123,
        output_dir=output_dir,
    )

    assert output_dir.exists()
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "train_config.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "feature_importances.json").exists()

    metrics = result["metrics"]
    assert "train" in metrics
    assert "val" in metrics
    assert "test" in metrics
    assert "overall" in metrics["test"]
    assert metrics["model"]["model_type"] == "random_forest"


def test_train_gradient_boosting_grouped(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "gb_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="gradient_boosting",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert output_dir.exists()
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "train_config.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "feature_importances.json").exists()

    metrics = result["metrics"]
    assert metrics["model"]["model_type"] == "gradient_boosting"
    assert metrics["model"]["family_name"] == "tree_boosting"
    assert metrics["model"]["wrapped_per_target"] is True


def test_gradient_boosting_feature_importances_are_per_target(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "gb_importances"

    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="gradient_boosting",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    payload = json.loads((output_dir / "feature_importances.json").read_text(encoding="utf-8"))

    assert set(payload["targets"].keys()) == set(TARGET_COLUMNS)
    for target in TARGET_COLUMNS:
        assert set(payload["targets"][target]["feature_importances"].keys()) == set(FEATURE_COLUMNS)


def test_train_ridge_writes_coefficients(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "ridge_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="ridge",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert (output_dir / "coefficients.json").exists()
    assert result["metrics"]["model"]["model_type"] == "ridge"
    assert result["metrics"]["model"]["family_name"] == "linear_regularized"


def test_train_extra_trees_writes_feature_importances(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "extra_trees_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert (output_dir / "feature_importances.json").exists()
    assert result["metrics"]["model"]["model_type"] == "extra_trees"
    assert result["metrics"]["model"]["family_name"] == "tree_ensemble"


def test_train_hist_gradient_boosting_writes_no_explainability_artifact(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "hist_gb_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="hist_gradient_boosting",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert not (output_dir / "coefficients.json").exists()
    assert not (output_dir / "feature_importances.json").exists()

    assert result["metrics"]["model"]["model_type"] == "hist_gradient_boosting"
    assert result["metrics"]["model"]["explainability_artifact_type"] == "none"


def test_single_target_training_does_not_emit_data_conversion_warning(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "single_target_extra_trees"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = train_baseline_model(
            dataset_path=dataset_root,
            feature_columns=FEATURE_COLUMNS,
            target_columns=["cl"],
            model_type="extra_trees",
            split_method="grouped",
            random_seed=123,
            model_params={"n_estimators": 5},
            output_dir=output_dir,
        )

    data_conversion_warnings = [
        warning for warning in caught
        if issubclass(warning.category, DataConversionWarning)
    ]
    assert data_conversion_warnings == []
    assert result["metrics"]["test"]["overall"]["n_targets"] == 1
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "metrics.json").exists()
