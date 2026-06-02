from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "feature_set_cli_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
        for alpha in [-2.0, 0.0, 4.0]:
            for control in [-5.0, 0.0, 5.0]:
                rows.append(
                    {
                        "geometry_id": geom_id,
                        "c1_m": 1.5 + 0.01 * geom_idx,
                        "b_total_m": 1.6 + 0.02 * geom_idx,
                        "sw1_deg": 40.0 + geom_idx,
                        "alpha_deg": alpha,
                        "velocity_mps": 24.0 + geom_idx,
                        "altitude_m": 1000.0 + 100.0 * geom_idx,
                        "control_input_deg": control,
                        "cl": 0.1 * alpha + 0.01 * geom_idx + 0.002 * control,
                        "cd": 0.02 + 0.001 * (alpha**2) + 0.0002 * (control**2) + 0.0001 * geom_idx,
                        "cm": -0.05 * alpha + 0.005 * geom_idx - 0.01 * control,
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
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest, indent=2), encoding="utf-8")
    return dataset_root


def test_ml_train_cli_accepts_feature_set(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "train_feature_set_cli"

    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_physics_v1",
            "--targets",
            "cl,cd,cm",
            "--model-type",
            "linear_regression",
            "--split-method",
            "grouped",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "[AERIS] ML training completed" in result.output
    train_config = json.loads((output_dir / "train_config.json").read_text(encoding="utf-8"))
    assert train_config["feature_set_name"] == "bwb_control_physics_v1"
    assert "alpha_deg_sq" in train_config["feature_columns"]


def test_ml_compare_cli_accepts_feature_set(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "compare_feature_set_cli"

    result = runner.invoke(
        app,
        [
            "ml",
            "compare",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_raw",
            "--targets",
            "cl,cd,cm",
            "--models",
            "linear_regression,ridge",
            "--split-method",
            "grouped",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "[AERIS] ML model comparison completed" in result.output
    summary = json.loads((output_dir / "comparison_summary.json").read_text(encoding="utf-8"))
    assert summary["feature_set_name"] == "bwb_control_raw"


def test_ml_tune_cli_accepts_feature_set(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "tune_feature_set_cli"
    param_space = tmp_path / "ridge_space.json"
    param_space.write_text('{"alpha": [0.1, 1.0]}', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "ml",
            "tune",
            "--backend",
            "aeris",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_raw",
            "--targets",
            "cl,cd,cm",
            "--model-type",
            "ridge",
            "--param-space-json",
            str(param_space),
            "--split-method",
            "grouped",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "[AERIS] ML tuning completed" in result.output
    summary = json.loads((output_dir / "tuning_summary.json").read_text(encoding="utf-8"))
    assert summary["feature_set_name"] == "bwb_control_raw"


def test_ml_train_cli_rejects_mixed_feature_inputs(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)

    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--dataset",
            str(dataset),
            "--features",
            "c1_m,b_total_m",
            "--feature-set",
            "bwb_control_raw",
            "--targets",
            "cl,cd,cm",
        ],
    )

    assert result.exit_code != 0
    normalized_output = result.output.replace("\n", " ")
    assert "Use only one" in normalized_output
    assert "--features" in normalized_output
    assert "--feature-preset" in normalized_output
    assert "--feature-set" in normalized_output


def test_ml_compare_seeds_cli_records_feature_set(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "compare_seeds_feature_set_cli"

    result = runner.invoke(
        app,
        [
            "ml",
            "compare-seeds",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_raw",
            "--targets",
            "cl,cd,cm",
            "--models",
            "linear_regression,ridge",
            "--seeds",
            "101,202",
            "--split-method",
            "grouped",
            "--group-column",
            "geometry_id",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads((output_dir / "comparison_seed_stability_summary.json").read_text())
    assert summary["feature_set_name"] == "bwb_control_raw"
    assert summary["feature_columns"] == [
        "c1_m",
        "b_total_m",
        "sw1_deg",
        "alpha_deg",
        "velocity_mps",
        "altitude_m",
        "control_input_deg",
    ]

