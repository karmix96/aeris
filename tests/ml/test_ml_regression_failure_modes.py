from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.model_promotion import promote_model_run, require_promoted_model


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_model_run(
    tmp_path: Path,
    *,
    diagnostics: bool = True,
    promotion_context: dict | None = None,
) -> Path:
    run = tmp_path / "model_run"
    (run / "models").mkdir(parents=True)
    if diagnostics:
        (run / "diagnostics").mkdir()
    (run / "models" / "model.pkl").write_bytes(b"hashable-model-bytes")

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
            "model_params": {"n_estimators": 10},
        },
    )
    _write_json(
        run / "metrics.json",
        {
            "val": {"overall": {"rmse_mean": 0.01, "mae_mean": 0.01, "r2_mean": 0.99}},
            "test": {"overall": {"rmse_mean": 0.02, "mae_mean": 0.02, "r2_mean": 0.98}},
        },
    )

    if promotion_context is None:
        promotion_context = {
            "promotion_ready_at_time_of_promotion": True,
            "promotion_forced": False,
            "promotion_blockers": [],
        }

    _write_json(
        run / "ml_run_manifest.json",
        {
            "dataset": {
                "promotion_context": promotion_context,
                "fingerprints": {"curated_csv": {"sha256": "abc"}},
            },
            "split": {"method": "grouped", "group_column": "geometry_id"},
        },
    )
    pd.DataFrame(
        {
            "geometry_id": ["g1", "g2", "g3"],
            "c1_m": [1.0, 1.2, 1.4],
            "alpha_deg": [0.0, 2.0, 4.0],
            "cl": [0.1, 0.2, 0.3],
            "cd": [0.01, 0.02, 0.03],
        }
    ).to_csv(run / "train_rows.csv", index=False)
    return run


def test_model_promotion_blocks_missing_diagnostics_by_default(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path, diagnostics=False)
    result = promote_model_run(model_run_dir=run, max_test_rmse_mean=0.1, min_test_r2_mean=0.9)

    assert result.passed is False
    assert result.manifest["status"] == "rejected"
    assert any("diagnostics" in blocker for blocker in result.blockers)



def test_model_promotion_blocks_force_promoted_dataset_without_override(tmp_path: Path) -> None:
    run = _minimal_model_run(
        tmp_path,
        promotion_context={
            "promotion_ready_at_time_of_promotion": True,
            "promotion_forced": True,
            "promotion_blockers": [],
        },
    )

    rejected = promote_model_run(model_run_dir=run, max_test_rmse_mean=0.1, min_test_r2_mean=0.9)
    assert rejected.passed is False
    assert any("force-promoted" in blocker for blocker in rejected.blockers)

    approved = promote_model_run(
        model_run_dir=run,
        max_test_rmse_mean=0.1,
        min_test_r2_mean=0.9,
        allow_forced_dataset=True,
    )
    assert approved.passed is True



def test_model_promotion_blocks_missing_dataset_promotion_context(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    manifest_path = run / "ml_run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset"].pop("promotion_context")
    _write_json(manifest_path, manifest)

    result = promote_model_run(model_run_dir=run, max_test_rmse_mean=0.1, min_test_r2_mean=0.9)

    assert result.passed is False
    assert any("promotion_context" in blocker for blocker in result.blockers)



def test_require_promoted_model_detects_artifact_hash_mismatch(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    result = promote_model_run(model_run_dir=run, max_test_rmse_mean=0.1, min_test_r2_mean=0.9)
    assert result.passed is True

    (run / "models" / "model.pkl").write_bytes(b"tampered-model-bytes")

    with pytest.raises(ValueError, match="hashes"):
        require_promoted_model(run)



def test_model_promotion_requires_model_artifact(tmp_path: Path) -> None:
    run = _minimal_model_run(tmp_path)
    (run / "models" / "model.pkl").unlink()

    with pytest.raises(FileNotFoundError):
        promote_model_run(model_run_dir=run)
