from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "ml_feature_set_cli_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4"]):
        for alpha, control in [(-2.0, -5.0), (0.0, 0.0), (4.0, 5.0)]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.01 * geom_idx,
                    "sw1_deg": 40.0 + geom_idx,
                    "alpha_deg": alpha,
                    "velocity_mps": 25.0 + geom_idx,
                    "altitude_m": 1200.0 + 50.0 * geom_idx,
                    "control_input_deg": control,
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha ** 2),
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )

    curated_csv = dataset_root / "curated_aero_dataset.csv"
    pd.DataFrame(rows).to_csv(curated_csv, index=False)
    rejected_csv = dataset_root / "rejected_aero_rows.csv"
    rejected_csv.write_text("", encoding="utf-8")
    (dataset_root / "promotion_manifest.json").write_text(
        json.dumps(
            {
                "dataset_root": str(dataset_root),
                "promotion_forced": False,
                "promotion_ready_at_time_of_promotion": True,
                "promotion_blockers": [],
                "artifacts": {
                    "curated_aero_dataset_csv": str(curated_csv),
                    "rejected_aero_rows_csv": str(rejected_csv),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return dataset_root


def test_ml_feature_sets_cli_lists_registry() -> None:
    result = runner.invoke(app, ["ml", "feature-sets"])
    assert result.exit_code == 0, result.stdout
    assert "[AERIS] ML feature sets" in result.stdout
    assert "bwb_control_raw" in result.stdout
    assert "bwb_control_physics_v1" in result.stdout


def test_ml_describe_feature_set_cli() -> None:
    result = runner.invoke(
        app,
        ["ml", "describe-feature-set", "--feature-set", "bwb_control_raw"],
    )
    assert result.exit_code == 0, result.stdout
    assert "[AERIS] ML feature set" in result.stdout
    assert "raw_features:" in result.stdout
    assert "engineered_features: none" in result.stdout


def test_ml_describe_feature_set_cli_json() -> None:
    result = runner.invoke(
        app,
        ["ml", "describe-feature-set", "--feature-set", "bwb_control_physics_v1", "--json"],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["name"] == "bwb_control_physics_v1"
    assert "alpha_sq" in payload["transforms"]


def test_ml_validate_feature_set_cli_raw(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    result = runner.invoke(
        app,
        [
            "ml",
            "validate-feature-set",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_raw",
            "--targets",
            "cl,cd,cm",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "[AERIS] ML feature-set validation" in result.stdout
    assert "feature_set: bwb_control_raw" in result.stdout
    assert "passed: True" in result.stdout
    assert "engineered_features: none" in result.stdout


def test_ml_validate_feature_set_cli_physics(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    result = runner.invoke(
        app,
        [
            "ml",
            "validate-feature-set",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_physics_v1",
            "--targets",
            "cl,cd,cm",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "feature_set: bwb_control_physics_v1" in result.stdout
    assert "passed: True" in result.stdout
    assert "alpha_deg_sq" in result.stdout
    assert "re_number" in result.stdout
