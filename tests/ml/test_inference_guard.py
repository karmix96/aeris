from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.inference_guard import check_inference_inputs
from aeris.ml.model_promotion import promote_model_run
from aeris.ml.train import train_baseline_model

FEATURE_COLUMNS = [
    "c1_m",
    "b_total_m",
    "sw1_deg",
    "alpha_deg",
    "velocity_mps",
    "altitude_m",
    "control_input_deg",
]
TARGET_COLUMNS = ["cl", "cd", "cm"]




def _inject_test_dataset_promotion_context(model_run_dir: Path, dataset_root: Path) -> None:
    """Give synthetic test model runs the dataset provenance required by model promotion."""
    import json
    from datetime import datetime, timezone

    manifest_path = model_run_dir / "ml_run_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    dataset_block = data.setdefault("dataset", {})
    dataset_block["promotion_context"] = {
        "schema_version": "aeris.test_dataset_promotion_context.v1",
        "status": "approved",
        "dataset_root": str(dataset_root),
        "promotion_manifest_path": str(dataset_root / "promotion_manifest.json"),
        "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
        "promotion_ready_at_time_of_promotion": True,
        "promotion_forced": False,
        "promotion_blockers": [],
        "created_for_test_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    data["dataset"] = dataset_block

    manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


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
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest, indent=2), encoding="utf-8")
    return dataset_root


def _train_and_promote(tmp_path: Path) -> tuple[Path, Path]:
    dataset_root = _build_dataset(tmp_path)
    model_run_dir = tmp_path / "model_run"
    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="extra_trees",
        split_method="grouped",
        random_seed=123,
        output_dir=model_run_dir,
    )
    _inject_test_dataset_promotion_context(model_run_dir, dataset_root)
    result = promote_model_run(
        model_run_dir=model_run_dir,
        max_test_rmse_mean=0.1,
        min_test_r2_mean=0.9,
    )
    assert result.passed is True
    return dataset_root, model_run_dir


def test_inference_guard_passes_for_in_envelope_inputs(tmp_path: Path) -> None:
    _, model_run_dir = _train_and_promote(tmp_path)
    input_csv = model_run_dir / "train_rows.csv"
    result = check_inference_inputs(model_run_dir=model_run_dir, input_csv=input_csv)
    assert result.passed is True
    assert result.report_path.exists()
    assert result.errors == []


def test_inference_guard_detects_out_of_envelope_feature(tmp_path: Path) -> None:
    _, model_run_dir = _train_and_promote(tmp_path)
    input_csv = tmp_path / "ood.csv"
    df = pd.read_csv(model_run_dir / "train_rows.csv")
    df.loc[:, "alpha_deg"] = 10.0
    df.to_csv(input_csv, index=False)

    result = check_inference_inputs(model_run_dir=model_run_dir, input_csv=input_csv)
    assert result.passed is False
    assert any("outside training envelope" in msg for msg in result.errors)

    with pytest.raises(ValueError):
        check_inference_inputs(
            model_run_dir=model_run_dir,
            input_csv=input_csv,
            fail_on_violations=True,
        )
