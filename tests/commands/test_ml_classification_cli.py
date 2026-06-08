from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _write_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(6):
        for alpha in (0.0, 2.0):
            red = int((i + alpha) >= 4)
            rows.append(
                {
                    "geometry_id": f"geom_{i:05d}",
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": 0.0,
                    "c1_m": 1.2 + 0.1 * i,
                    "b_total_m": 1.4 + 0.05 * i,
                    "sw1_deg": -30.0 - i,
                    "longitudinal_basic_flyable_int": 1 - red,
                    "red_flag_int": red,
                }
            )
    curated = root / "curated_aero_dataset.csv"
    pd.DataFrame(rows).to_csv(curated, index=False)
    (root / "curation_report.json").write_text(json.dumps({"promotion_ready": True}), encoding="utf-8")
    (root / "final_run_summary.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (root / "promotion_manifest.json").write_text(
        json.dumps(
            {
                "promotion_forced": False,
                "promotion_ready_at_time_of_promotion": True,
                "promotion_blockers": [],
                "artifacts": {"curated_aero_dataset_csv": str(curated.resolve())},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


def test_ml_classify_help_exposes_command() -> None:
    result = runner.invoke(app, ["ml", "classify", "--help"])
    assert result.exit_code == 0
    assert "--classifier-type" in result.stdout
    assert "classifier-type" in result.stdout


def test_ml_compare_classifiers_help_exposes_command() -> None:
    result = runner.invoke(app, ["ml", "compare-classifiers", "--help"])
    assert result.exit_code == 0
    assert "--classifiers" in result.stdout
    assert "classifiers" in result.stdout


def test_ml_classify_cli_smoke(tmp_path: Path) -> None:
    ds = _write_dataset(tmp_path / "ds")
    out = tmp_path / "classify_run"
    result = runner.invoke(
        app,
        [
            "ml",
            "classify",
            "--dataset",
            str(ds),
            "--features",
            "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg",
            "--targets",
            "longitudinal_basic_flyable_int,red_flag_int",
            "--classifier-type",
            "logistic_regression",
            "--split-method",
            "grouped",
            "--group-column",
            "geometry_id",
            "--output-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "ML classification completed" in result.stdout
    assert (out / "classification_summary.json").exists()


def test_ml_compare_classifiers_cli_smoke(tmp_path: Path) -> None:
    ds = _write_dataset(tmp_path / "ds")
    out = tmp_path / "compare_run"
    result = runner.invoke(
        app,
        [
            "ml",
            "compare-classifiers",
            "--dataset",
            str(ds),
            "--features",
            "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg",
            "--targets",
            "longitudinal_basic_flyable_int,red_flag_int",
            "--classifiers",
            "logistic_regression,random_forest_classifier",
            "--split-method",
            "grouped",
            "--group-column",
            "geometry_id",
            "--output-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "ML classifier comparison completed" in result.stdout
    assert (out / "classifier_comparison_summary.json").exists()
