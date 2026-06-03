from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _model_run(tmp_path: Path) -> Path:
    run = tmp_path / "model_run_cli_gates"
    (run / "models").mkdir(parents=True)
    (run / "diagnostics").mkdir()
    (run / "models" / "model.pkl").write_bytes(b"model")
    _write_json(
        run / "train_config.json",
        {
            "dataset_path": str(tmp_path / "dataset"),
            "feature_columns": ["c1_m", "alpha_deg"],
            "target_columns": ["cl", "cd"],
            "model_type": "extra_trees",
            "split_method": "grouped",
            "group_column": "geometry_id",
            "random_seed": 123,
            "model_params": {},
        },
    )
    _write_json(
        run / "metrics.json",
        {
            "val": {"overall": {"rmse_mean": 0.01, "r2_mean": 0.99}},
            "test": {
                "overall": {"rmse_mean": 0.02, "r2_mean": 0.98},
                "per_target": {
                    "cl": {"rmse": 0.02, "mae": 0.01, "r2": 0.98, "max_abs_error": 0.03, "error_p95": 0.025},
                    "cd": {"rmse": 0.002, "mae": 0.001, "r2": 0.95, "max_abs_error": 0.003, "error_p95": 0.0025},
                },
            },
        },
    )
    _write_json(
        run / "ml_run_manifest.json",
        {
            "dataset": {"promotion_context": {"promotion_ready_at_time_of_promotion": True, "promotion_forced": False, "promotion_blockers": []}},
            "split": {"method": "grouped"},
        },
    )
    rows = pd.DataFrame(
        {
            "geometry_id": ["g1", "g2", "g3"],
            "c1_m": [1.0, 1.2, 1.4],
            "alpha_deg": [0.0, 2.0, 4.0],
            "cl": [0.1, 0.3, 0.5],
            "cd": [0.01, 0.02, 0.04],
        }
    )
    rows.to_csv(run / "test_rows.csv", index=False)
    rows.to_csv(run / "train_rows.csv", index=False)
    return run


def test_suggest_promotion_gates_cli(tmp_path: Path) -> None:
    run = _model_run(tmp_path)
    output_dir = tmp_path / "suggested_gates"
    result = runner.invoke(
        app,
        [
            "ml",
            "suggest-promotion-gates",
            "--model-run-dir", str(run),
            "--output-dir", str(output_dir),
            "--profile", "normal",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "promotion gate suggestions completed" in result.stdout
    assert (output_dir / "promotion_gate_suggestions.json").exists()
    assert (output_dir / "promotion_gates_template.yaml").exists()


def test_promote_model_cli_accepts_gate_config(tmp_path: Path) -> None:
    run = _model_run(tmp_path)
    gate_path = tmp_path / "promotion_gates.yaml"
    gate_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "aeris.model_promotion_gate_config.v1",
                "global": {"max_test_rmse_mean": 0.1, "min_test_r2_mean": 0.9},
                "targets": {
                    "cl": {"required": True, "max_rmse": 0.05, "min_r2": 0.9},
                    "cd": {"required": True, "max_rmse": 0.01, "min_r2": 0.9},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "ml", "promote-model",
            "--model-run-dir", str(run),
            "--gate-config", str(gate_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "status: approved" in result.stdout
    manifest = json.loads((run / "model_promotion_manifest.json").read_text(encoding="utf-8"))
    assert manifest["promotion_gate_config"]["path"] == str(gate_path.resolve())
    assert manifest["promotion_gate_config"]["evaluation"]["passed"] is True
