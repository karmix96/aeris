from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_model_run(tmp_path: Path) -> Path:
    run = tmp_path / "model_run_cli"
    (run / "models").mkdir(parents=True)
    (run / "diagnostics").mkdir()
    (run / "models" / "model.pkl").write_bytes(b"model")
    _write_json(run / "train_config.json", {
        "dataset_path": str(tmp_path / "dataset"),
        "feature_columns": ["c1_m", "alpha_deg"],
        "target_columns": ["cl"],
        "model_type": "extra_trees",
        "split_method": "grouped",
        "group_column": "geometry_id",
        "random_seed": 123,
        "model_params": {},
    })
    _write_json(run / "metrics.json", {
        "val": {"overall": {"rmse_mean": 0.01, "r2_mean": 0.99}},
        "test": {"overall": {"rmse_mean": 0.02, "r2_mean": 0.98}},
    })
    _write_json(run / "ml_run_manifest.json", {
        "dataset": {"promotion_context": {
            "promotion_ready_at_time_of_promotion": True,
            "promotion_forced": False,
            "promotion_blockers": [],
        }},
        "split": {"method": "grouped"},
    })
    pd.DataFrame({
        "geometry_id": ["g1", "g2"],
        "c1_m": [1.0, 2.0],
        "alpha_deg": [0.0, 2.0],
        "cl": [0.1, 0.2],
    }).to_csv(run / "train_rows.csv", index=False)
    return run


def test_promote_inspect_require_model_cli(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    promote = runner.invoke(app, [
        "ml", "promote-model",
        "--model-run-dir", str(run),
        "--max-test-rmse-mean", "0.1",
        "--min-test-r2-mean", "0.9",
    ])
    assert promote.exit_code == 0, promote.stdout
    assert "Model promotion completed" in promote.stdout
    assert "status: approved" in promote.stdout
    require = runner.invoke(app, ["ml", "require-promoted-model", "--model-run-dir", str(run)])
    assert require.exit_code == 0, require.stdout
    assert "Promoted model gate check" in require.stdout
    inspect = runner.invoke(app, ["ml", "inspect-model", "--model-run-dir", str(run)])
    assert inspect.exit_code == 0, inspect.stdout
    assert "model_type: extra_trees" in inspect.stdout
    assert "promotion_status: approved" in inspect.stdout
