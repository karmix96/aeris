"""
Regression metrics for AERIS ML.

The old RMSE/MAE/R2 trio is kept for compatibility, but this module adds the
error percentiles and normalized metrics needed for serious aero surrogate work.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def _as_2d(array: np.ndarray) -> np.ndarray:
    arr = np.asarray(array, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


def _safe_float(value: float | np.floating | int | None) -> float | None:
    if value is None:
        return None
    value_f = float(value)
    if not np.isfinite(value_f):
        return None
    return value_f


def evaluate_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_columns: list[str],
) -> dict[str, Any]:
    """
    Compute per-target and overall regression metrics.

    Compatibility keys retained:
    - per_target[target].rmse / mae / r2
    - overall.rmse_mean / mae_mean / r2_mean
    """
    y_true = _as_2d(y_true)
    y_pred = _as_2d(y_pred)

    if y_true.shape != y_pred.shape:
        raise ValueError(f"y_true/y_pred shape mismatch: {y_true.shape} vs {y_pred.shape}")
    if y_true.shape[1] != len(target_columns):
        raise ValueError(
            f"target column count mismatch: y has {y_true.shape[1]} columns, "
            f"target_columns has {len(target_columns)}"
        )

    per_target: dict[str, dict[str, float | None]] = {}
    rmse_values: list[float] = []
    mae_values: list[float] = []
    r2_values: list[float] = []
    max_abs_values: list[float] = []

    for idx, target in enumerate(target_columns):
        yt = y_true[:, idx]
        yp = y_pred[:, idx]
        err = yp - yt
        abs_err = np.abs(err)

        rmse = float(np.sqrt(mean_squared_error(yt, yp)))
        mae = float(mean_absolute_error(yt, yp))
        r2 = float(r2_score(yt, yp))
        max_abs = float(np.max(abs_err)) if len(abs_err) else 0.0
        target_std = float(np.std(yt)) if len(yt) else 0.0
        target_range = float(np.max(yt) - np.min(yt)) if len(yt) else 0.0

        nrmse_std = rmse / target_std if target_std > 0 else None
        nrmse_range = rmse / target_range if target_range > 0 else None

        per_target[target] = {
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
            "max_abs_error": max_abs,
            "error_p50": float(np.percentile(abs_err, 50)),
            "error_p90": float(np.percentile(abs_err, 90)),
            "error_p95": float(np.percentile(abs_err, 95)),
            "error_p99": float(np.percentile(abs_err, 99)),
            "bias_mean": float(np.mean(err)),
            "error_std": float(np.std(err)),
            "target_mean": float(np.mean(yt)),
            "target_std": target_std,
            "target_min": float(np.min(yt)),
            "target_max": float(np.max(yt)),
            "target_range": target_range,
            "nrmse_by_std": _safe_float(nrmse_std),
            "nrmse_by_range": _safe_float(nrmse_range),
        }

        rmse_values.append(rmse)
        mae_values.append(mae)
        r2_values.append(r2)
        max_abs_values.append(max_abs)

    return {
        "per_target": per_target,
        "overall": {
            "rmse_mean": float(np.mean(rmse_values)),
            "mae_mean": float(np.mean(mae_values)),
            "r2_mean": float(np.mean(r2_values)),
            "max_abs_error_mean": float(np.mean(max_abs_values)),
            "n_rows": int(y_true.shape[0]),
            "n_targets": int(y_true.shape[1]),
        },
    }
