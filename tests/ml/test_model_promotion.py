from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.model_promotion import inspect_model_run, promote_model_run, require_promoted_model


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_model_run(tmp_path: Path) -> Path:
    run = tmp_path / "model_run"
    (run / "models").mkdir(parents=True)
    (run / "diagnostics").mkdir()
    (run / "models" / "model.pkl").write_bytes(b"not-a-real-model-but-hashable")
    _write_json(run / "train_config.json", {
        "dataset_path": str(tmp_path / "dataset"),
        "feature_columns": ["c1_m", "alpha_deg"],
        "target_columns": ["cl", "cd"],
        "model_type": "extra_trees",
        "split_method": "grouped",
        "group_column": "geometry_id",
        "random_seed": 123,
        "allow_forced": False,
        "model_params": {"n_estimators": 10},
    })
    _write_json(run / "metrics.json", {
        "val": {"overall": {"rmse_mean": 0.01, "mae_mean": 0.01, "r2_mean": 0.99}},
        "test": {"overall": {"rmse_mean": 0.02, "mae_mean": 0.02, "r2_mean": 0.98}},
    })
    _write_json(run / "ml_run_manifest.json", {
        "dataset": {
            "promotion_context": {
                "promotion_ready_at_time_of_promotion": True,
                "promotion_forced": False,
                "promotion_blockers": [],
            },
            "fingerprints": {"curated_csv": {"sha256": "abc"}},
        },
        "split": {"method": "grouped"},
    })
    pd.DataFrame({
        "geometry_id": ["g1", "g2", "g3"],
        "c1_m": [1.0, 1.2, 1.4],
        "alpha_deg": [0.0, 2.0, 4.0],
        "cl": [0.1, 0.2, 0.3],
        "cd": [0.01, 0.02, 0.03],
    }).to_csv(run / "train_rows.csv", index=False)
    return run


def test_promote_and_require_model_run(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    result = promote_model_run(
        model_run_dir=run,
        max_val_rmse_mean=0.1,
        max_test_rmse_mean=0.1,
        min_test_r2_mean=0.9,
    )
    assert result.passed is True
    assert result.manifest_path.exists()
    assert result.model_card_path.exists()
    assert result.training_envelope_path is not None
    assert result.training_envelope_path.exists()
    manifest = require_promoted_model(run)
    assert manifest["status"] == "approved"
    info = inspect_model_run(run)
    assert info["promotion"]["status"] == "approved"
    assert info["model_type"] == "extra_trees"


def test_promotion_threshold_blocks_model(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    result = promote_model_run(model_run_dir=run, max_test_rmse_mean=0.001)
    assert result.passed is False
    assert result.manifest["status"] == "rejected"
    with pytest.raises(ValueError):
        require_promoted_model(run)
