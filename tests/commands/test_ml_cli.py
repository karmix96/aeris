from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


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


def test_ml_train_cli_linear(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "cli_linear"

    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--dataset",
            str(dataset_root),
            "--features",
            "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg",
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
    assert "[AERIS] ML training completed" in result.stdout
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "coefficients.json").exists()


def test_ml_train_cli_gradient_boosting(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "cli_gb"

    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--dataset",
            str(dataset_root),
            "--features",
            "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg",
            "--targets",
            "cl,cd,cm",
            "--model-type",
            "gradient_boosting",
            "--split-method",
            "grouped",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "[AERIS] ML training completed" in result.stdout
    assert "gradient_boosting" in result.stdout
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "feature_importances.json").exists()


def test_ml_train_cli_from_config(tmp_path: Path) -> None:
    import yaml

    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "cli_config"
    config_path = tmp_path / "ml_train.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "ml": {
                    "dataset": str(dataset_root),
                    "features": "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg",
                    "targets": "cl,cd,cm",
                    "split": {"method": "grouped", "group_column": "geometry_id", "random_seed": 123},
                    "model": {"type": "random_forest", "params": {"n_estimators": 7}},
                    "output_dir": str(output_dir),
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["ml", "train", "--config", str(config_path)])

    assert result.exit_code == 0, result.stdout
    assert "[AERIS] ML training completed" in result.stdout
    assert "random_forest" in result.stdout
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "models" / "model.pkl").exists()
    assert (output_dir / "ml_run_manifest.json").exists()

    train_config = json.loads((output_dir / "train_config.json").read_text(encoding="utf-8"))
    assert train_config["source_config_path"] == str(config_path.resolve())
    assert train_config["model_params"]["n_estimators"] == 7


def test_ml_train_cli_model_params_json(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "cli_params"
    params_json = tmp_path / "rf_params.json"
    params_json.write_text('{"n_estimators": 5, "max_depth": 2}', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--dataset", str(dataset_root),
            "--features", "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg",
            "--targets", "cl,cd,cm",
            "--model-type", "random_forest",
            "--model-params-json", str(params_json),
            "--split-method", "grouped",
            "--output-dir", str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    train_config = json.loads((output_dir / "train_config.json").read_text(encoding="utf-8"))
    assert train_config["model_params"]["n_estimators"] == 5
    assert train_config["model_params"]["max_depth"] == 2


def test_ml_eda_cli_writes_report(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "eda_cli"

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = runner.invoke(
            app,
            [
                "ml",
                "eda",
                "--dataset", str(dataset_root),
                "--feature-preset", "bwb_control",
                "--targets", "cl,cd,cm",
                "--output-dir", str(output_dir),
                "--no-plots",
            ],
        )

    assert result.exit_code == 0, result.stdout
    assert "[AERIS] ML EDA completed" in result.stdout
    assert (output_dir / "eda_report.json").exists()
    assert (output_dir / "eda_summary.md").exists()
    report = json.loads((output_dir / "eda_report.json").read_text(encoding="utf-8"))
    assert report["shape"]["n_rows"] > 0
    assert report["metadata"]["feature_columns"][-1] == "control_input_deg"
    skipped = {item["column"] for item in report["correlation"].get("skipped_columns", [])}
    assert "velocity_mps" in skipped
    assert "altitude_m" in skipped


def test_ml_eda_cli_accepts_feature_set(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "eda_cli_feature_set"

    result = runner.invoke(
        app,
        [
            "ml",
            "eda",
            "--dataset", str(dataset_root),
            "--feature-set", "bwb_control_physics_v1",
            "--targets", "cl,cd,cm",
            "--output-dir", str(output_dir),
            "--no-plots",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "feature_set_applied: True" in result.stdout
    report = json.loads((output_dir / "eda_report.json").read_text(encoding="utf-8"))
    assert report["metadata"]["feature_set_name"] == "bwb_control_physics_v1"
    assert report["metadata"]["feature_set_applied"] is True
    assert "alpha_deg_sq" in report["metadata"]["engineered_columns"]
    assert "re_number" in report["metadata"]["final_feature_columns"]
    assert "alpha_deg_sq" in report["feature_stats"]
    assert report["metadata"]["row_count"] == report["shape"]["n_rows"]
    assert report["metadata"]["column_count"] == report["shape"]["n_columns"]


def test_ml_eda_cli_rejects_multiple_feature_selectors(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "eda_cli_bad_selectors"

    result = runner.invoke(
        app,
        [
            "ml",
            "eda",
            "--dataset", str(dataset_root),
            "--feature-preset", "bwb_control",
            "--feature-set", "bwb_control_physics_v1",
            "--targets", "cl,cd,cm",
            "--output-dir", str(output_dir),
            "--no-plots",
        ],
    )

    assert result.exit_code != 0
    combined_output = "\n".join(
        part
        for part in [
            result.stdout or "",
            getattr(result, "stderr", "") or "",
            str(result.exception or ""),
        ]
        if part
    )
    # Typer/Rich may wrap long option strings inside the error box, so avoid
    # asserting one exact unwrapped line. The command contract is that EDA
    # rejects multiple feature selectors with a clear selector-conflict error.
    assert "Use only one of" in combined_output
    assert "--features" in combined_output
    assert "--feature-preset" in combined_output
    assert "--feature" in combined_output


def test_ml_inspect_model_help_has_json_flag():
    result = runner.invoke(app, ["ml", "inspect-model", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.stdout


def test_ml_require_promoted_model_help_has_json_flag():
    result = runner.invoke(app, ["ml", "require-promoted-model", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.stdout


def test_ml_tune_help_has_workflow_flag():
    result = runner.invoke(app, ["ml", "tune", "--help"])
    assert result.exit_code == 0
    assert "--workflow" in result.stdout


def test_ml_build_delta_dataset_artifacts_not_getattr():
    import ast, pathlib
    src = pathlib.Path("src/aeris/commands/ml.py").read_text(encoding="utf-8")
    fn_start = src.find("def ml_build_delta_dataset(")
    fn_end   = src.find("\n@ml_app", fn_start + 1)
    fn_body  = src[fn_start:fn_end]
    assert "getattr(result" not in fn_body, (
        "ml_build_delta_dataset must not use getattr on result — use result.attribute directly"
    )

