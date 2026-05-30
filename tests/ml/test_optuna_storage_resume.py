from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.optuna_tune import optuna_available, tune_model_optuna

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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
                    "cd": 0.02 + 0.001 * (alpha**2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )
    pd.DataFrame(rows).to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
    (dataset_root / "rejected_aero_rows.csv").write_text("", encoding="utf-8")
    _write_json(
        dataset_root / "promotion_manifest.json",
        {
            "dataset_root": str(dataset_root),
            "promotion_forced": False,
            "promotion_ready_at_time_of_promotion": True,
            "promotion_blockers": [],
            "qc_context": {"qc_preset_used": "production", "geometry_qc_passed": True, "aero_qc_passed": True},
            "artifacts": {
                "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
                "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
            },
        },
    )
    return dataset_root


@pytest.mark.skipif(not optuna_available(), reason="Optuna is not installed")
def test_optuna_sqlite_storage_resume_adds_trials(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    storage = f"sqlite:///{tmp_path / 'study.db'}"
    param_space = {"alpha": {"type": "float", "low": 0.01, "high": 1.0, "log": True}}

    first = tune_model_optuna(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="ridge",
        param_space=param_space,
        n_trials=2,
        sampler_name="random",
        tuning_random_seed=123,
        study_name="resume_test",
        storage=storage,
        load_if_exists=True,
        split_method="grouped",
        random_seed=123,
        output_dir=tmp_path / "optuna_resume",
    )
    assert first["summary"]["n_trials"] == 2

    second = tune_model_optuna(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="ridge",
        param_space=param_space,
        n_trials=1,
        sampler_name="random",
        tuning_random_seed=123,
        study_name="resume_test",
        storage=storage,
        load_if_exists=True,
        split_method="grouped",
        random_seed=123,
        output_dir=tmp_path / "optuna_resume",
    )
    assert second["summary"]["n_trials"] == 3
    assert second["summary"]["n_successful_trials"] == 3
