from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from aeris.ml.live_training import run_live_mlp_arrays


def test_run_live_mlp_arrays_writes_epoch_artifacts(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    X = rng.normal(size=(40, 4))
    y0 = 2.0 * X[:, 0] - 0.5 * X[:, 1]
    y1 = -1.0 * X[:, 2] + 0.25 * X[:, 3]
    y = np.column_stack([y0, y1])

    events: list[dict] = []
    result = run_live_mlp_arrays(
        X_train=X[:28],
        y_train=y[:28],
        X_val=X[28:34],
        y_val=y[28:34],
        X_test=X[34:],
        y_test=y[34:],
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
    assert artifacts.loss_curve_png.exists()
    assert artifacts.model_path.exists()
    assert artifacts.metrics_json.exists()

    report = json.loads(artifacts.report_json.read_text(encoding="utf-8"))
    assert report["schema_version"] == "aeris.live_training_monitor.v2"
    assert report["monitor_status"] == "live_iterative_training"
    assert report["live_streaming_supported"] is True
    assert report["history_available"] is True
    assert report["n_history_rows"] == 4
    assert report["latest_epoch"]["epoch"] == 4
