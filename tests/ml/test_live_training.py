from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from aeris.ml.live_training import run_live_mlp_arrays


def test_run_live_mlp_arrays_writes_full_metric_artifacts(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    X = rng.normal(size=(54, 4))
    y0 = 2.0 * X[:, 0] - 0.5 * X[:, 1]
    y1 = -1.0 * X[:, 2] + 0.25 * X[:, 3]
    y = np.column_stack([y0, y1])

    events: list[dict] = []
    result = run_live_mlp_arrays(
        X_train=X[:36],
        y_train=y[:36],
        X_val=X[36:45],
        y_val=y[36:45],
        X_test=X[45:],
        y_test=y[45:],
        target_columns=["target_a", "target_b"],
        output_dir=tmp_path / "live_run",
        max_epochs=4,
        random_seed=11,
        model_params={"hidden_layer_sizes": [8], "learning_rate_init": 0.001, "alpha": 0.0001},
        epoch_callback=events.append,
    )

    artifacts = result["artifacts"]
    assert len(events) == 4
    assert artifacts.report_json.exists()
    assert artifacts.history_csv.exists()
    assert artifacts.history_long_csv.exists()
    assert artifacts.loss_curve_png.exists()
    assert artifacts.rmse_mean_curve_png.exists()
    assert artifacts.r2_mean_curve_png.exists()
    assert artifacts.per_target_rmse_curve_png.exists()
    assert artifacts.normalized_error_curve_png.exists()
    assert artifacts.generalization_gap_curve_png.exists()
    assert artifacts.model_path.exists()
    assert artifacts.metrics_json.exists()

    hist = pd.read_csv(artifacts.history_csv)
    required_cols = {
        "epoch",
        "train_loss",
        "train_rmse_mean",
        "val_rmse_mean",
        "test_rmse_mean",
        "train_r2_mean",
        "val_r2_mean",
        "train_nrmse_scale_mean",
        "val_nrmse_scale_mean",
        "val_minus_train_rmse_mean",
        "val_rmse__target_a",
        "val_r2__target_b",
        "val_nrmse_scale__target_a",
        "val_loss_mse__target_b",
        "epoch_time_sec",
    }
    assert required_cols.issubset(set(hist.columns))
    assert hist["val_rmse_mean"].notna().all()

    long_hist = pd.read_csv(artifacts.history_long_csv)
    assert {"epoch", "partition", "target", "rmse", "nrmse_scale", "bias", "error_p95"}.issubset(long_hist.columns)
    assert set(long_hist["partition"]) == {"train", "val", "test"}

    report = json.loads(artifacts.report_json.read_text(encoding="utf-8"))
    assert report["schema_version"] == "aeris.live_training_monitor.v2.1"
    assert report["monitor_status"] == "live_iterative_training_full_metrics"
    assert report["live_streaming_supported"] is True
    assert report["history_available"] is True
    assert report["n_history_rows"] == 4
    assert "target_normalization" in report
    assert "diagnostics" in report
    assert "overfit_warning" in report["diagnostics"]
    assert "plateau_warning" in report["diagnostics"]



def test_live_training_v22_target_scaling_and_residual_artifacts(tmp_path):
    """Live MLP trains on scaled targets and writes residual artifacts."""
    import numpy as np
    from aeris.ml.live_training import run_live_mlp_arrays

    rng = np.random.default_rng(123)
    X = rng.normal(size=(40, 4))
    y0 = 100.0 * X[:, 0] + 10.0
    y1 = 0.01 * X[:, 1] - 0.2
    y = np.column_stack([y0, y1])
    out = tmp_path / "live_v22"
    result = run_live_mlp_arrays(
        X_train=X[:24],
        y_train=y[:24],
        X_val=X[24:32],
        y_val=y[24:32],
        X_test=X[32:],
        y_test=y[32:],
        target_columns=["large_units", "small_units"],
        output_dir=out,
        max_epochs=3,
        random_seed=1,
        model_params={"hidden_layer_sizes": [8], "learning_rate_init": 0.001, "alpha": 0.0001},
        tracking_backends=[],
    )
    report = result["report"]
    assert report["target_scaling"]["enabled"] is True
    assert (out / "training_monitor" / "residuals_long.csv").exists()
    assert "quality_warnings" in report

# AERIS_LIVE_TRAINING_V2_2_TARGET_SCALING_TEST
