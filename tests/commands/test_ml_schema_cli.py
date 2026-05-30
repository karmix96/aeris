from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "ml_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4"]):
        for alpha in [0.0, 2.0, 4.0]:
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
                    "cd": 0.02 + 0.001 * alpha**2,
                    "cm": -0.05 * alpha,
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
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest), encoding="utf-8")
    return dataset_root


def test_ml_feature_presets_cli_lists_presets() -> None:
    result = runner.invoke(app, ["ml", "feature-presets"])

    assert result.exit_code == 0, result.stdout
    assert "ML feature presets" in result.stdout
    assert "bwb_control" in result.stdout


def test_ml_validate_schema_cli_with_feature_preset(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)

    result = runner.invoke(
        app,
        [
            "ml",
            "validate-schema",
            "--dataset",
            str(dataset_root),
            "--feature-preset",
            "bwb_control",
            "--targets",
            "cl,cd,cm",
            "--group-column",
            "geometry_id",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "ML schema validation" in result.stdout
    assert "passed: True" in result.stdout


def test_ml_train_cli_accepts_feature_preset(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "train_with_preset"

    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--dataset",
            str(dataset_root),
            "--feature-preset",
            "bwb_control",
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

    assert result.exit_code == 0, result.stdout
    assert "ML training completed" in result.stdout
    assert (output_dir / "metrics.json").exists()
