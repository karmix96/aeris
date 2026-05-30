from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from aeris.ml.fingerprints import file_sha256, json_sha256
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.diagnostics import write_regression_diagnostics


def test_file_and_json_hashes_are_stable(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("abc", encoding="utf-8")

    assert file_sha256(p) == file_sha256(p)
    assert json_sha256({"b": 2, "a": 1}) == json_sha256({"a": 1, "b": 2})


def test_enhanced_regression_metrics_keep_compatibility_keys() -> None:
    y_true = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])
    y_pred = np.array([[1.1, 1.9], [2.1, 4.2], [2.8, 5.7]])

    m = evaluate_regression_metrics(y_true, y_pred, ["cl", "cd"])

    assert "rmse" in m["per_target"]["cl"]
    assert "mae" in m["per_target"]["cl"]
    assert "r2" in m["per_target"]["cl"]
    assert "error_p95" in m["per_target"]["cl"]
    assert "nrmse_by_range" in m["per_target"]["cl"]
    assert "rmse_mean" in m["overall"]
    assert m["overall"]["n_rows"] == 3


def test_write_regression_diagnostics(tmp_path: Path) -> None:
    df = pd.DataFrame({"geometry_id": ["g1", "g2"], "alpha_deg": [0.0, 2.0], "cl": [0.1, 0.2]})
    y_true = np.array([[0.1], [0.2]])
    y_pred = np.array([[0.11], [0.19]])

    out = write_regression_diagnostics(
        partition_name="test",
        df=df,
        target_columns=["cl"],
        y_true=y_true,
        y_pred=y_pred,
        output_dir=tmp_path,
    )

    assert Path(out["prediction_vs_truth_csv"]).exists()
    assert Path(out["residuals_csv"]).exists()
    assert out["summary"]["n_rows"] == 2
