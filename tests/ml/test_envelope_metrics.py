from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from aeris.ml.envelope_metrics import compute_envelope_metrics


def _make_model_run(tmp_path: Path) -> Path:
    model_run = tmp_path / "model_run"
    (model_run / "models").mkdir(parents=True)
    X = np.array([[0.0, 0.0], [0.5, 0.2], [1.0, 1.0], [0.2, 0.8]], dtype=float)
    y = np.column_stack([X[:, 0] + X[:, 1], 2.0 * X[:, 0] - X[:, 1]])
    model = LinearRegression().fit(X, y)
    with (model_run / "models" / "model.pkl").open("wb") as f:
        pickle.dump(model, f)
    (model_run / "train_config.json").write_text(
        json.dumps({"feature_columns": ["x", "z"], "target_columns": ["y1", "y2"], "model_type": "linear"}),
        encoding="utf-8",
    )
    (model_run / "training_envelope.json").write_text(
        json.dumps({"schema_version": "aeris.training_envelope.v1", "feature_ranges": {"x": {"min": 0.0, "max": 1.0}, "z": {"min": 0.0, "max": 1.0}}}),
        encoding="utf-8",
    )
    rows = pd.DataFrame(
        {
            "x": [0.1, 0.9, 1.2, -0.2],
            "z": [0.2, 0.7, 0.5, 0.4],
        }
    )
    rows["y1"] = rows["x"] + rows["z"]
    rows["y2"] = 2.0 * rows["x"] - rows["z"]
    rows.to_csv(model_run / "test_rows.csv", index=False)
    return model_run


def test_compute_envelope_metrics_splits_inside_and_outside_rows(tmp_path: Path) -> None:
    model_run = _make_model_run(tmp_path)
    result = compute_envelope_metrics(model_run_dir=model_run, require_promoted_model_gate=False)

    assert result.report["schema_version"] == "aeris.envelope_metrics_report.v1"
    assert result.report["row_counts"]["total"] == 4
    assert result.report["row_counts"]["inside"] == 2
    assert result.report["row_counts"]["outside"] == 2
    assert result.report["truth_available"] is True
    assert result.artifacts.report_path.exists()
    assert result.artifacts.predictions_csv_path.exists()
    assert result.artifacts.by_target_csv_path.exists()
    assert result.artifacts.by_feature_violation_csv_path.exists()

    by_target = pd.read_csv(result.artifacts.by_target_csv_path)
    assert {"all", "inside", "outside"}.issubset(set(by_target["partition"]))
    assert {"y1", "y2"}.issubset(set(by_target["target"]))

    out = pd.read_csv(result.artifacts.predictions_csv_path)
    assert "envelope_status" in out.columns
    assert set(out["envelope_status"]) == {"inside", "outside"}
    assert "pred__y1" in out.columns


def test_compute_envelope_metrics_can_use_custom_input_and_output(tmp_path: Path) -> None:
    model_run = _make_model_run(tmp_path)
    custom = tmp_path / "candidate.csv"
    pd.DataFrame({"x": [0.5, 1.5], "z": [0.5, 0.5], "y1": [1.0, 2.0], "y2": [0.5, 2.5]}).to_csv(custom, index=False)
    out_dir = tmp_path / "envelope_metrics"

    result = compute_envelope_metrics(
        model_run_dir=model_run,
        input_csv=custom,
        output_dir=out_dir,
        require_promoted_model_gate=False,
    )

    assert result.artifacts.output_dir == out_dir.resolve()
    assert result.report["row_counts"]["inside"] == 1
    assert result.report["row_counts"]["outside"] == 1
    assert result.report["feature_violation_summary"][0]["feature"] == "x"
