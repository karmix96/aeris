from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from aeris.ml.model_promotion import promote_model_run
from aeris.ml.promotion_gates import load_promotion_gate_config, suggest_promotion_gates


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _model_run(tmp_path: Path) -> Path:
    run = tmp_path / "model_run"
    (run / "models").mkdir(parents=True)
    (run / "diagnostics").mkdir()
    (run / "models" / "model.pkl").write_bytes(b"hashable-model")
    _write_json(
        run / "train_config.json",
        {
            "dataset_path": str(tmp_path / "dataset"),
            "feature_columns": ["c1_m", "alpha_deg"],
            "target_columns": ["cl", "cd", "cm"],
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
            "val": {"overall": {"rmse_mean": 0.02, "mae_mean": 0.015, "r2_mean": 0.95}},
            "test": {
                "overall": {"rmse_mean": 0.035, "mae_mean": 0.02, "r2_mean": 0.91},
                "per_target": {
                    "cl": {"rmse": 0.02, "mae": 0.015, "r2": 0.96, "max_abs_error": 0.04, "error_p95": 0.035},
                    "cd": {"rmse": 0.002, "mae": 0.0015, "r2": 0.93, "max_abs_error": 0.004, "error_p95": 0.0035},
                    "cm": {"rmse": 0.08, "mae": 0.06, "r2": 0.75, "max_abs_error": 0.12, "error_p95": 0.11},
                },
            },
        },
    )
    _write_json(
        run / "ml_run_manifest.json",
        {
            "dataset": {
                "promotion_context": {
                    "promotion_ready_at_time_of_promotion": True,
                    "promotion_forced": False,
                    "promotion_blockers": [],
                },
                "fingerprints": {"curated_csv": {"sha256": "abc"}},
            },
            "split": {"method": "grouped"},
        },
    )
    rows = pd.DataFrame(
        {
            "geometry_id": ["g1", "g2", "g3", "g4"],
            "c1_m": [1.0, 1.1, 1.2, 1.3],
            "alpha_deg": [0.0, 2.0, 4.0, 6.0],
            "cl": [0.1, 0.2, 0.4, 0.6],
            "cd": [0.01, 0.013, 0.018, 0.025],
            "cm": [-0.1, -0.2, -0.35, -0.55],
        }
    )
    rows.to_csv(run / "test_rows.csv", index=False)
    rows.to_csv(run / "train_rows.csv", index=False)
    return run


def test_suggest_promotion_gates_writes_generic_target_template(tmp_path: Path) -> None:
    run = _model_run(tmp_path)
    result = suggest_promotion_gates(model_run_dir=run, output_dir=tmp_path / "suggestions", profile="normal")

    assert result.report_path.exists()
    assert result.template_path.exists()
    assert set(result.template["targets"]) == {"cl", "cd", "cm"}
    assert result.template["targets"]["cl"]["required"] is True
    assert "max_nrmse_iqr" in result.template["targets"]["cd"]

    loaded = load_promotion_gate_config(result.template_path)
    assert loaded["schema_version"] == "aeris.model_promotion_gate_config.v1"
    assert loaded["targets"]["cm"]["min_r2"] == 0.9
    assert "target_suggestions" in result.report


def test_promote_model_uses_per_target_gate_config(tmp_path: Path) -> None:
    run = _model_run(tmp_path)
    gate_config = {
        "schema_version": "aeris.model_promotion_gate_config.v1",
        "global": {"max_test_rmse_mean": 0.1, "min_test_r2_mean": 0.5},
        "targets": {
            "cl": {"required": True, "max_rmse": 0.05, "min_r2": 0.9},
            "cm": {"required": True, "max_rmse": 0.03, "min_r2": 0.9},
        },
    }
    gate_path = tmp_path / "promotion_gates.yaml"
    gate_path.write_text(yaml.safe_dump(gate_config, sort_keys=False), encoding="utf-8")

    rejected = promote_model_run(model_run_dir=run, gate_config_path=gate_path)
    assert rejected.passed is False
    assert any("target 'cm'" in blocker for blocker in rejected.blockers)
    assert rejected.manifest["promotion_gate_config"]["path"] == str(gate_path.resolve())

    gate_config["targets"]["cm"] = {"required": True, "max_rmse": 0.2, "min_r2": 0.7}
    gate_path.write_text(yaml.safe_dump(gate_config, sort_keys=False), encoding="utf-8")
    approved = promote_model_run(model_run_dir=run, gate_config_path=gate_path)
    assert approved.passed is True
    assert approved.manifest["promotion_gate_config"]["evaluation"]["passed"] is True
