from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.tune import build_param_trials, tune_model

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


def test_build_param_trials_grid_is_deterministic() -> None:
    trials = build_param_trials(
        {"alpha": [0.1, 1.0], "fit_intercept": [True, False]},
        strategy="grid",
    )
    assert trials == [
        {"alpha": 0.1, "fit_intercept": True},
        {"alpha": 0.1, "fit_intercept": False},
        {"alpha": 1.0, "fit_intercept": True},
        {"alpha": 1.0, "fit_intercept": False},
    ]


def test_tune_model_grid_writes_summary_and_best_trial(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "ridge_tune"

    result = tune_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="ridge",
        param_space={"alpha": [0.1, 1.0, 10.0]},
        strategy="grid",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert (output_dir / "tuning_summary.json").exists()
    assert (output_dir / "tuning_trials.csv").exists()
    assert (output_dir / "best_trial.json").exists()
    assert (output_dir / "trials" / "trial_0000" / "metrics.json").exists()
    assert (output_dir / "trials" / "trial_0001" / "metrics.json").exists()
    assert (output_dir / "trials" / "trial_0002" / "metrics.json").exists()

    summary = json.loads((output_dir / "tuning_summary.json").read_text(encoding="utf-8"))
    assert summary["model_type"] == "ridge"
    assert summary["n_trials"] == 3
    assert summary["n_successful_trials"] == 3
    assert summary["best_trial"] is not None
    assert summary["best_trial"]["trial_id"].startswith("trial_")

    rows = pd.read_csv(output_dir / "tuning_trials.csv")
    assert len(rows) == 3
    assert set(rows["status"]) == {"success"}
    assert rows["rank"].notna().any()
    assert result["summary"]["best_trial"] is not None
