from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from aeris.ml.model_promotion import promote_model_run
from aeris.ml.model_registry import build_model, list_model_types
from aeris.ml.quality import predict_with_confidence
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
    dataset_root = tmp_path / "neural_ml_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)
    rows = []
    geom_ids = [f"g{i:02d}" for i in range(12)]
    for geom_idx, geom_id in enumerate(geom_ids):
        for alpha in [-2.0, 0.0, 2.0, 4.0, 6.0]:
            for control in [-5.0, 0.0, 5.0]:
                c1 = 1.45 + 0.015 * geom_idx
                span = 1.55 + 0.012 * geom_idx
                sweep = 35.0 + 0.3 * geom_idx
                rows.append(
                    {
                        "geometry_id": geom_id,
                        "c1_m": c1,
                        "b_total_m": span,
                        "sw1_deg": sweep,
                        "alpha_deg": alpha,
                        "velocity_mps": 24.0 + 0.2 * geom_idx,
                        "altitude_m": 1000.0 + 10.0 * geom_idx,
                        "control_input_deg": control,
                        "cl": 0.08 * alpha + 0.006 * control + 0.015 * (span - 1.55),
                        "cd": 0.025 + 0.0012 * alpha**2 + 0.00012 * control**2 + 0.0002 * geom_idx,
                        "cm": -0.045 * alpha - 0.012 * control + 0.004 * geom_idx,
                    }
                )
    pd.DataFrame(rows).to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
    (dataset_root / "rejected_aero_rows.csv").write_text("", encoding="utf-8")
    promotion_manifest = {
        "dataset_root": str(dataset_root),
        "promotion_forced": False,
        "promotion_ready_at_time_of_promotion": True,
        "promotion_blockers": [],
        "qc_context": {"qc_preset_used": "production", "geometry_qc_passed": True, "aero_qc_passed": True},
        "artifacts": {
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(json.dumps(promotion_manifest, indent=2), encoding="utf-8")
    return dataset_root


def _small_neural_params() -> dict[str, object]:
    return {
        "hidden_layer_sizes": [12],
        "max_iter": 250,
        "early_stopping": False,
        "learning_rate": "constant",
        "learning_rate_init": 0.01,
        "tol": 1.0e-5,
    }


def test_neural_model_types_are_registered() -> None:
    model_types = list_model_types()
    assert "neural_mlp" in model_types
    assert "neural_mlp_ensemble" in model_types

    single = build_model("neural_mlp", random_seed=123, model_params=_small_neural_params())
    ensemble = build_model(
        "neural_mlp_ensemble",
        random_seed=123,
        model_params={**_small_neural_params(), "n_members": 3},
    )
    assert hasattr(single, "fit") and hasattr(single, "predict")
    assert hasattr(ensemble, "fit") and hasattr(ensemble, "predict_members")


def test_train_neural_mlp_through_existing_training_pipeline(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    model_run_dir = tmp_path / "neural_mlp_run"

    result = train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="neural_mlp",
        split_method="grouped",
        random_seed=123,
        model_params=_small_neural_params(),
        output_dir=model_run_dir,
    )

    assert (model_run_dir / "models" / "model.pkl").exists()
    assert (model_run_dir / "metrics.json").exists()
    assert result["metrics"]["model"]["model_type"] == "neural_mlp"
    assert result["metrics"]["model"]["family_name"] == "neural_tabular"
    assert np.isfinite(result["metrics"]["test"]["overall"]["rmse_mean"])


def test_neural_mlp_ensemble_supports_confidence_spread(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    model_run_dir = tmp_path / "neural_ensemble_run"

    train_baseline_model(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=TARGET_COLUMNS,
        model_type="neural_mlp_ensemble",
        split_method="grouped",
        random_seed=123,
        model_params={**_small_neural_params(), "n_members": 3},
        output_dir=model_run_dir,
    )
    _inject_test_dataset_promotion_context(model_run_dir, dataset_root)
    promotion = promote_model_run(
        model_run_dir=model_run_dir,
        max_test_rmse_mean=10.0,
        min_test_r2_mean=-1000.0,
    )
    assert promotion.passed is True

    input_csv = tmp_path / "candidate_pool.csv"
    pd.read_csv(model_run_dir / "test_rows.csv").head(10).to_csv(input_csv, index=False)
    confidence = predict_with_confidence(
        model_run_dir=model_run_dir,
        input_csv=input_csv,
        output_dir=tmp_path / "confidence",
        require_promoted_model_gate=True,
    )

    assert confidence.report["uncertainty"]["supported"] is True
    assert confidence.report["uncertainty"]["method"] == "native_estimator_prediction_spread"
    assert "uncertainty__cl" in confidence.output_df.columns
    assert np.isfinite(confidence.output_df["uncertainty__cl"].to_numpy(dtype=float)).any()


def test_neural_mlp_cli_training_smoke(tmp_path: Path) -> None:
    pytest.importorskip("aerosandbox")
    from aeris.cli import app

    dataset_root = _build_dataset(tmp_path)
    params_path = tmp_path / "mlp_params.json"
    params_path.write_text(json.dumps(_small_neural_params()), encoding="utf-8")
    output_dir = tmp_path / "cli_neural_mlp"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "ml",
            "train",
            "--dataset",
            str(dataset_root),
            "--feature-preset",
            "bwb_control",
            "--targets",
            ",".join(TARGET_COLUMNS),
            "--model-type",
            "neural_mlp",
            "--split-method",
            "grouped",
            "--random-seed",
            "123",
            "--model-params-json",
            str(params_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "ML training completed" in result.output
    assert "model_type: neural_mlp" in result.output
    assert (output_dir / "models" / "model.pkl").exists()
