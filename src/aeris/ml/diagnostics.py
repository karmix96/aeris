"""
PATCH 02 — src/aeris/ml/diagnostics.py
========================================
Adds per-regime diagnostic slicing after the existing global diagnostics.

WHAT THIS ADDS
--------------
1. `compute_regime_diagnostics(frame, regime_columns, target_columns)`
   Slices residuals_csv by bins of alpha_deg, control_input_deg, velocity_mps,
   and any other regime_columns present. Returns per-bin RMSE, MAE, bias.

2. `write_regression_diagnostics()` gains an optional `regime_columns` parameter.
   When supplied (and columns are present), writes regime_diagnostics.json to
   the diagnostics dir and adds its path to the returned dict.

HOW TO APPLY
------------
Replace src/aeris/ml/diagnostics.py entirely with this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _as_2d(array: np.ndarray) -> np.ndarray:
    arr = np.asarray(array, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


# ---------------------------------------------------------------------------
# Existing public functions (unchanged signatures, unchanged behaviour)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# NEW: per-regime slicing
# ---------------------------------------------------------------------------

# Default bin edges for the most common regime dimensions.
# Values chosen for the BWB design space: alpha -6..14°, control -12..12°.
_DEFAULT_BIN_EDGES: dict[str, list[float]] = {
    "alpha_deg":        [-99.0, -4.0, 0.0, 4.0, 8.0, 12.0, 99.0],
    "control_input_deg": [-99.0, -8.0, -3.0, 3.0, 8.0, 99.0],
    "velocity_mps":     [0.0, 15.0, 22.0, 30.0, 40.0, 999.0],
    "altitude_m":       [-99.0, 500.0, 1500.0, 3000.0, 99999.0],
    "reynolds":         [0.0, 2e5, 5e5, 1e6, 2e6, 1e9],
    "mach":             [0.0, 0.1, 0.2, 0.3, 1.0],
}

_DEFAULT_REGIME_COLUMNS: tuple[str, ...] = (
    "alpha_deg",
    "control_input_deg",
    "velocity_mps",
    "altitude_m",
)


def _bin_label(lo: float, hi: float) -> str:
    """Human-readable bin label."""
    lo_s = f"{lo:.3g}" if abs(lo) < 1e6 else f"{lo:.2e}"
    hi_s = f"{hi:.3g}" if abs(hi) < 1e6 else f"{hi:.2e}"
    return f"[{lo_s}, {hi_s})"


def _per_bin_metrics(
    frame: pd.DataFrame,
    col: str,
    edges: list[float],
    target_columns: list[str],
) -> list[dict[str, Any]]:
    """Compute per-bin residual metrics for one regime column."""
    bins: list[dict[str, Any]] = []
    values = pd.to_numeric(frame[col], errors="coerce").to_numpy(dtype=float)

    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        mask = (values >= lo) & (values < hi)
        n = int(mask.sum())
        if n == 0:
            continue

        sub = frame[mask]
        entry: dict[str, Any] = {
            "bin": _bin_label(lo, hi),
            "lo": float(lo),
            "hi": float(hi),
            "n_rows": n,
            "targets": {},
        }
        for target in target_columns:
            err_col = f"error__{target}"
            abs_col = f"abs_error__{target}"
            if err_col not in sub.columns or abs_col not in sub.columns:
                continue
            err = sub[err_col].to_numpy(dtype=float)
            abs_err = sub[abs_col].to_numpy(dtype=float)
            finite_mask = np.isfinite(err) & np.isfinite(abs_err)
            if not finite_mask.any():
                entry["targets"][target] = {"n_finite": 0}
                continue
            ef = err[finite_mask]
            af = abs_err[finite_mask]
            rmse = float(np.sqrt(np.mean(ef ** 2)))
            entry["targets"][target] = {
                "n_finite": int(finite_mask.sum()),
                "rmse": rmse,
                "mae": float(np.mean(af)),
                "bias_mean": float(np.mean(ef)),
                "abs_error_p95": float(np.percentile(af, 95)),
                "abs_error_max": float(np.max(af)),
            }
        bins.append(entry)
    return bins


def compute_regime_diagnostics(
    frame: pd.DataFrame,
    target_columns: list[str],
    *,
    regime_columns: list[str] | None = None,
    bin_edges_override: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """
    Compute per-regime residual diagnostics from a prediction-vs-truth frame.

    Parameters
    ----------
    frame:
        Output of build_prediction_vs_truth_frame(). Must contain
        error__<target> and abs_error__<target> columns.
    target_columns:
        Target names (cl, cd, cm, ...).
    regime_columns:
        Which columns to slice by. Defaults to alpha_deg, control_input_deg,
        velocity_mps, altitude_m (whichever are present in frame).
    bin_edges_override:
        Optional dict of {column: [edge0, edge1, ...]} to override defaults.
        Missing columns fall back to _DEFAULT_BIN_EDGES or even-quantile bins.

    Returns
    -------
    dict with schema_version, n_rows, regime_slices keyed by column name.
    """
    if regime_columns is None:
        regime_columns = [c for c in _DEFAULT_REGIME_COLUMNS if c in frame.columns]

    edges_map = dict(_DEFAULT_BIN_EDGES)
    if bin_edges_override:
        edges_map.update(bin_edges_override)

    slices: dict[str, Any] = {}
    for col in regime_columns:
        if col not in frame.columns:
            continue
        edges = edges_map.get(col)
        if edges is None:
            # Auto-quantile fallback: 5 equal-sized bins from the data.
            vals = pd.to_numeric(frame[col], errors="coerce").dropna().to_numpy(dtype=float)
            if len(vals) < 2:
                continue
            qs = np.linspace(0, 100, 6)
            edges = sorted(set(np.percentile(vals, qs).tolist()))
            edges[0] = edges[0] - 1e-9
            edges[-1] = edges[-1] + 1e-9

        slices[col] = _per_bin_metrics(frame, col, edges, target_columns)

    # Compute worst-bin summary: which regime column+bin has the highest RMSE
    # for any target? Useful for quick scanning across many targets.
    worst_bins: list[dict[str, Any]] = []
    for col, bins in slices.items():
        for b in bins:
            for target, tmet in b.get("targets", {}).items():
                rmse = tmet.get("rmse")
                if rmse is not None:
                    worst_bins.append({
                        "regime_column": col,
                        "bin": b["bin"],
                        "target": target,
                        "rmse": rmse,
                        "n_rows": b["n_rows"],
                    })
    worst_bins.sort(key=lambda x: x["rmse"], reverse=True)

    return {
        "schema_version": "aeris.regime_diagnostics.v1",
        "n_rows": int(len(frame)),
        "target_columns": list(target_columns),
        "regime_columns_sliced": list(slices.keys()),
        "regime_slices": slices,
        "worst_bins_by_rmse": worst_bins[:20],  # top 20 worst regime/target combos
    }


# ---------------------------------------------------------------------------
# Patched write_regression_diagnostics (new optional parameter: regime_columns)
# ---------------------------------------------------------------------------

def write_regression_diagnostics(
    *,
    partition_name: str,
    df: pd.DataFrame,
    target_columns: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
    output_dir: Path,
    regime_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Write prediction-vs-truth and residual CSVs for one data partition.

    NEW: if `regime_columns` is supplied (or the frame contains the default
    regime columns), also writes regime_diagnostics.json with per-bin metrics.
    This is additive — callers that do not pass regime_columns get the same
    output as before.
    """
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
        residual_cols.extend(
            [f"true__{target}", f"pred__{target}", f"error__{target}", f"abs_error__{target}"]
        )

    frame[residual_cols].to_csv(residuals_path, index=False)

    # ── NEW: regime diagnostics ──────────────────────────────────────────────
    regime_diag_path: Path | None = None
    regime_cols_present = [
        c for c in (regime_columns or list(_DEFAULT_REGIME_COLUMNS))
        if c in frame.columns
    ]
    if regime_cols_present:
        regime_diag = compute_regime_diagnostics(
            frame,
            target_columns,
            regime_columns=regime_cols_present,
        )
        regime_diag_path = output_dir / f"{partition_name}_regime_diagnostics.json"
        regime_diag_path.write_text(json.dumps(regime_diag, indent=2), encoding="utf-8")

    result: dict[str, Any] = {
        "partition": partition_name,
        "prediction_vs_truth_csv": str(prediction_path),
        "residuals_csv": str(residuals_path),
        "summary": build_residual_summary(frame=frame, target_columns=target_columns),
    }
    if regime_diag_path is not None:
        result["regime_diagnostics_json"] = str(regime_diag_path)

    return result
