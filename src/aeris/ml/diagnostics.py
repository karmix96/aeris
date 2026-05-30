"""
Diagnostic artifact writers for AERIS ML runs.

These outputs make model failures inspectable by condition, geometry/airfoil id,
and target variable. They are intentionally CSV-first so they can be inspected
with normal tooling before we add plotting/report layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _as_2d(array: np.ndarray) -> np.ndarray:
    arr = np.asarray(array, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


def build_prediction_vs_truth_frame(
    *,
    base_df: pd.DataFrame,
    target_columns: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> pd.DataFrame:
    """Return a dataframe with true, predicted, residual, and absolute residual columns."""
    y_true = _as_2d(y_true)
    y_pred = _as_2d(y_pred)

    if y_true.shape != y_pred.shape:
        raise ValueError(f"y_true/y_pred shape mismatch: {y_true.shape} vs {y_pred.shape}")
    if y_true.shape[1] != len(target_columns):
        raise ValueError("target_columns does not match y array width")

    out = base_df.reset_index(drop=True).copy()
    for idx, target in enumerate(target_columns):
        out[f"true__{target}"] = y_true[:, idx]
        out[f"pred__{target}"] = y_pred[:, idx]
        out[f"error__{target}"] = y_pred[:, idx] - y_true[:, idx]
        out[f"abs_error__{target}"] = np.abs(y_pred[:, idx] - y_true[:, idx])
    return out


def build_residual_summary(
    *,
    frame: pd.DataFrame,
    target_columns: list[str],
) -> dict[str, Any]:
    """Build compact residual summary from a prediction-vs-truth dataframe."""
    summary: dict[str, Any] = {"targets": {}, "n_rows": int(len(frame))}
    for target in target_columns:
        err = frame[f"error__{target}"].to_numpy(dtype=float)
        abs_err = np.abs(err)
        summary["targets"][target] = {
            "bias_mean": float(np.mean(err)),
            "error_std": float(np.std(err)),
            "abs_error_mean": float(np.mean(abs_err)),
            "abs_error_max": float(np.max(abs_err)),
            "abs_error_p50": float(np.percentile(abs_err, 50)),
            "abs_error_p90": float(np.percentile(abs_err, 90)),
            "abs_error_p95": float(np.percentile(abs_err, 95)),
            "abs_error_p99": float(np.percentile(abs_err, 99)),
        }
    return summary


def write_regression_diagnostics(
    *,
    partition_name: str,
    df: pd.DataFrame,
    target_columns: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
    output_dir: Path,
) -> dict[str, Any]:
    """Write prediction-vs-truth and residual CSVs for one data partition."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = build_prediction_vs_truth_frame(
        base_df=df,
        target_columns=target_columns,
        y_true=y_true,
        y_pred=y_pred,
    )

    prediction_path = output_dir / f"{partition_name}_prediction_vs_truth.csv"
    residuals_path = output_dir / f"{partition_name}_residuals.csv"

    frame.to_csv(prediction_path, index=False)

    residual_cols: list[str] = []
    id_like_cols = [
        col for col in [
            "geometry_id",
            "airfoil_id",
            "case_id",
            "alpha_deg",
            "beta_deg",
            "reynolds",
            "mach",
            "velocity_mps",
            "altitude_m",
            "control_input_deg",
            "solver_id",
            "fidelity_level",
        ] if col in frame.columns
    ]
    residual_cols.extend(id_like_cols)
    for target in target_columns:
        residual_cols.extend([f"true__{target}", f"pred__{target}", f"error__{target}", f"abs_error__{target}"])

    frame[residual_cols].to_csv(residuals_path, index=False)

    return {
        "partition": partition_name,
        "prediction_vs_truth_csv": str(prediction_path),
        "residuals_csv": str(residuals_path),
        "summary": build_residual_summary(frame=frame, target_columns=target_columns),
    }
