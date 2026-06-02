from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.model_promotion import inspect_model_run, promote_model_run, require_promoted_model
from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import get_feature_set


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_model_run(tmp_path: Path) -> Path:
    run = tmp_path / "model_run"
    (run / "models").mkdir(parents=True)
    (run / "diagnostics").mkdir()
    (run / "models" / "model.pkl").write_bytes(b"not-a-real-model-but-hashable")
    _write_json(run / "train_config.json", {
        "dataset_path": str(tmp_path / "dataset"),
        "feature_columns": ["c1_m", "alpha_deg"],
        "target_columns": ["cl", "cd"],
        "model_type": "extra_trees",
        "split_method": "grouped",
        "group_column": "geometry_id",
        "random_seed": 123,
        "allow_forced": False,
        "model_params": {"n_estimators": 10},
    })
    _write_json(run / "metrics.json", {
        "val": {"overall": {"rmse_mean": 0.01, "mae_mean": 0.01, "r2_mean": 0.99}},
        "test": {"overall": {"rmse_mean": 0.02, "mae_mean": 0.02, "r2_mean": 0.98}},
    })
    _write_json(run / "ml_run_manifest.json", {
        "dataset": {
            "promotion_context": {
                "promotion_ready_at_time_of_promotion": True,
                "promotion_forced": False,
                "promotion_blockers": [],
            },
            "fingerprints": {"curated_csv": {"sha256": "abc"}},
        },
        "split": {"method": "grouped"},
    })
    pd.DataFrame({
        "geometry_id": ["g1", "g2", "g3"],
        "c1_m": [1.0, 1.2, 1.4],
        "alpha_deg": [0.0, 2.0, 4.0],
        "cl": [0.1, 0.2, 0.3],
        "cd": [0.01, 0.02, 0.03],
    }).to_csv(run / "train_rows.csv", index=False)
    return run


def test_promote_and_require_model_run(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    result = promote_model_run(
        model_run_dir=run,
        max_val_rmse_mean=0.1,
        max_test_rmse_mean=0.1,
        min_test_r2_mean=0.9,
    )
    assert result.passed is True
    assert result.manifest_path.exists()
    assert result.model_card_path.exists()
    assert result.training_envelope_path is not None
    assert result.training_envelope_path.exists()
    manifest = require_promoted_model(run)
    assert manifest["status"] == "approved"
    info = inspect_model_run(run)
    assert info["promotion"]["status"] == "approved"
    assert info["model_type"] == "extra_trees"


def test_promotion_threshold_blocks_model(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    result = promote_model_run(model_run_dir=run, max_test_rmse_mean=0.001)
    assert result.passed is False
    assert result.manifest["status"] == "rejected"
    with pytest.raises(ValueError):
        require_promoted_model(run)



def _feature_set_promoted_dataset(tmp_path: Path) -> tuple[Path, pd.DataFrame]:
    dataset = tmp_path / "feature_set_dataset"
    dataset.mkdir(parents=True, exist_ok=True)
    raw_df = pd.DataFrame(
        {
            "geometry_id": ["g1", "g1", "g2", "g2"],
            "c1_m": [1.6, 1.6, 1.7, 1.7],
            "b_total_m": [1.6, 1.6, 1.8, 1.8],
            "sw1_deg": [-40.0, -40.0, -35.0, -35.0],
            "alpha_deg": [0.0, 4.0, 0.0, 4.0],
            "velocity_mps": [28.0, 28.0, 30.0, 30.0],
            "altitude_m": [1500.0, 1500.0, 1000.0, 1000.0],
            "control_input_deg": [-5.0, 5.0, -5.0, 5.0],
            "cl": [0.2, 0.5, 0.22, 0.54],
            "cd": [0.01, 0.03, 0.011, 0.032],
            "cm": [-0.2, -0.4, -0.21, -0.42],
        }
    )
    curated = dataset / "curated_aero_dataset.csv"
    raw_df.to_csv(curated, index=False)
    _write_json(
        dataset / "promotion_manifest.json",
        {
            "promotion_ready_at_time_of_promotion": True,
            "promotion_forced": False,
            "promotion_blockers": [],
            "artifacts": {"curated_aero_dataset_csv": str(curated)},
        },
    )
    return dataset, raw_df


def test_model_promotion_accepts_feature_set_engineered_columns(tmp_path: Path) -> None:
    dataset, raw_df = _feature_set_promoted_dataset(tmp_path)
    feature_set = get_feature_set("bwb_control_physics_v1")
    engineered_df, _ = apply_feature_engineering(raw_df, transforms=list(feature_set.transforms))

    run = _minimal_model_run(tmp_path)
    train_config_path = run / "train_config.json"
    train_config = json.loads(train_config_path.read_text(encoding="utf-8"))
    train_config.update(
        {
            "dataset_path": str(dataset),
            "feature_set_name": feature_set.name,
            "feature_set": feature_set.to_dict(),
            "feature_columns": list(feature_set.columns),
            "target_columns": ["cl", "cd", "cm"],
            "group_column": "geometry_id",
        }
    )
    _write_json(train_config_path, train_config)

    train_rows = engineered_df[["geometry_id", *feature_set.columns, "cl", "cd", "cm"]]
    train_rows.to_csv(run / "train_rows.csv", index=False)

    result = promote_model_run(
        model_run_dir=run,
        max_test_rmse_mean=0.1,
        min_test_r2_mean=0.9,
    )

    assert result.passed is True
    assert result.manifest["status"] == "approved"
    assert result.manifest["feature_set_name"] == "bwb_control_physics_v1"
    assert result.manifest["model"]["feature_set_name"] == "bwb_control_physics_v1"
    assert not any("Missing required columns" in blocker for blocker in result.blockers)
