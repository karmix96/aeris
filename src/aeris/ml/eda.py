"""
Exploratory Data Analysis for AERIS promoted aero datasets.

This module operates directly on promoted datasets (curated_aero_dataset.csv).
It produces a structured JSON summary and optional per-column statistics that
are safe to compute before any train/val/test split.

Design rules:
- No model fitting, no splitting, no leakage.
- All functions are pure: accept a DataFrame, return a dict.
- run_eda() is the single entry point for CLI and train.py integration.
- Plots are optional and never block the JSON summary.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EDA_SCHEMA_VERSION = "aeris.eda_report.v1"


# ---------------------------------------------------------------------------
# Individual check functions — each returns a dict
# ---------------------------------------------------------------------------

def _summarize_shape(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "n_rows": int(len(df)),
        "n_columns": int(len(df.columns)),
        "columns": list(df.columns),
    }


def _detect_constant_columns(df: pd.DataFrame) -> dict[str, Any]:
    """Columns with only one unique finite value — useless as features."""
    constants: list[str] = []
    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        n_unique = int(numeric.dropna().nunique())
        if n_unique <= 1:
            constants.append(col)
    return {
        "constant_columns": constants,
        "n_constant": len(constants),
    }


def _detect_duplicates(df: pd.DataFrame) -> dict[str, Any]:
    n_dup = int(df.duplicated().sum())
    return {
        "n_duplicate_rows": n_dup,
        "has_duplicates": n_dup > 0,
    }


def _per_column_stats(
    df: pd.DataFrame,
    columns: list[str],
    label: str,
) -> dict[str, Any]:
    """Min/max/mean/std/nan count for a list of columns."""
    stats: dict[str, Any] = {}
    for col in columns:
        if col not in df.columns:
            stats[col] = {"error": "missing"}
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        finite = numeric.dropna()
        n_nan = int(numeric.isna().sum())
        stats[col] = {
            "n_finite": int(len(finite)),
            "n_nan": n_nan,
            "min": float(finite.min()) if len(finite) else None,
            "max": float(finite.max()) if len(finite) else None,
            "mean": float(finite.mean()) if len(finite) else None,
            "std": float(finite.std(ddof=1)) if len(finite) > 1 else None,
            "p25": float(finite.quantile(0.25)) if len(finite) else None,
            "p75": float(finite.quantile(0.75)) if len(finite) else None,
        }
    return {label: stats}


def _per_geometry_coverage(
    df: pd.DataFrame,
    group_column: str = "geometry_id",
) -> dict[str, Any]:
    """How many rows does each geometry contribute?"""
    if group_column not in df.columns:
        return {"error": f"'{group_column}' not in dataset"}
    counts = df.groupby(group_column).size()
    return {
        "n_geometries": int(counts.shape[0]),
        "rows_per_geometry_min": int(counts.min()),
        "rows_per_geometry_max": int(counts.max()),
        "rows_per_geometry_mean": float(counts.mean()),
        "rows_per_geometry_std": float(counts.std(ddof=1)) if len(counts) > 1 else 0.0,
        "uniform_coverage": bool(counts.nunique() == 1),
    }


def _alpha_control_coverage(
    df: pd.DataFrame,
    alpha_col: str = "alpha_deg",
    control_col: str = "control_input_deg",
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if alpha_col in df.columns:
        vals = sorted(pd.to_numeric(df[alpha_col], errors="coerce").dropna().unique().tolist())
        result["alpha_values"] = [float(v) for v in vals]
        result["n_alpha_values"] = len(vals)
    else:
        result["alpha_values"] = None
        result["n_alpha_values"] = None
    if control_col in df.columns:
        vals = sorted(pd.to_numeric(df[control_col], errors="coerce").dropna().unique().tolist())
        result["control_input_values"] = [float(v) for v in vals]
        result["n_control_values"] = len(vals)
    else:
        result["control_input_values"] = None
        result["n_control_values"] = None
    return result


def _correlation_matrix(
    df: pd.DataFrame,
    columns: list[str],
) -> dict[str, Any]:
    """Pearson correlation matrix for specified columns."""
    available = [c for c in columns if c in df.columns]
    if len(available) < 2:
        return {"error": "fewer than 2 columns available for correlation"}
    numeric_df = df[available].apply(pd.to_numeric, errors="coerce")
    corr = numeric_df.corr(method="pearson")
    return {
        "columns": available,
        "matrix": {
            col: {other: (None if math.isnan(v) else round(float(v), 4))
                  for other, v in corr[col].items()}
            for col in available
        },
    }


def _nonlinearity_scan(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_cols: list[str],
) -> dict[str, Any]:
    """
    Rough nonlinearity signal: compare Pearson r² (linear) vs Spearman r² (rank).
    A large gap means the feature-target relationship is nonlinear.
    """
    results: dict[str, Any] = {}
    for target in target_cols:
        if target not in df.columns:
            continue
        y = pd.to_numeric(df[target], errors="coerce")
        target_results: dict[str, Any] = {}
        for feat in feature_cols:
            if feat not in df.columns:
                continue
            x = pd.to_numeric(df[feat], errors="coerce")
            mask = x.notna() & y.notna()
            if mask.sum() < 10:
                continue
            xf, yf = x[mask], y[mask]
            pearson_r = float(np.corrcoef(xf, yf)[0, 1])
            spearman_r = float(xf.rank().corr(yf.rank()))
            target_results[feat] = {
                "pearson_r": round(pearson_r, 4),
                "spearman_r": round(spearman_r, 4),
                "nonlinearity_gap": round(abs(abs(spearman_r) - abs(pearson_r)), 4),
            }
        results[target] = target_results
    return results


def _outlier_scan(
    df: pd.DataFrame,
    columns: list[str],
    sigma: float = 4.0,
) -> dict[str, Any]:
    """Flag rows where any column exceeds sigma standard deviations from mean."""
    outlier_counts: dict[str, int] = {}
    for col in columns:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(numeric) < 4:
            continue
        mean, std = float(numeric.mean()), float(numeric.std(ddof=1))
        if std == 0:
            continue
        n_out = int(((numeric - mean).abs() > sigma * std).sum())
        if n_out > 0:
            outlier_counts[col] = n_out
    return {
        "sigma_threshold": sigma,
        "columns_with_outliers": outlier_counts,
        "n_columns_with_outliers": len(outlier_counts),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_eda(
    df: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_columns: list[str],
    group_column: str = "geometry_id",
    outlier_sigma: float = 4.0,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """
    Run full EDA on a promoted aero dataset DataFrame.

    Parameters
    ----------
    df:
        The curated_aero_dataset DataFrame (already loaded, not split).
    feature_columns:
        Columns used as ML features.
    target_columns:
        Columns used as ML targets.
    group_column:
        Grouping column for per-geometry coverage check.
    outlier_sigma:
        Z-score threshold for outlier flagging.
    output_path:
        If provided, writes the JSON report to this path.

    Returns
    -------
    dict with keys: schema_version, shape, constant_columns, duplicates,
    feature_stats, target_stats, per_geometry_coverage, alpha_control_coverage,
    correlation, nonlinearity, outliers.
    """
    all_cols = list(dict.fromkeys(feature_columns + target_columns))

    report: dict[str, Any] = {
        "schema_version": EDA_SCHEMA_VERSION,
        "shape": _summarize_shape(df),
        "constant_columns": _detect_constant_columns(df),
        "duplicates": _detect_duplicates(df),
        **_per_column_stats(df, feature_columns, "feature_stats"),
        **_per_column_stats(df, target_columns, "target_stats"),
        "per_geometry_coverage": _per_geometry_coverage(df, group_column),
        "alpha_control_coverage": _alpha_control_coverage(df),
        "correlation": _correlation_matrix(df, all_cols),
        "nonlinearity": _nonlinearity_scan(df, feature_columns, target_columns),
        "outliers": _outlier_scan(df, all_cols, sigma=outlier_sigma),
    }

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report