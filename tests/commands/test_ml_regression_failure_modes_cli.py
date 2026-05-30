from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app
from aeris.ml.model_promotion import promote_model_run
from aeris.ml.train import train_baseline_model

runner = CliRunner()

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
FEATURES_CSV = ",".join(FEATURE_COLUMNS)


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
                    "sw1_deg": 40.0 + 0.1 * geom_idx,
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
            "qc_context": {
                "qc_preset_used": "production",
                "geometry_qc_passed": True,
                "aero_qc_passed": True,
            },
            "artifacts": {
                "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
                "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
            },
        },
    )
    return dataset_root


def _train_model(dataset_root: Path, output_dir: Path) -> Path:
    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )
    return output_dir


def test_predict_require_promoted_model_rejects_unpromoted_run(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    model_run = _train_model(dataset_root, tmp_path / "model_run")
    input_csv = dataset_root / "curated_aero_dataset.csv"

    result = runner.invoke(
        app,
        [
            "ml",
            "predict",
            "--model-run-dir",
            str(model_run),
            "--input-csv",
            str(input_csv),
            "--require-promoted-model",
            "--output-dir",
            str(tmp_path / "predict_out"),
        ],
    )

    assert result.exit_code != 0


def test_predict_require_promoted_model_detects_hash_mismatch(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    model_run = _train_model(dataset_root, tmp_path / "model_run")
    promote_model_run(model_run_dir=model_run, max_test_rmse_mean=1.0, min_test_r2_mean=-1.0)
    (model_run / "models" / "model.pkl").write_bytes(b"tampered")

    result = runner.invoke(
        app,
        [
            "ml",
            "predict",
            "--model-run-dir",
            str(model_run),
            "--input-csv",
            str(dataset_root / "curated_aero_dataset.csv"),
            "--require-promoted-model",
            "--output-dir",
            str(tmp_path / "predict_out"),
        ],
    )

    assert result.exit_code != 0
    assert "hash" in (result.stdout + result.stderr).lower()


def test_predict_rejects_missing_feature_column(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    model_run = _train_model(dataset_root, tmp_path / "model_run")
    bad_input = tmp_path / "bad_input.csv"
    df = pd.read_csv(dataset_root / "curated_aero_dataset.csv")
    df = df.drop(columns=["alpha_deg"])
    df.to_csv(bad_input, index=False)

    result = runner.invoke(
        app,
        [
            "ml",
            "predict",
            "--model-run-dir",
            str(model_run),
            "--input-csv",
            str(bad_input),
            "--output-dir",
            str(tmp_path / "predict_bad"),
        ],
    )

    assert result.exit_code != 0


def test_tune_accepts_feature_preset_cli(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    param_space = tmp_path / "ridge_space.json"
    _write_json(param_space, {"params": {"alpha": [0.1], "fit_intercept": [True]}})

    result = runner.invoke(
        app,
        [
            "ml",
            "tune",
            "--backend",
            "aeris",
            "--dataset",
            str(dataset_root),
            "--feature-preset",
            "bwb_control",
            "--targets",
            "cl,cd,cm",
            "--model-type",
            "ridge",
            "--param-space-json",
            str(param_space),
            "--strategy",
            "grid",
            "--max-trials",
            "1",
            "--split-method",
            "grouped",
            "--output-dir",
            str(tmp_path / "tune_preset"),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "ML tuning completed" in result.stdout
    assert (tmp_path / "tune_preset" / "best_trial.json").exists()


def test_compare_accepts_feature_preset_cli(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)

    result = runner.invoke(
        app,
        [
            "ml",
            "compare",
            "--dataset",
            str(dataset_root),
            "--feature-preset",
            "bwb_control",
            "--targets",
            "cl,cd,cm",
            "--models",
            "linear_regression,ridge",
            "--split-method",
            "grouped",
            "--output-dir",
            str(tmp_path / "compare_preset"),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "ML model comparison completed" in result.stdout
    assert (tmp_path / "compare_preset" / "comparison_summary.json").exists()
