from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

optuna = pytest.importorskip("optuna")

from aeris.ml.optuna_tune import load_optuna_param_space_json, suggest_params_from_space, tune_model_optuna

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



def test_load_optuna_param_space_json_preserves_distribution_specs(tmp_path: Path) -> None:
    path = tmp_path / "space.json"
    path.write_text(
        json.dumps(
            {
                "search": {"backend": "optuna", "sampler": "random"},
                "params": {
                    "alpha": {"type": "float", "low": 0.01, "high": 10.0, "log": True},
                    "fit_intercept": [True, False],
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_optuna_param_space_json(path)

    assert loaded["search"]["backend"] == "optuna"
    assert loaded["params"]["alpha"] == {"type": "float", "low": 0.01, "high": 10.0, "log": True}
    assert loaded["params"]["fit_intercept"] == [True, False]

def test_suggest_params_from_space_supports_optuna_specs() -> None:
    fixed = optuna.trial.FixedTrial(
        {
            "alpha": 0.1,
            "fit_intercept": True,
            "max_iter": 1000,
        }
    )
    params = suggest_params_from_space(
        fixed,
        {
            "alpha": {"type": "float", "low": 0.001, "high": 1.0, "log": True},
            "fit_intercept": [True, False],
            "max_iter": {"type": "int", "low": 500, "high": 2000, "step": 500},
            "solver": {"type": "fixed", "value": "auto"},
        },
    )
    assert params == {
        "alpha": 0.1,
        "fit_intercept": True,
        "max_iter": 1000,
        "solver": "auto",
    }


def test_tune_model_optuna_writes_summary_and_best_trial(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "optuna_ridge_tune"

    result = tune_model_optuna(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="ridge",
        param_space={
            "alpha": {"type": "float", "low": 0.01, "high": 10.0, "log": True},
            "fit_intercept": [True, False],
        },
        n_trials=3,
        sampler_name="random",
        tuning_random_seed=123,
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert (output_dir / "tuning_summary.json").exists()
    assert (output_dir / "tuning_trials.csv").exists()
    assert (output_dir / "best_trial.json").exists()
    assert (output_dir / "trials" / "trial_0000" / "metrics.json").exists()

    summary = json.loads((output_dir / "tuning_summary.json").read_text(encoding="utf-8"))
    assert summary["backend"] == "optuna"
    assert summary["model_type"] == "ridge"
    assert summary["n_successful_trials"] == 3
    assert summary["best_trial"] is not None
    assert result["summary"]["best_trial"] is not None
    assert result["summary"]["best_trial"].get("model_params")

    rows = pd.read_csv(output_dir / "tuning_trials.csv")
    assert len(rows) == 3
    assert set(rows["status"]) == {"success"}
    assert rows["rank"].notna().any()
