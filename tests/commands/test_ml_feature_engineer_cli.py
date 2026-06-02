from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app


runner = CliRunner()


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "feature_engineer_cli_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    control_by_alpha = {-2.0: -5.0, 0.0: 0.0, 4.0: 5.0}
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4"]):
        for alpha in [-2.0, 0.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "case_id": f"{geom_id}_a{alpha:g}",
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.02 * geom_idx,
                    "sw1_deg": 40.0 + geom_idx,
                    "alpha_deg": alpha,
                    "velocity_mps": 24.0 + geom_idx,
                    "altitude_m": 1000.0 + 100.0 * geom_idx,
                    "control_input_deg": control_by_alpha[alpha],
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha**2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )

    curated_csv = dataset_root / "curated_aero_dataset.csv"
    rejected_csv = dataset_root / "rejected_aero_rows.csv"
    pd.DataFrame(rows).to_csv(curated_csv, index=False)
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


def test_ml_feature_engineer_cli_materializes_physics_feature_set(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "engineered"

    result = runner.invoke(
        app,
        [
            "ml",
            "feature-engineer",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_physics_v1",
            "--targets",
            "cl,cd,cm",
            "--output-dir",
            str(output_dir),
            "--only-feature-columns",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "[AERIS] ML feature-set materialization completed" in result.stdout
    assert "feature_set: bwb_control_physics_v1" in result.stdout
    assert (output_dir / "engineered_dataset.csv").exists()
    assert (output_dir / "feature_engineering_manifest.json").exists()
    assert (output_dir / "feature_schema.json").exists()
    assert (output_dir / "feature_materialization_report.json").exists()

    df = pd.read_csv(output_dir / "engineered_dataset.csv")
    assert "alpha_deg_sq" in df.columns
    assert "re_number" in df.columns
    assert "case_id" not in df.columns


def test_ml_feature_engineer_cli_json_output(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "engineered_json"

    result = runner.invoke(
        app,
        [
            "ml",
            "feature-engineer",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_raw",
            "--targets",
            "cl,cd,cm",
            "--output-dir",
            str(output_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["feature_set"]["name"] == "bwb_control_raw"
    assert payload["n_rows"] == 12
    assert (output_dir / "engineered_dataset.csv").exists()


def test_ml_feature_engineer_cli_fails_cleanly_for_unknown_feature_set(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)

    result = runner.invoke(
        app,
        [
            "ml",
            "feature-engineer",
            "--dataset",
            str(dataset),
            "--feature-set",
            "does_not_exist",
            "--targets",
            "cl,cd,cm",
        ],
    )

    assert result.exit_code != 0
    assert "Unknown feature set" in result.output
