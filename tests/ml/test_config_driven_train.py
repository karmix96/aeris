from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from aeris.ml.config import (
    load_ml_experiment_config,
    load_model_params_by_type_json,
    load_model_params_json,
)
from aeris.ml.train import train_baseline_model_from_config


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
    (dataset_root / "promotion_manifest.json").write_text(
        json.dumps(
            {
                "dataset_root": str(dataset_root),
                "promotion_forced": False,
                "promotion_ready_at_time_of_promotion": True,
                "promotion_blockers": [],
                "qc_context": {"qc_preset_used": "production"},
                "artifacts": {
                    "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
                    "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return dataset_root


def _write_config(tmp_path: Path, dataset_root: Path, output_dir: Path) -> Path:
    config_path = tmp_path / "ml_config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "ml": {
                    "dataset": str(dataset_root),
                    "features": FEATURE_COLUMNS,
                    "targets": TARGET_COLUMNS,
                    "split": {
                        "method": "grouped",
                        "group_column": "geometry_id",
                        "train_fraction": 0.7,
                        "val_fraction": 0.15,
                        "test_fraction": 0.15,
                        "random_seed": 123,
                    },
                    "model": {
                        "type": "random_forest",
                        "params": {"n_estimators": 11, "max_depth": 3},
                    },
                    "output_dir": str(output_dir),
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def test_load_ml_experiment_config(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "config_run"
    config_path = _write_config(tmp_path, dataset_root, output_dir)

    cfg = load_ml_experiment_config(config_path)

    assert cfg.dataset_path == dataset_root
    assert cfg.feature_columns == FEATURE_COLUMNS
    assert cfg.target_columns == TARGET_COLUMNS
    assert cfg.model_type == "random_forest"
    assert cfg.model_params["n_estimators"] == 11
    assert cfg.output_dir == output_dir


def test_train_baseline_model_from_config(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "config_run"
    config_path = _write_config(tmp_path, dataset_root, output_dir)

    result = train_baseline_model_from_config(config_path)

    assert result["metrics"]["model"]["model_type"] == "random_forest"
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "feature_importances.json").exists()

    train_config = json.loads((output_dir / "train_config.json").read_text(encoding="utf-8"))
    assert train_config["model_params"]["n_estimators"] == 11
    assert train_config["source_config_path"] == str(config_path.resolve())
    assert train_config["source_config_sha256"]

    manifest = json.loads((output_dir / "ml_run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_config"]["path"] == str(config_path.resolve())
    assert manifest["source_config"]["sha256"]


def test_model_params_json_loaders(tmp_path: Path) -> None:
    flat = tmp_path / "flat.json"
    flat.write_text('{"n_estimators": 9, "max_depth": 2}', encoding="utf-8")
    assert load_model_params_json(flat) == {"n_estimators": 9, "max_depth": 2}

    by_type = tmp_path / "by_type.json"
    by_type.write_text(
        '{"random_forest": {"n_estimators": 9}, "gradient_boosting": {"learning_rate": 0.05}}',
        encoding="utf-8",
    )
    loaded = load_model_params_by_type_json(by_type)
    assert loaded["random_forest"]["n_estimators"] == 9
    assert loaded["gradient_boosting"]["learning_rate"] == 0.05
