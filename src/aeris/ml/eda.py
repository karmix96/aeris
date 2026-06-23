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

EDA_SCHEMA_VERSION = "aeris.eda_report.v2"


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


def _numeric_column_status(series: pd.Series, *, min_rows: int = 2) -> dict[str, Any]:
    """Return numeric usability diagnostics for correlation-style EDA checks."""
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric.dropna()
    n_finite = int(len(finite))
    n_unique = int(finite.nunique())
    if n_finite < min_rows:
        return {
            "status": "skipped",
            "reason": "insufficient_finite_rows",
            "n_finite": n_finite,
            "n_unique": n_unique,
        }
    if n_unique < 2:
        return {
            "status": "skipped",
            "reason": "constant_or_single_unique_value",
            "n_finite": n_finite,
            "n_unique": n_unique,
        }
    std = float(finite.std(ddof=1)) if n_finite > 1 else 0.0
    if not math.isfinite(std) or std == 0.0:
        return {
            "status": "skipped",
            "reason": "zero_or_invalid_std",
            "n_finite": n_finite,
            "n_unique": n_unique,
        }
    return {
        "status": "usable",
        "reason": None,
        "n_finite": n_finite,
        "n_unique": n_unique,
        "std": std,
    }


def _correlatable_numeric_columns(df: pd.DataFrame, columns: list[str], *, min_rows: int = 2) -> tuple[list[str], list[dict[str, Any]]]:
    """Columns that can participate in Pearson/Spearman correlation without NaNs/warnings."""
    usable: list[str] = []
    skipped: list[dict[str, Any]] = []
    for col in columns:
        if col not in df.columns:
            skipped.append({"column": col, "reason": "missing", "status": "skipped"})
            continue
        status = _numeric_column_status(df[col], min_rows=min_rows)
        if status["status"] == "usable":
            usable.append(col)
        else:
            skipped.append({"column": col, **status})
    return usable, skipped


def _safe_corr(x: pd.Series, y: pd.Series, *, method: str, min_rows: int = 3) -> float | None:
    """Warning-safe correlation for one pair. Returns None when undefined."""
    x_num = pd.to_numeric(x, errors="coerce")
    y_num = pd.to_numeric(y, errors="coerce")
    mask = x_num.notna() & y_num.notna()
    if int(mask.sum()) < min_rows:
        return None
    xf = x_num[mask]
    yf = y_num[mask]
    if int(xf.nunique()) < 2 or int(yf.nunique()) < 2:
        return None
    value = xf.corr(yf, method=method)
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value)


def _correlation_matrix(
    df: pd.DataFrame,
    columns: list[str],
) -> dict[str, Any]:
    """Pearson correlation matrix for specified columns, skipping undefined constant columns."""
    requested = [c for c in columns if c in df.columns]
    usable, skipped = _correlatable_numeric_columns(df, requested, min_rows=2)
    if len(usable) < 2:
        return {
            "columns": usable,
            "requested_columns": requested,
            "skipped_columns": skipped,
            "matrix": {},
            "warning": "fewer than 2 non-constant numeric columns available for correlation",
        }

    matrix: dict[str, dict[str, float | None]] = {}
    for col in usable:
        matrix[col] = {}
        for other in usable:
            if col == other:
                matrix[col][other] = 1.0
            else:
                value = _safe_corr(df[col], df[other], method="pearson", min_rows=2)
                matrix[col][other] = None if value is None else round(value, 4)
    return {
        "columns": usable,
        "requested_columns": requested,
        "skipped_columns": skipped,
        "matrix": matrix,
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
            pearson_r = _safe_corr(xf, yf, method="pearson", min_rows=10)
            spearman_r = _safe_corr(xf, yf, method="spearman", min_rows=10)
            if pearson_r is None or spearman_r is None:
                target_results[feat] = {
                    "status": "skipped",
                    "reason": "undefined_correlation_constant_or_insufficient_variance",
                    "pearson_r": None,
                    "spearman_r": None,
                    "nonlinearity_gap": None,
                }
                continue
            target_results[feat] = {
                "status": "computed",
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


def _round_float(value: float | None, digits: int = 6) -> float | None:
    """Round finite floats for stable JSON reports."""
    if value is None:
        return None
    try:
        val = float(value)
    except Exception:
        return None
    if not math.isfinite(val):
        return None
    return round(val, digits)


def _dtype_report(df: pd.DataFrame) -> dict[str, Any]:
    """Column dtype and numeric-coercion diagnostics."""
    columns: dict[str, Any] = {}
    for col in df.columns:
        series = df[col]
        numeric = pd.to_numeric(series, errors="coerce")
        non_missing = int(series.notna().sum())
        numeric_non_missing = int(numeric.notna().sum())
        columns[col] = {
            "dtype": str(series.dtype),
            "n_unique": int(series.nunique(dropna=True)),
            "n_missing": int(series.isna().sum()),
            "numeric_coercible_fraction": (
                float(numeric_non_missing / non_missing) if non_missing else None
            ),
            "is_numeric_like": bool(non_missing > 0 and numeric_non_missing == non_missing),
        }
    return {
        "columns": columns,
        "n_columns": int(len(columns)),
        "n_numeric_like": int(sum(1 for item in columns.values() if item["is_numeric_like"])),
    }


def _missingness_report(
    df: pd.DataFrame,
    *,
    important_columns: list[str],
    group_column: str = "geometry_id",
    condition_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Missing-value diagnostics by column, group, and operating condition."""
    condition_columns = condition_columns or [
        "alpha_deg",
        "control_input_deg",
        "delta_e_sym_deg",
        "delta_a_diff_deg",
        "velocity_mps",
        "altitude_m",
    ]
    n_rows = int(len(df))

    by_column: dict[str, Any] = {}
    for col in df.columns:
        n_missing = int(df[col].isna().sum())
        by_column[col] = {
            "n_missing": n_missing,
            "missing_fraction": float(n_missing / n_rows) if n_rows else None,
        }

    selected = [c for c in important_columns if c in df.columns]
    by_group: dict[str, Any]
    if group_column in df.columns and selected:
        missing_mask = df[selected].isna().any(axis=1)
        counts = missing_mask.groupby(df[group_column]).sum().sort_values(ascending=False)
        top = counts[counts > 0].head(20)
        by_group = {
            "group_column": group_column,
            "important_columns": selected,
            "n_groups": int(df[group_column].nunique(dropna=True)),
            "n_groups_with_any_missing": int((counts > 0).sum()),
            "top_groups_by_missing_rows": [
                {"group": str(idx), "n_missing_rows": int(val)}
                for idx, val in top.items()
            ],
        }
    else:
        by_group = {
            "group_column": group_column,
            "important_columns": selected,
            "status": "skipped",
            "reason": "missing_group_column_or_no_selected_columns",
        }

    by_condition: dict[str, Any] = {}
    target_like = [c for c in selected if c in df.columns]
    for cond in condition_columns:
        if cond not in df.columns or not target_like:
            continue
        cond_summary: dict[str, Any] = {}
        for value, sub in df.groupby(cond, dropna=False):
            key = "<NA>" if pd.isna(value) else str(value)
            cond_summary[key] = {
                "n_rows": int(len(sub)),
                "n_rows_with_any_missing": int(sub[target_like].isna().any(axis=1).sum()),
            }
        by_condition[cond] = cond_summary

    return {
        "n_rows": n_rows,
        "by_column": by_column,
        "columns_with_missing": [col for col, item in by_column.items() if item["n_missing"] > 0],
        "n_columns_with_missing": int(sum(1 for item in by_column.values() if item["n_missing"] > 0)),
        "by_group": by_group,
        "by_condition": by_condition,
    }


def _categorical_summary(
    df: pd.DataFrame,
    *,
    max_unique_for_category: int = 25,
    top_n: int = 10,
) -> dict[str, Any]:
    """Small categorical/status-column summary for failure/status/provenance fields."""
    preferred_names = {
        "solver_id",
        "solver_status",
        "status",
        "failure_reason",
        "reject_reason",
        "rejection_reason",
        "geometry_family",
        "source_generator",
        "sweep_type",
        "control_mode",
        "fidelity_level",
    }
    summaries: dict[str, Any] = {}
    for col in df.columns:
        series = df[col]
        numeric_status = _numeric_column_status(series, min_rows=2)
        n_unique = int(series.nunique(dropna=True))
        should_summarize = (
            col in preferred_names
            or series.dtype == "object"
            or n_unique <= max_unique_for_category and numeric_status["status"] != "usable"
        )
        if not should_summarize:
            continue
        counts = series.fillna("<NA>").astype(str).value_counts(dropna=False).head(top_n)
        summaries[col] = {
            "n_unique": n_unique,
            "top_values": [
                {"value": str(idx), "count": int(val)}
                for idx, val in counts.items()
            ],
        }
    return {
        "columns": summaries,
        "n_categorical_columns_summarized": int(len(summaries)),
    }


def _robust_outlier_scan(df: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    """IQR and MAD outlier counts. Less gullible than mean/std outliers."""
    results: dict[str, Any] = {}
    for col in columns:
        if col not in df.columns:
            continue
        x = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(x) < 8 or int(x.nunique()) < 2:
            continue

        q1 = float(x.quantile(0.25))
        q3 = float(x.quantile(0.75))
        iqr = q3 - q1
        if math.isfinite(iqr) and iqr > 0.0:
            lo = q1 - 1.5 * iqr
            hi = q3 + 1.5 * iqr
            iqr_count = int(((x < lo) | (x > hi)).sum())
        else:
            # Degenerate-but-not-constant columns happen in smoke datasets:
            # many identical values plus one/few extreme rows. Treat values
            # different from the median as robust outliers instead of silently
            # reporting nothing.
            median_for_iqr = float(x.median())
            lo = hi = median_for_iqr
            iqr_count = int((x != median_for_iqr).sum())

        median = float(x.median())
        mad = float((x - median).abs().median())
        if math.isfinite(mad) and mad > 0.0:
            robust_z = 0.6745 * (x - median).abs() / mad
            mad_count = int((robust_z > 3.5).sum())
        else:
            mad_count = int((x != median).sum())

        if iqr_count > 0 or mad_count > 0:
            results[col] = {
                "iqr_outlier_count": iqr_count,
                "mad_outlier_count": mad_count,
                "iqr_lower_bound": _round_float(lo),
                "iqr_upper_bound": _round_float(hi),
                "median": _round_float(median),
                "mad": _round_float(mad),
            }
    return {
        "columns": results,
        "n_columns_with_robust_outliers": int(len(results)),
    }


def _slope_summary(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    group_cols: list[str],
    min_unique_x: int = 2,
) -> dict[str, Any]:
    """Fit y = slope*x+b by group and summarize slopes."""
    if x_col not in df.columns or y_col not in df.columns:
        return {"status": "skipped", "reason": "missing_x_or_y_column"}

    available_groups = [c for c in group_cols if c in df.columns and c != x_col and c != y_col]
    work = df[available_groups + [x_col, y_col]].copy()
    work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    work = work[work[x_col].notna() & work[y_col].notna()]
    if work.empty:
        return {"status": "skipped", "reason": "no_finite_rows"}

    iterator = work.groupby(available_groups, dropna=False) if available_groups else [((), work)]
    rows: list[dict[str, Any]] = []
    for key, sub in iterator:
        if not isinstance(key, tuple):
            key = (key,)
        if len(sub) < min_unique_x or int(sub[x_col].nunique()) < min_unique_x:
            continue
        try:
            slope, intercept = np.polyfit(sub[x_col].to_numpy(float), sub[y_col].to_numpy(float), 1)
        except Exception:
            continue
        rows.append({
            "group": {col: (None if pd.isna(val) else val) for col, val in zip(available_groups, key)},
            "n_rows": int(len(sub)),
            "x_min": _round_float(float(sub[x_col].min())),
            "x_max": _round_float(float(sub[x_col].max())),
            "slope": _round_float(float(slope)),
            "intercept": _round_float(float(intercept)),
        })

    slopes = [float(r["slope"]) for r in rows if r.get("slope") is not None]
    if not slopes:
        return {"status": "skipped", "reason": "no_evaluable_groups", "group_columns": available_groups}

    return {
        "status": "computed",
        "x_column": x_col,
        "y_column": y_col,
        "group_columns": available_groups,
        "n_groups_evaluable": int(len(slopes)),
        "slope_min": _round_float(min(slopes)),
        "slope_max": _round_float(max(slopes)),
        "slope_mean": _round_float(float(np.mean(slopes))),
        "slope_median": _round_float(float(np.median(slopes))),
        "n_positive_slopes": int(sum(s > 0 for s in slopes)),
        "n_negative_slopes": int(sum(s < 0 for s in slopes)),
        "examples": rows[:20],
    }


def _aero_physics_sanity(
    df: pd.DataFrame,
    *,
    group_column: str = "geometry_id",
) -> dict[str, Any]:
    """Lightweight aerodynamic sanity EDA. Not a QC gate; a diagnostic map."""
    report: dict[str, Any] = {}

    if "cd" in df.columns:
        cd = pd.to_numeric(df["cd"], errors="coerce")
        finite = cd.dropna()
        report["cd_sanity"] = {
            "n_finite": int(len(finite)),
            "n_nonpositive": int((finite <= 0.0).sum()),
            "min_cd": _round_float(float(finite.min())) if len(finite) else None,
            "max_cd": _round_float(float(finite.max())) if len(finite) else None,
            "passed_positive_cd_check": bool(len(finite) > 0 and int((finite <= 0.0).sum()) == 0),
        }
    else:
        report["cd_sanity"] = {"status": "skipped", "reason": "missing_cd"}

    if "cl" in df.columns and "cd" in df.columns:
        cl = pd.to_numeric(df["cl"], errors="coerce")
        cd = pd.to_numeric(df["cd"], errors="coerce")
        mask = cl.notna() & cd.notna() & (cd > 0.0)
        ld = cl[mask] / cd[mask]
        report["lift_to_drag_sanity"] = {
            "n_finite": int(len(ld)),
            "min_l_over_d": _round_float(float(ld.min())) if len(ld) else None,
            "max_l_over_d": _round_float(float(ld.max())) if len(ld) else None,
            "mean_l_over_d": _round_float(float(ld.mean())) if len(ld) else None,
        }
    else:
        report["lift_to_drag_sanity"] = {"status": "skipped", "reason": "missing_cl_or_cd"}

    alpha_groups = [group_column, "control_input_deg", "delta_e_sym_deg", "delta_a_diff_deg", "velocity_mps", "altitude_m", "beta_deg"]
    if "alpha_deg" in df.columns and "cl" in df.columns:
        report["cl_alpha_slope"] = _slope_summary(df, x_col="alpha_deg", y_col="cl", group_cols=alpha_groups)
    else:
        report["cl_alpha_slope"] = {"status": "skipped", "reason": "missing_alpha_or_cl"}

    if "alpha_deg" in df.columns and "cm" in df.columns:
        cm_alpha = _slope_summary(df, x_col="alpha_deg", y_col="cm", group_cols=alpha_groups)
        if cm_alpha.get("status") == "computed":
            n_eval = int(cm_alpha.get("n_groups_evaluable", 0) or 0)
            n_neg = int(cm_alpha.get("n_negative_slopes", 0) or 0)
            cm_alpha["expected_sign"] = "negative_for_static_pitch_stability_smoke_check"
            cm_alpha["n_groups_with_expected_negative_slope"] = n_neg
            cm_alpha["n_groups_with_nonnegative_slope"] = n_eval - n_neg
            cm_alpha["passed_expected_sign_check"] = bool(n_eval > 0 and n_neg == n_eval)
        report["cm_alpha_slope"] = cm_alpha
    else:
        report["cm_alpha_slope"] = {"status": "skipped", "reason": "missing_alpha_or_cm"}

    control_col = "delta_e_sym_deg" if "delta_e_sym_deg" in df.columns else "control_input_deg"
    control_groups = [group_column, "alpha_deg", "velocity_mps", "altitude_m", "beta_deg"]
    if control_col in df.columns and "cm" in df.columns:
        report["cm_control_slope"] = _slope_summary(df, x_col=control_col, y_col="cm", group_cols=control_groups)
    else:
        report["cm_control_slope"] = {"status": "skipped", "reason": "missing_control_or_cm"}

    return report


def _top_feature_target_relationships(
    df: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_columns: list[str],
    top_n: int = 8,
) -> dict[str, Any]:
    """Rank feature-target relationships by absolute Pearson/Spearman signal."""
    result: dict[str, Any] = {}
    for target in target_columns:
        if target not in df.columns:
            continue
        rows: list[dict[str, Any]] = []
        for feature in feature_columns:
            if feature not in df.columns:
                continue
            pearson = _safe_corr(df[feature], df[target], method="pearson", min_rows=5)
            spearman = _safe_corr(df[feature], df[target], method="spearman", min_rows=5)
            signal = max(abs(v) for v in [pearson or 0.0, spearman or 0.0])
            if signal <= 0.0:
                continue
            rows.append({
                "feature": feature,
                "pearson_r": _round_float(pearson, 4),
                "spearman_r": _round_float(spearman, 4),
                "max_abs_signal": _round_float(signal, 4),
            })
        result[target] = sorted(rows, key=lambda item: item["max_abs_signal"] or 0.0, reverse=True)[:top_n]
    return result




def _top_missing_columns(missingness: dict[str, Any], *, top_n: int = 20) -> list[dict[str, Any]]:
    """Return sorted missingness rows for the most affected columns."""
    rows: list[dict[str, Any]] = []
    for col, item in (missingness.get("by_column", {}) or {}).items():
        n_missing = int(item.get("n_missing", 0) or 0)
        if n_missing <= 0:
            continue
        rows.append({
            "column": col,
            "n_missing": n_missing,
            "missing_fraction": _round_float(item.get("missing_fraction"), 6),
        })
    return sorted(rows, key=lambda r: (r["n_missing"], r["column"]), reverse=True)[:top_n]


def _target_variability_report(df: pd.DataFrame, target_columns: list[str]) -> dict[str, Any]:
    """Report whether targets have enough finite variation to be learnable."""
    out: dict[str, Any] = {}
    for target in target_columns:
        if target not in df.columns:
            out[target] = {"status": "missing"}
            continue
        y = pd.to_numeric(df[target], errors="coerce").dropna()
        if len(y) == 0:
            out[target] = {"status": "no_finite_values", "n_finite": 0}
            continue
        std = float(y.std(ddof=1)) if len(y) > 1 else 0.0
        rng = float(y.max() - y.min()) if len(y) else 0.0
        out[target] = {
            "status": "ok" if len(y) >= 10 and y.nunique() >= 4 and std > 0 else "weak_or_degenerate",
            "n_finite": int(len(y)),
            "n_unique": int(y.nunique()),
            "min": _round_float(float(y.min())),
            "max": _round_float(float(y.max())),
            "range": _round_float(rng),
            "std": _round_float(std),
        }
    return out


def _regime_summary(
    df: pd.DataFrame,
    *,
    target_columns: list[str],
    regime_columns: list[str] | None = None,
    max_rows: int = 400,
) -> dict[str, Any]:
    """Target summaries by alpha/control/condition regime."""
    regime_columns = regime_columns or ["alpha_deg", "control_input_deg", "velocity_mps", "altitude_m"]
    available_regime_cols = [c for c in regime_columns if c in df.columns]
    available_targets = [c for c in target_columns if c in df.columns]
    if not available_regime_cols or not available_targets:
        return {"status": "skipped", "reason": "missing_regime_or_target_columns"}

    work = df[available_regime_cols + available_targets].copy()
    for col in available_targets:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    rows: list[dict[str, Any]] = []
    for key, sub in work.groupby(available_regime_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        item: dict[str, Any] = {
            "regime": {c: (None if pd.isna(v) else v) for c, v in zip(available_regime_cols, key)},
            "n_rows": int(len(sub)),
            "targets": {},
        }
        for target in available_targets:
            y = pd.to_numeric(sub[target], errors="coerce").dropna()
            item["targets"][target] = {
                "n_finite": int(len(y)),
                "mean": _round_float(float(y.mean())) if len(y) else None,
                "std": _round_float(float(y.std(ddof=1))) if len(y) > 1 else None,
                "min": _round_float(float(y.min())) if len(y) else None,
                "max": _round_float(float(y.max())) if len(y) else None,
            }
        rows.append(item)
    rows = sorted(rows, key=lambda r: tuple(str(r["regime"].get(c)) for c in available_regime_cols))
    return {
        "status": "computed",
        "regime_columns": available_regime_cols,
        "target_columns": available_targets,
        "n_regimes": int(len(rows)),
        "rows": rows[:max_rows],
        "truncated": bool(len(rows) > max_rows),
    }


def _regime_outlier_scan(
    df: pd.DataFrame,
    columns: list[str],
    *,
    regime_columns: list[str] | None = None,
    min_group_rows: int = 8,
    robust_z_threshold: float = 3.5,
) -> dict[str, Any]:
    """Outliers within alpha/control regimes instead of one global bucket."""
    regime_columns = regime_columns or ["alpha_deg", "control_input_deg"]
    available_regime_cols = [c for c in regime_columns if c in df.columns]
    scan_cols = [c for c in columns if c in df.columns]
    if not available_regime_cols or not scan_cols:
        return {"status": "skipped", "reason": "missing_regime_or_scan_columns"}

    examples: list[dict[str, Any]] = []
    counts_by_column: dict[str, int] = {c: 0 for c in scan_cols}
    n_groups_evaluable = 0
    for key, sub in df.groupby(available_regime_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        if len(sub) < min_group_rows:
            continue
        n_groups_evaluable += 1
        regime = {c: (None if pd.isna(v) else v) for c, v in zip(available_regime_cols, key)}
        for col in scan_cols:
            x = pd.to_numeric(sub[col], errors="coerce")
            finite = x.dropna()
            if len(finite) < min_group_rows or int(finite.nunique()) < 2:
                continue
            median = float(finite.median())
            mad = float((finite - median).abs().median())
            if mad > 0.0 and math.isfinite(mad):
                robust_z = 0.6745 * (finite - median).abs() / mad
                n_out = int((robust_z > robust_z_threshold).sum())
            else:
                q1 = float(finite.quantile(0.25))
                q3 = float(finite.quantile(0.75))
                iqr = q3 - q1
                if not math.isfinite(iqr) or iqr <= 0:
                    n_out = 0
                else:
                    lo = q1 - 1.5 * iqr
                    hi = q3 + 1.5 * iqr
                    n_out = int(((finite < lo) | (finite > hi)).sum())
            if n_out > 0:
                counts_by_column[col] = counts_by_column.get(col, 0) + n_out
                if len(examples) < 50:
                    examples.append({
                        "column": col,
                        "regime": regime,
                        "n_group_rows": int(len(sub)),
                        "n_outlier_rows": n_out,
                    })

    counts_by_column = {k: v for k, v in counts_by_column.items() if v > 0}
    return {
        "status": "computed",
        "regime_columns": available_regime_cols,
        "scan_columns": scan_cols,
        "min_group_rows": min_group_rows,
        "robust_z_threshold": robust_z_threshold,
        "n_groups_evaluable": int(n_groups_evaluable),
        "counts_by_column": counts_by_column,
        "n_columns_with_regime_outliers": int(len(counts_by_column)),
        "examples": examples,
    }


def _linear_fit_r2(x: np.ndarray, y: np.ndarray, degree: int) -> tuple[np.ndarray, float] | None:
    try:
        coeffs = np.polyfit(x, y, degree)
        pred = np.polyval(coeffs, x)
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
        return coeffs, r2
    except Exception:
        return None


def _polar_diagnostics(
    df: pd.DataFrame,
    *,
    group_column: str = "geometry_id",
    min_rows: int = 4,
) -> dict[str, Any]:
    """Fit CD = k*CL² + b*CL + CD0 by group to catch suspicious polar shapes."""
    if "cl" not in df.columns or "cd" not in df.columns:
        return {"status": "skipped", "reason": "missing_cl_or_cd"}
    group_cols = [c for c in [group_column, "control_input_deg", "velocity_mps", "altitude_m", "beta_deg"] if c in df.columns]
    work = df[group_cols + ["cl", "cd"]].copy()
    work["cl"] = pd.to_numeric(work["cl"], errors="coerce")
    work["cd"] = pd.to_numeric(work["cd"], errors="coerce")
    work = work[work["cl"].notna() & work["cd"].notna()]
    if work.empty:
        return {"status": "skipped", "reason": "no_finite_cl_cd_rows"}

    rows: list[dict[str, Any]] = []
    for key, sub in (work.groupby(group_cols, dropna=False) if group_cols else [((), work)]):
        if not isinstance(key, tuple):
            key = (key,)
        sub = sub.sort_values("cl")
        if len(sub) < min_rows or int(sub["cl"].nunique()) < 3:
            continue
        x = sub["cl"].to_numpy(float)
        y = sub["cd"].to_numpy(float)
        fit = _linear_fit_r2(x, y, degree=2)
        if fit is None:
            continue
        coeffs, r2 = fit
        k, b, cd0 = [float(v) for v in coeffs]
        rows.append({
            "group": {c: (None if pd.isna(v) else v) for c, v in zip(group_cols, key)},
            "n_rows": int(len(sub)),
            "cl_min": _round_float(float(np.min(x))),
            "cl_max": _round_float(float(np.max(x))),
            "cd_min": _round_float(float(np.min(y))),
            "cd_max": _round_float(float(np.max(y))),
            "k_cl2": _round_float(k),
            "linear_cl_term": _round_float(b),
            "cd0_intercept": _round_float(cd0),
            "r2": _round_float(r2),
            "flag_negative_k": bool(k < 0.0),
            "flag_low_r2": bool(r2 < 0.70),
            "flag_negative_cd0": bool(cd0 < 0.0),
        })

    if not rows:
        return {"status": "skipped", "reason": "no_evaluable_polar_groups", "group_columns": group_cols}
    return {
        "status": "computed",
        "group_columns": group_cols,
        "n_groups_evaluable": int(len(rows)),
        "n_negative_k_groups": int(sum(r["flag_negative_k"] for r in rows)),
        "n_low_r2_groups": int(sum(r["flag_low_r2"] for r in rows)),
        "n_negative_cd0_groups": int(sum(r["flag_negative_cd0"] for r in rows)),
        "r2_min": _round_float(min(float(r["r2"]) for r in rows if r.get("r2") is not None)),
        "r2_median": _round_float(float(np.median([float(r["r2"]) for r in rows if r.get("r2") is not None]))),
        "k_min": _round_float(min(float(r["k_cl2"]) for r in rows if r.get("k_cl2") is not None)),
        "k_max": _round_float(max(float(r["k_cl2"]) for r in rows if r.get("k_cl2") is not None)),
        "examples": rows[:50],
        "worst_r2_examples": sorted(rows, key=lambda r: r.get("r2") if r.get("r2") is not None else 999.0)[:20],
    }


def _slope_distribution(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    group_cols: list[str],
    min_unique_x: int = 2,
    weak_abs_slope_threshold: float = 1e-6,
) -> dict[str, Any]:
    """Slope distribution helper with weak/nonzero counts."""
    base = _slope_summary(df, x_col=x_col, y_col=y_col, group_cols=group_cols, min_unique_x=min_unique_x)
    if base.get("status") != "computed":
        return base
    available_groups = base.get("group_columns", []) or []
    work = df[available_groups + [x_col, y_col]].copy()
    work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    work = work[work[x_col].notna() & work[y_col].notna()]
    slopes: list[float] = []
    for _key, sub in (work.groupby(available_groups, dropna=False) if available_groups else [((), work)]):
        if len(sub) < min_unique_x or int(sub[x_col].nunique()) < min_unique_x:
            continue
        try:
            slope, _intercept = np.polyfit(sub[x_col].to_numpy(float), sub[y_col].to_numpy(float), 1)
            if math.isfinite(float(slope)):
                slopes.append(float(slope))
        except Exception:
            pass
    base["weak_abs_slope_threshold"] = weak_abs_slope_threshold
    base["n_weak_or_zero_slopes"] = int(sum(abs(s) <= weak_abs_slope_threshold for s in slopes))
    base["slope_abs_median"] = _round_float(float(np.median(np.abs(slopes)))) if slopes else None
    return base


def _control_effect_sanity(
    df: pd.DataFrame,
    *,
    group_column: str = "geometry_id",
) -> dict[str, Any]:
    """Control-effect slope diagnostics for CL/CD/Cm vs symmetric elevon input."""
    control_col = "delta_e_sym_deg" if "delta_e_sym_deg" in df.columns else "control_input_deg"
    if control_col not in df.columns:
        return {"status": "skipped", "reason": "missing_control_column"}
    group_cols = [c for c in [group_column, "alpha_deg", "velocity_mps", "altitude_m", "beta_deg"] if c in df.columns]
    out: dict[str, Any] = {
        "status": "computed",
        "control_column": control_col,
        "group_columns": group_cols,
    }
    for target in ["cl", "cd", "cm"]:
        if target in df.columns:
            out[f"{target}_control_slope"] = _slope_distribution(
                df,
                x_col=control_col,
                y_col=target,
                group_cols=group_cols,
                weak_abs_slope_threshold=1e-5 if target != "cd" else 1e-7,
            )
        else:
            out[f"{target}_control_slope"] = {"status": "skipped", "reason": f"missing_{target}"}
    return out


def _design_space_projection(
    df: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_columns: list[str] | None = None,
    group_column: str = "geometry_id",
    max_examples: int = 100,
) -> dict[str, Any]:
    """Two-dimensional PCA-style projection using SVD, no fitting artifact saved."""
    target_columns = target_columns or []
    usable, skipped = _correlatable_numeric_columns(df, [c for c in feature_columns if c in df.columns], min_rows=5)
    if len(usable) < 2:
        return {"status": "skipped", "reason": "fewer_than_two_usable_numeric_features", "skipped_columns": skipped}

    base_cols = [group_column] if group_column in df.columns else []
    work = df[base_cols + usable + [c for c in target_columns if c in df.columns]].copy()
    if group_column in work.columns:
        numeric_agg = {c: "median" for c in usable + [c for c in target_columns if c in df.columns]}
        work = work.groupby(group_column, dropna=False).agg(numeric_agg).reset_index()
    X = work[usable].apply(pd.to_numeric, errors="coerce")
    X = X.fillna(X.median(numeric_only=True)).fillna(0.0)
    std = X.std(ddof=1).replace(0.0, np.nan)
    Xs = ((X - X.mean()) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if len(Xs) < 2:
        return {"status": "skipped", "reason": "fewer_than_two_rows_after_grouping"}
    try:
        U, S, Vt = np.linalg.svd(Xs.to_numpy(float), full_matrices=False)
    except Exception as exc:
        return {"status": "skipped", "reason": f"svd_failed: {exc}"}
    if len(S) < 2:
        return {"status": "skipped", "reason": "svd_returned_less_than_two_components"}
    scores = U[:, :2] * S[:2]
    denom = float(np.sum(S ** 2))
    evr = (S[:2] ** 2) / denom if denom > 0 else np.array([0.0, 0.0])
    examples: list[dict[str, Any]] = []
    for i in range(min(len(work), max_examples)):
        item = {
            "sample_index": int(i),
            "pc1": _round_float(float(scores[i, 0])),
            "pc2": _round_float(float(scores[i, 1])),
        }
        if group_column in work.columns:
            item[group_column] = str(work.iloc[i][group_column])
        for target in target_columns:
            if target in work.columns:
                item[target] = _round_float(pd.to_numeric(pd.Series([work.iloc[i][target]]), errors="coerce").iloc[0])
        examples.append(item)
    return {
        "status": "computed",
        "method": "standardized_feature_svd_pca",
        "level": "geometry_group_median" if group_column in df.columns else "row_level",
        "feature_columns_used": usable,
        "skipped_columns": skipped,
        "n_samples_projected": int(len(work)),
        "explained_variance_ratio_pc1": _round_float(float(evr[0])),
        "explained_variance_ratio_pc2": _round_float(float(evr[1])),
        "examples": examples,
    }


def _learning_readiness_diagnosis(
    report: dict[str, Any],
    *,
    feature_columns: list[str],
    target_columns: list[str],
) -> dict[str, Any]:
    """Heuristic EDA-to-ML readiness notes. This is not model validation."""
    shape = report.get("shape", {}) or {}
    n_rows = int(shape.get("n_rows", 0) or 0)
    coverage = report.get("per_geometry_coverage", {}) or {}
    n_groups = int(coverage.get("n_geometries", 0) or 0)
    constants = set((report.get("constant_columns", {}) or {}).get("constant_columns", []) or [])
    constant_features = [c for c in feature_columns if c in constants]
    missing = report.get("missingness", {}) or {}
    target_variability = report.get("target_variability", {}) or {}
    relationships = report.get("top_feature_target_relationships", {}) or {}

    target_rows: dict[str, Any] = {}
    for target in target_columns:
        top = relationships.get(target, []) or []
        best_signal = top[0].get("max_abs_signal") if top else None
        variability = target_variability.get(target, {}) or {}
        issues: list[str] = []
        if variability.get("status") != "ok":
            issues.append("low_or_degenerate_target_variation")
        if best_signal is None or float(best_signal) < 0.15:
            issues.append("weak_simple_feature_target_signal")
        target_rows[target] = {
            "target_variability_status": variability.get("status"),
            "best_simple_abs_correlation_signal": best_signal,
            "status": "ready_for_baseline_ml" if not issues else "needs_attention_before_trusting_metrics",
            "issues": issues,
        }

    global_issues: list[str] = []
    if n_rows < 500:
        global_issues.append("small_row_count_for_general_surrogate")
    if n_groups < 30:
        global_issues.append("small_geometry_group_count_for_grouped_split")
    if constant_features:
        global_issues.append("constant_features_present")
    if missing.get("n_columns_with_missing", 0):
        global_issues.append("missing_values_present")
    if coverage.get("uniform_coverage") is False:
        global_issues.append("nonuniform_geometry_coverage")

    if n_groups >= 50 and n_rows >= 1000:
        scale_label = "pilot_scale"
    elif n_groups >= 10 and n_rows >= 100:
        scale_label = "canary_or_small_pilot"
    else:
        scale_label = "smoke_only"
    return {
        "status": "usable_for_pilot_baselines" if not global_issues or scale_label == "pilot_scale" else "use_only_for_smoke_or_debug",
        "scale_label": scale_label,
        "n_rows": n_rows,
        "n_groups": n_groups,
        "n_features": int(len(feature_columns)),
        "n_targets": int(len(target_columns)),
        "constant_features": constant_features,
        "global_issues": global_issues,
        "target_readiness": target_rows,
    }


def compare_eda_reports(report_paths: list[str | Path]) -> dict[str, Any]:
    """Compare multiple EDA JSON reports without recomputing EDA."""
    rows: list[dict[str, Any]] = []
    for path in report_paths:
        p = Path(path).expanduser()
        data = json.loads(p.read_text(encoding="utf-8"))
        metadata = data.get("metadata", {}) or {}
        shape = data.get("shape", {}) or {}
        physics = data.get("aero_physics_sanity", {}) or {}
        cd_sanity = physics.get("cd_sanity", {}) or {}
        polar = data.get("polar_diagnostics", {}) or {}
        readiness = data.get("learning_readiness", {}) or {}
        rows.append({
            "report_path": str(p),
            "dataset_root": metadata.get("dataset_root"),
            "schema_version": data.get("schema_version"),
            "rows": shape.get("n_rows"),
            "columns": shape.get("n_columns"),
            "groups": (data.get("per_geometry_coverage", {}) or {}).get("n_geometries"),
            "promotion_forced": metadata.get("promotion_forced"),
            "missing_columns": (data.get("missingness", {}) or {}).get("n_columns_with_missing"),
            "constant_columns": (data.get("constant_columns", {}) or {}).get("n_constant"),
            "cd_min": cd_sanity.get("min_cd"),
            "cd_max": cd_sanity.get("max_cd"),
            "nonpositive_cd_rows": cd_sanity.get("n_nonpositive"),
            "polar_low_r2_groups": polar.get("n_low_r2_groups"),
            "learning_scale_label": readiness.get("scale_label"),
            "learning_status": readiness.get("status"),
            "recommendation_count": len(data.get("operator_recommendations", []) or []),
        })
    return {
        "schema_version": "aeris.eda_comparison.v1",
        "n_reports": int(len(rows)),
        "reports": rows,
    }
def _operator_recommendations(report: dict[str, Any]) -> list[str]:
    """Plain-English operator hints derived from EDA diagnostics."""
    hints: list[str] = []
    constants = report.get("constant_columns", {}).get("constant_columns", []) or []
    feature_cols = set((report.get("metadata", {}) or {}).get("feature_columns", []) or [])
    constant_features = [c for c in constants if c in feature_cols]
    if constant_features:
        hints.append(
            "Remove or ignore constant feature columns for this dataset: "
            + ", ".join(constant_features[:12])
        )

    missing = report.get("missingness", {}) or {}
    if missing.get("n_columns_with_missing", 0) > 0:
        hints.append(
            f"Inspect missing values before training: {missing.get('n_columns_with_missing')} column(s) contain missing entries."
        )

    coverage = report.get("per_geometry_coverage", {}) or {}
    if coverage.get("uniform_coverage") is False:
        hints.append(
            "Geometry coverage is not uniform; inspect failed/incomplete geometry groups before trusting grouped-split metrics."
        )

    cd_sanity = (report.get("aero_physics_sanity", {}) or {}).get("cd_sanity", {}) or {}
    if cd_sanity.get("n_nonpositive", 0):
        hints.append("Non-positive CD values exist; this is usually a solver/data-quality red flag, not a model feature.")

    cm_alpha = (report.get("aero_physics_sanity", {}) or {}).get("cm_alpha_slope", {}) or {}
    if cm_alpha.get("status") == "computed" and cm_alpha.get("n_groups_with_nonnegative_slope", 0):
        hints.append(
            "Some Cm-alpha groups have non-negative slope; audit moment reference, sign convention, or unstable geometry regimes."
        )

    regime_outliers = report.get("regime_outliers", {}) or {}
    if regime_outliers.get("n_columns_with_regime_outliers", 0):
        hints.append(
            f"Regime-aware outliers exist in {regime_outliers.get('n_columns_with_regime_outliers')} column(s); inspect by alpha/control before deleting rows globally."
        )

    polar = report.get("polar_diagnostics", {}) or {}
    if polar.get("status") == "computed":
        if polar.get("n_low_r2_groups", 0):
            hints.append(
                f"Polar diagnostics found {polar.get('n_low_r2_groups')} CL-CD group(s) with weak parabolic fit; inspect AVL/viscous-correction behavior."
            )
        if polar.get("n_negative_k_groups", 0):
            hints.append(
                f"Polar diagnostics found {polar.get('n_negative_k_groups')} group(s) with negative CL² drag coefficient; this is suspicious for normal attached-flow polar behavior."
            )

    control = report.get("control_effect_sanity", {}) or {}
    cm_control = control.get("cm_control_slope", {}) or {}
    if cm_control.get("status") == "computed" and cm_control.get("n_weak_or_zero_slopes", 0):
        hints.append(
            f"Control-effect scan found {cm_control.get('n_weak_or_zero_slopes')} weak Cm-vs-control group(s); inspect trim authority before training flyability models."
        )

    readiness = report.get("learning_readiness", {}) or {}
    if readiness.get("global_issues"):
        hints.append("Learning-readiness warnings: " + ", ".join(readiness.get("global_issues", [])[:8]))
    for target, item in (readiness.get("target_readiness", {}) or {}).items():
        if item.get("issues"):
            hints.append(f"Target `{target}` needs attention: " + ", ".join(item.get("issues", [])[:4]))

    corr_skipped = report.get("correlation", {}).get("skipped_columns", []) or []
    if corr_skipped:
        hints.append(
            f"Correlation skipped {len(corr_skipped)} column(s), usually because they are constant, missing, or non-numeric."
        )

    if not hints:
        hints.append("No obvious EDA blockers detected. Still inspect plots before training; autopilot confidence is how bugs get tenure.")
    return hints


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
        "dtypes": _dtype_report(df),
        "missingness": _missingness_report(
            df,
            important_columns=all_cols,
            group_column=group_column,
        ),
        "categorical_summary": _categorical_summary(df),
        "constant_columns": _detect_constant_columns(df),
        "duplicates": _detect_duplicates(df),
        **_per_column_stats(df, feature_columns, "feature_stats"),
        **_per_column_stats(df, target_columns, "target_stats"),
        "target_variability": _target_variability_report(df, target_columns),
        "per_geometry_coverage": _per_geometry_coverage(df, group_column),
        "alpha_control_coverage": _alpha_control_coverage(df),
        "regime_summary": _regime_summary(df, target_columns=target_columns),
        "correlation": _correlation_matrix(df, all_cols),
        "top_feature_target_relationships": _top_feature_target_relationships(
            df,
            feature_columns=feature_columns,
            target_columns=target_columns,
        ),
        "nonlinearity": _nonlinearity_scan(df, feature_columns, target_columns),
        "outliers": _outlier_scan(df, all_cols, sigma=outlier_sigma),
        "robust_outliers": _robust_outlier_scan(df, all_cols),
        "regime_outliers": _regime_outlier_scan(df, all_cols),
        "aero_physics_sanity": _aero_physics_sanity(df, group_column=group_column),
        "polar_diagnostics": _polar_diagnostics(df, group_column=group_column),
        "control_effect_sanity": _control_effect_sanity(df, group_column=group_column),
        "design_space_projection": _design_space_projection(
            df,
            feature_columns=feature_columns,
            target_columns=target_columns,
            group_column=group_column,
        ),
    }
    report["learning_readiness"] = _learning_readiness_diagnosis(
        report,
        feature_columns=feature_columns,
        target_columns=target_columns,
    )
    report["operator_recommendations"] = _operator_recommendations(report)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report

# ---------------------------------------------------------------------------
# Promoted-dataset operator wrapper + optional plots
# ---------------------------------------------------------------------------

def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_eda_summary_markdown(report: dict[str, Any], output_path: Path) -> Path:
    """Write a compact human-readable EDA summary.

    The JSON report remains the source of truth; this markdown is for quick
    operator review in terminals, Git diffs, and the future GUI.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    shape = report.get("shape", {}) or {}
    constants = report.get("constant_columns", {}) or {}
    duplicates = report.get("duplicates", {}) or {}
    coverage = report.get("per_geometry_coverage", {}) or {}
    alpha_control = report.get("alpha_control_coverage", {}) or {}
    outliers = report.get("outliers", {}) or {}
    correlation = report.get("correlation", {}) or {}
    metadata = report.get("metadata", {}) or {}

    lines: list[str] = []
    lines.append("# AERIS ML EDA Summary")
    lines.append("")
    lines.append("## Dataset")
    lines.append(f"- dataset: `{metadata.get('dataset_root', 'unknown')}`")
    lines.append(f"- curated CSV: `{metadata.get('curated_csv_path', 'unknown')}`")
    lines.append(f"- promotion forced: `{metadata.get('promotion_forced', False)}`")
    lines.append("")
    lines.append("## Shape")
    lines.append(f"- rows: `{shape.get('n_rows')}`")
    lines.append(f"- columns: `{shape.get('n_columns')}`")
    lines.append("")
    lines.append("## Main flags")
    lines.append(f"- constant columns: `{constants.get('n_constant', 0)}`")
    if constants.get("constant_columns"):
        lines.append("  - " + ", ".join(f"`{c}`" for c in constants["constant_columns"]))
    lines.append(f"- duplicate rows: `{duplicates.get('n_duplicate_rows', 0)}`")
    lines.append(f"- columns with outliers: `{outliers.get('n_columns_with_outliers', 0)}`")
    missingness = report.get("missingness", {}) or {}
    physics = report.get("aero_physics_sanity", {}) or {}
    recommendations = report.get("operator_recommendations", []) or []
    lines.append(f"- columns with missing values: `{missingness.get('n_columns_with_missing', 0)}`")
    cd_sanity = physics.get("cd_sanity", {}) or {}
    if "n_nonpositive" in cd_sanity:
        lines.append(f"- non-positive CD rows: `{cd_sanity.get('n_nonpositive')}`")
    cm_alpha = physics.get("cm_alpha_slope", {}) or {}
    if cm_alpha.get("status") == "computed":
        lines.append(f"- Cm-alpha groups with nonnegative slope: `{cm_alpha.get('n_groups_with_nonnegative_slope', 'n/a')}`")
    regime_outliers = report.get("regime_outliers", {}) or {}
    if regime_outliers.get("status") == "computed":
        lines.append(f"- regime-outlier columns: `{regime_outliers.get('n_columns_with_regime_outliers', 0)}`")
    polar = report.get("polar_diagnostics", {}) or {}
    if polar.get("status") == "computed":
        lines.append(f"- polar groups with low parabolic-fit R²: `{polar.get('n_low_r2_groups', 0)}`")
        lines.append(f"- polar groups with negative k(CL²): `{polar.get('n_negative_k_groups', 0)}`")
    control = report.get("control_effect_sanity", {}) or {}
    cm_control = control.get("cm_control_slope", {}) or {}
    if cm_control.get("status") == "computed":
        lines.append(f"- weak Cm-control slope groups: `{cm_control.get('n_weak_or_zero_slopes', 0)}`")
    readiness = report.get("learning_readiness", {}) or {}
    if readiness:
        lines.append(f"- learning-readiness status: `{readiness.get('status', 'unknown')}`")
        lines.append(f"- learning scale label: `{readiness.get('scale_label', 'unknown')}`")
    if correlation.get("skipped_columns"):
        skipped_names = [item.get("column") for item in correlation.get("skipped_columns", []) if item.get("column")]
        lines.append(f"- correlation-skipped columns: `{len(skipped_names)}`")
        if skipped_names:
            lines.append("  - " + ", ".join(f"`{c}`" for c in skipped_names[:20]))
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- group count: `{coverage.get('n_geometries', 'n/a')}`")
    lines.append(f"- rows/group min: `{coverage.get('rows_per_geometry_min', 'n/a')}`")
    lines.append(f"- rows/group max: `{coverage.get('rows_per_geometry_max', 'n/a')}`")
    lines.append(f"- uniform coverage: `{coverage.get('uniform_coverage', 'n/a')}`")
    lines.append(f"- alpha values: `{alpha_control.get('alpha_values')}`")
    lines.append(f"- control values: `{alpha_control.get('control_input_values')}`")
    lines.append("")
    lines.append("## Operator recommendations")
    for hint in recommendations[:12]:
        lines.append(f"- {hint}")

    top_missing = _top_missing_columns(missingness, top_n=12)
    if top_missing:
        lines.append("")
        lines.append("## Missingness hotspots")
        for item in top_missing:
            lines.append(
                f"- `{item['column']}`: `{item['n_missing']}` missing "
                f"({item['missing_fraction']})"
            )

    if readiness.get("target_readiness"):
        lines.append("")
        lines.append("## Target learning-readiness")
        for target, item in readiness.get("target_readiness", {}).items():
            lines.append(
                f"- `{target}`: `{item.get('status')}`; "
                f"best simple signal=`{item.get('best_simple_abs_correlation_signal')}`; "
                f"issues=`{', '.join(item.get('issues', [])) or 'none'}`"
            )
    lines.append("")
    lines.append("## Notes")
    lines.append("- Constant feature columns are not automatically fatal, but they teach the model nothing in this dataset.")
    lines.append("- EDA is pre-split and leakage-safe: it does not fit a model and does not use validation/test information for training.")
    lines.append("- Use this report before training, comparing, tuning, or promoting ML models.")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _available_numeric_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    available: list[str] = []
    for col in columns:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() > 0:
            available.append(col)
    return available


def write_eda_plots(
    df: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_columns: list[str],
    output_dir: Path,
    group_column: str = "geometry_id",
) -> list[dict[str, Any]]:
    """Write lightweight matplotlib EDA plots.

    Plots are best-effort. If matplotlib is unavailable or a specific plot cannot
    be produced, the returned artifact list records the error instead of blocking
    the JSON EDA report.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, Any]] = []

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - depends on optional plotting stack
        return [{"kind": "plots", "status": "skipped", "reason": f"matplotlib unavailable: {exc}"}]

    def _record(path: Path, kind: str) -> None:
        artifacts.append({"kind": kind, "path": str(path), "status": "written"})

    def _record_error(kind: str, exc: Exception) -> None:
        artifacts.append({"kind": kind, "status": "failed", "reason": str(exc)})

    numeric_cols, skipped_corr_cols = _correlatable_numeric_columns(
        df,
        list(dict.fromkeys(feature_columns + target_columns)),
        min_rows=2,
    )
    if skipped_corr_cols:
        artifacts.append({
            "kind": "correlation_input_diagnostics",
            "status": "computed",
            "skipped_columns": skipped_corr_cols,
        })

    # 1) Full correlation heatmap.
    try:
        if len(numeric_cols) >= 2:
            corr = df[numeric_cols].apply(pd.to_numeric, errors="coerce").corr().fillna(0.0)
            fig, ax = plt.subplots(figsize=(max(7, 0.6 * len(numeric_cols)), max(5, 0.55 * len(numeric_cols))))
            im = ax.imshow(corr.values, vmin=-1, vmax=1)
            ax.set_xticks(range(len(numeric_cols)))
            ax.set_yticks(range(len(numeric_cols)))
            ax.set_xticklabels(numeric_cols, rotation=45, ha="right", fontsize=8)
            ax.set_yticklabels(numeric_cols, fontsize=8)
            ax.set_title("Feature/target Pearson correlation")
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            fig.tight_layout()
            path = output_dir / "correlation_heatmap.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            _record(path, "correlation_heatmap")
        else:
            artifacts.append({"kind": "correlation_heatmap", "status": "skipped", "reason": "fewer than 2 non-constant numeric columns"})
    except Exception as exc:
        _record_error("correlation_heatmap", exc)

    # 2) Feature-target correlation heatmap.
    try:
        fcols, skipped_feature_corr_cols = _correlatable_numeric_columns(df, feature_columns, min_rows=2)
        tcols, skipped_target_corr_cols = _correlatable_numeric_columns(df, target_columns, min_rows=2)
        if skipped_feature_corr_cols or skipped_target_corr_cols:
            artifacts.append({
                "kind": "feature_target_correlation_input_diagnostics",
                "status": "computed",
                "skipped_feature_columns": skipped_feature_corr_cols,
                "skipped_target_columns": skipped_target_corr_cols,
            })
        if fcols and tcols:
            corr = df[fcols + tcols].apply(pd.to_numeric, errors="coerce").corr().loc[fcols, tcols].fillna(0.0)
            fig, ax = plt.subplots(figsize=(max(5, 0.8 * len(tcols)), max(4, 0.35 * len(fcols))))
            im = ax.imshow(corr.values, vmin=-1, vmax=1, aspect="auto")
            ax.set_xticks(range(len(tcols)))
            ax.set_yticks(range(len(fcols)))
            ax.set_xticklabels(tcols, fontsize=9)
            ax.set_yticklabels(fcols, fontsize=8)
            ax.set_title("Feature-target Pearson correlation")
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            fig.tight_layout()
            path = output_dir / "feature_target_correlation.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            _record(path, "feature_target_correlation")
        else:
            artifacts.append({"kind": "feature_target_correlation", "status": "skipped", "reason": "no non-constant numeric feature/target pair"})
    except Exception as exc:
        _record_error("feature_target_correlation", exc)

    # 3) Distributions for features and targets.
    def _hist_grid(cols: list[str], title: str, filename: str, kind: str) -> None:
        cols = _available_numeric_columns(df, cols)[:12]
        if not cols:
            return
        n = len(cols)
        ncols = 3 if n >= 3 else n
        nrows = int(math.ceil(n / ncols))
        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows))
        if nrows == 1 and ncols == 1:
            axes_list = [axes]
        else:
            axes_list = list(np.array(axes).reshape(-1))
        for ax, col in zip(axes_list, cols):
            values = pd.to_numeric(df[col], errors="coerce").dropna()
            ax.hist(values, bins=min(30, max(5, int(math.sqrt(max(len(values), 1))))))
            ax.set_title(col, fontsize=9)
        for ax in axes_list[len(cols):]:
            ax.axis("off")
        fig.suptitle(title)
        fig.tight_layout()
        path = output_dir / filename
        fig.savefig(path, dpi=160)
        plt.close(fig)
        _record(path, kind)

    try:
        _hist_grid(feature_columns, "Feature distributions", "feature_distributions.png", "feature_distributions")
    except Exception as exc:
        _record_error("feature_distributions", exc)

    try:
        _hist_grid(target_columns, "Target distributions", "target_distributions.png", "target_distributions")
    except Exception as exc:
        _record_error("target_distributions", exc)

    # 4) Alpha x control coverage heatmap.
    try:
        if "alpha_deg" in df.columns and "control_input_deg" in df.columns:
            table = pd.crosstab(df["alpha_deg"], df["control_input_deg"])
            fig, ax = plt.subplots(figsize=(max(5, 0.6 * table.shape[1]), max(4, 0.45 * table.shape[0])))
            im = ax.imshow(table.values, aspect="auto")
            ax.set_xticks(range(table.shape[1]))
            ax.set_yticks(range(table.shape[0]))
            ax.set_xticklabels([str(v) for v in table.columns], rotation=45, ha="right")
            ax.set_yticklabels([str(v) for v in table.index])
            ax.set_xlabel("control_input_deg")
            ax.set_ylabel("alpha_deg")
            ax.set_title("Alpha/control row-count coverage")
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            fig.tight_layout()
            path = output_dir / "alpha_control_coverage.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            _record(path, "alpha_control_coverage")
    except Exception as exc:
        _record_error("alpha_control_coverage", exc)

    # 5) Target vs alpha scatter/mean trend.
    try:
        if "alpha_deg" in df.columns:
            tcols = _available_numeric_columns(df, target_columns)[:6]
            if tcols:
                n = len(tcols)
                fig, axes = plt.subplots(n, 1, figsize=(7, max(3, 2.8 * n)), squeeze=False)
                for ax, target in zip(axes.reshape(-1), tcols):
                    x = pd.to_numeric(df["alpha_deg"], errors="coerce")
                    y = pd.to_numeric(df[target], errors="coerce")
                    mask = x.notna() & y.notna()
                    ax.scatter(x[mask], y[mask], s=14, alpha=0.75)
                    means = pd.DataFrame({"alpha": x[mask], target: y[mask]}).groupby("alpha")[target].mean()
                    ax.plot(means.index.to_numpy(), means.to_numpy(), marker="o", linewidth=1.5)
                    ax.set_xlabel("alpha_deg")
                    ax.set_ylabel(target)
                    ax.set_title(f"{target} vs alpha")
                fig.tight_layout()
                path = output_dir / "targets_vs_alpha.png"
                fig.savefig(path, dpi=160)
                plt.close(fig)
                _record(path, "targets_vs_alpha")
    except Exception as exc:
        _record_error("targets_vs_alpha", exc)



    # 6) Aero polar: CD vs CL.
    try:
        if "cl" in df.columns and "cd" in df.columns:
            cl = pd.to_numeric(df["cl"], errors="coerce")
            cd = pd.to_numeric(df["cd"], errors="coerce")
            mask = cl.notna() & cd.notna()
            if int(mask.sum()) >= 3:
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.scatter(cd[mask], cl[mask], s=14, alpha=0.75)
                ax.set_xlabel("cd")
                ax.set_ylabel("cl")
                ax.set_title("Aero polar: CL vs CD")
                fig.tight_layout()
                path = output_dir / "aero_polar_cl_vs_cd.png"
                fig.savefig(path, dpi=160)
                plt.close(fig)
                _record(path, "aero_polar_cl_vs_cd")
    except Exception as exc:
        _record_error("aero_polar_cl_vs_cd", exc)

    # 7) Target-vs-feature scatter grid for the first useful feature/target pairs.
    try:
        fcols = _available_numeric_columns(df, feature_columns)[:6]
        tcols = _available_numeric_columns(df, target_columns)[:3]
        pairs = [(f, t) for t in tcols for f in fcols if f != t][:12]
        if pairs:
            n = len(pairs)
            ncols = 3 if n >= 3 else n
            nrows = int(math.ceil(n / ncols))
            fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows))
            axes_list = list(np.array(axes).reshape(-1)) if n > 1 else [axes]
            for ax, (feature, target) in zip(axes_list, pairs):
                x = pd.to_numeric(df[feature], errors="coerce")
                y = pd.to_numeric(df[target], errors="coerce")
                mask = x.notna() & y.notna()
                ax.scatter(x[mask], y[mask], s=10, alpha=0.65)
                ax.set_xlabel(feature, fontsize=8)
                ax.set_ylabel(target, fontsize=8)
                ax.set_title(f"{target} vs {feature}", fontsize=9)
            for ax in axes_list[len(pairs):]:
                ax.axis("off")
            fig.tight_layout()
            path = output_dir / "targets_vs_features.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            _record(path, "targets_vs_features")
    except Exception as exc:
        _record_error("targets_vs_features", exc)



    # 8) Boxplots by alpha and control for target distributions.
    def _boxplot_by_regime(regime_col: str, filename: str, kind: str) -> None:
        if regime_col not in df.columns:
            artifacts.append({"kind": kind, "status": "skipped", "reason": f"missing_{regime_col}"})
            return
        tcols = _available_numeric_columns(df, target_columns)[:3]
        if not tcols:
            artifacts.append({"kind": kind, "status": "skipped", "reason": "no_numeric_targets"})
            return
        regime_values = sorted(pd.to_numeric(df[regime_col], errors="coerce").dropna().unique().tolist())
        if len(regime_values) < 2 or len(regime_values) > 25:
            artifacts.append({"kind": kind, "status": "skipped", "reason": "too_few_or_too_many_regime_values"})
            return
        fig, axes = plt.subplots(len(tcols), 1, figsize=(max(7, 0.45 * len(regime_values)), 3.0 * len(tcols)), squeeze=False)
        for ax, target in zip(axes.reshape(-1), tcols):
            series_list = []
            labels = []
            for val in regime_values:
                mask = pd.to_numeric(df[regime_col], errors="coerce") == val
                y = pd.to_numeric(df.loc[mask, target], errors="coerce").dropna()
                if len(y):
                    series_list.append(y.to_numpy(float))
                    labels.append(str(val))
            if series_list:
                ax.boxplot(series_list, labels=labels, showfliers=True)
                ax.set_title(f"{target} by {regime_col}")
                ax.set_xlabel(regime_col)
                ax.set_ylabel(target)
                ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        path = output_dir / filename
        fig.savefig(path, dpi=160)
        plt.close(fig)
        _record(path, kind)

    try:
        _boxplot_by_regime("alpha_deg", "target_boxplots_by_alpha.png", "target_boxplots_by_alpha")
    except Exception as exc:
        _record_error("target_boxplots_by_alpha", exc)

    try:
        _boxplot_by_regime("control_input_deg", "target_boxplots_by_control.png", "target_boxplots_by_control")
    except Exception as exc:
        _record_error("target_boxplots_by_control", exc)

    # 9) Small pair plot / scatter matrix for the strongest useful columns.
    try:
        relationships = _top_feature_target_relationships(
            df,
            feature_columns=feature_columns,
            target_columns=target_columns,
            top_n=6,
        )
        chosen: list[str] = []
        for target, rows in relationships.items():
            if target in df.columns and target not in chosen:
                chosen.append(target)
            for row in rows[:2]:
                col = row.get("feature")
                if col in df.columns and col not in chosen:
                    chosen.append(col)
        chosen = _available_numeric_columns(df, chosen)[:5]
        if len(chosen) >= 2:
            data = df[chosen].apply(pd.to_numeric, errors="coerce")
            n = len(chosen)
            fig, axes = plt.subplots(n, n, figsize=(2.4 * n, 2.4 * n))
            for i, ycol in enumerate(chosen):
                for j, xcol in enumerate(chosen):
                    ax = axes[i, j]
                    if i == j:
                        vals = data[xcol].dropna()
                        ax.hist(vals, bins=min(24, max(5, int(math.sqrt(max(len(vals), 1))))))
                    else:
                        mask = data[xcol].notna() & data[ycol].notna()
                        ax.scatter(data.loc[mask, xcol], data.loc[mask, ycol], s=8, alpha=0.55)
                    if i == n - 1:
                        ax.set_xlabel(xcol, fontsize=7, rotation=0)
                    else:
                        ax.set_xticklabels([])
                    if j == 0:
                        ax.set_ylabel(ycol, fontsize=7)
                    else:
                        ax.set_yticklabels([])
            fig.suptitle("Top EDA pair plot (strongest feature-target signals)")
            fig.tight_layout()
            path = output_dir / "top_pairplot.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            _record(path, "top_pairplot")
        else:
            artifacts.append({"kind": "top_pairplot", "status": "skipped", "reason": "fewer_than_two_numeric_columns"})
    except Exception as exc:
        _record_error("top_pairplot", exc)

    # 10) PCA/SVD design-space projection plot.
    try:
        proj = _design_space_projection(
            df,
            feature_columns=feature_columns,
            target_columns=target_columns,
            group_column=group_column,
            max_examples=5000,
        )
        if proj.get("status") == "computed" and proj.get("examples"):
            ex = proj["examples"]
            pc1 = [item["pc1"] for item in ex if item.get("pc1") is not None and item.get("pc2") is not None]
            pc2 = [item["pc2"] for item in ex if item.get("pc1") is not None and item.get("pc2") is not None]
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.scatter(pc1, pc2, s=18, alpha=0.75)
            ax.set_xlabel(f"PC1 ({proj.get('explained_variance_ratio_pc1')})")
            ax.set_ylabel(f"PC2 ({proj.get('explained_variance_ratio_pc2')})")
            ax.set_title("Design-space PCA/SVD projection")
            fig.tight_layout()
            path = output_dir / "design_space_pca.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            _record(path, "design_space_pca")
        else:
            artifacts.append({"kind": "design_space_pca", "status": "skipped", "reason": proj.get("reason", "projection_not_computed")})
    except Exception as exc:
        _record_error("design_space_pca", exc)

    # 11) Regime target means as alpha x control heatmaps.
    try:
        if "alpha_deg" in df.columns and "control_input_deg" in df.columns:
            tcols = _available_numeric_columns(df, target_columns)[:3]
            if tcols:
                fig, axes = plt.subplots(1, len(tcols), figsize=(5 * len(tcols), 4), squeeze=False)
                for ax, target in zip(axes.reshape(-1), tcols):
                    pivot = df.pivot_table(index="alpha_deg", columns="control_input_deg", values=target, aggfunc="mean")
                    im = ax.imshow(pivot.values, aspect="auto")
                    ax.set_xticks(range(pivot.shape[1]))
                    ax.set_yticks(range(pivot.shape[0]))
                    ax.set_xticklabels([str(v) for v in pivot.columns], rotation=45, ha="right")
                    ax.set_yticklabels([str(v) for v in pivot.index])
                    ax.set_title(f"Mean {target} by alpha/control")
                    ax.set_xlabel("control_input_deg")
                    ax.set_ylabel("alpha_deg")
                    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
                fig.tight_layout()
                path = output_dir / "regime_target_means.png"
                fig.savefig(path, dpi=160)
                plt.close(fig)
                _record(path, "regime_target_means")
    except Exception as exc:
        _record_error("regime_target_means", exc)

    # 12) Polar fit quality diagnostic.
    try:
        polar = _polar_diagnostics(df, group_column=group_column)
        examples = polar.get("examples", []) if polar.get("status") == "computed" else []
        r2_vals = [float(x["r2"]) for x in examples if x.get("r2") is not None]
        k_vals = [float(x["k_cl2"]) for x in examples if x.get("k_cl2") is not None]
        if r2_vals or k_vals:
            fig, axes = plt.subplots(1, 2, figsize=(9, 4))
            if r2_vals:
                axes[0].hist(r2_vals, bins=min(30, max(5, int(math.sqrt(len(r2_vals))))))
                axes[0].set_title("Polar fit R²")
            if k_vals:
                axes[1].hist(k_vals, bins=min(30, max(5, int(math.sqrt(len(k_vals))))))
                axes[1].set_title("Polar k coefficient")
            fig.tight_layout()
            path = output_dir / "polar_fit_quality.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            _record(path, "polar_fit_quality")
        else:
            artifacts.append({"kind": "polar_fit_quality", "status": "skipped", "reason": polar.get("reason", "no_polar_examples")})
    except Exception as exc:
        _record_error("polar_fit_quality", exc)

    # 13) Control-effect slope diagnostic.
    try:
        control = _control_effect_sanity(df, group_column=group_column)
        if control.get("status") == "computed":
            target_keys = ["cl_control_slope", "cd_control_slope", "cm_control_slope"]
            labels = []
            medians = []
            weak = []
            for key in target_keys:
                item = control.get(key, {}) or {}
                if item.get("status") == "computed":
                    labels.append(key.replace("_control_slope", ""))
                    medians.append(float(item.get("slope_median") or 0.0))
                    weak.append(int(item.get("n_weak_or_zero_slopes") or 0))
            if labels:
                fig, ax = plt.subplots(figsize=(7, 4))
                xpos = np.arange(len(labels))
                ax.bar(xpos, medians)
                ax.set_xticks(xpos)
                ax.set_xticklabels(labels)
                ax.set_ylabel("median slope per deg control")
                ax.set_title("Control-effect slope summary")
                for x, w in zip(xpos, weak):
                    ax.text(x, medians[x] if abs(medians[x]) > 1e-12 else 0, f"weak={w}", ha="center", va="bottom", fontsize=8)
                fig.tight_layout()
                path = output_dir / "control_effect_slopes.png"
                fig.savefig(path, dpi=160)
                plt.close(fig)
                _record(path, "control_effect_slopes")
        else:
            artifacts.append({"kind": "control_effect_slopes", "status": "skipped", "reason": control.get("reason", "control_not_computed")})
    except Exception as exc:
        _record_error("control_effect_slopes", exc)

    return artifacts


def run_promoted_dataset_eda(
    *,
    dataset_root: str | Path,
    feature_columns: list[str] | None = None,
    feature_set_name: str | None = None,
    target_columns: list[str],
    group_column: str = "geometry_id",
    allow_forced: bool = False,
    outlier_sigma: float = 4.0,
    output_dir: str | Path | None = None,
    write_plots: bool = False,
) -> dict[str, Any]:
    """Run EDA on a promoted AERIS aero dataset and write operator artifacts.

    Supports direct feature columns or a named feature set. Feature-set mode
    validates raw source columns, applies declared transforms in memory, and
    runs EDA on the materialized feature frame. It does not train, split, or
    write a reusable engineered training dataset.
    """
    from aeris.dataset.promoted_dataset import load_promoted_aero_dataset
    from aeris.ml.feature_engineering import apply_feature_engineering
    from aeris.ml.feature_sets import get_feature_set, validate_feature_set_dataframe

    if feature_columns and feature_set_name:
        raise ValueError("Use either feature_columns or feature_set_name for EDA, not both.")
    if not feature_columns and not feature_set_name:
        raise ValueError("EDA requires either explicit feature_columns or a feature_set_name.")

    dataset_root_path = Path(dataset_root).expanduser().resolve()
    context = load_promoted_aero_dataset(
        dataset_root=dataset_root_path,
        allow_forced=allow_forced,
    )
    df = context["dataframe"]
    curated_csv = Path(context["curated_aero_dataset_csv"]).expanduser().resolve()

    eda_df = df
    if feature_set_name:
        feature_set = get_feature_set(feature_set_name)
        validation = validate_feature_set_dataframe(
            df,
            feature_set=feature_set,
            target_columns=target_columns,
            group_column=group_column,
            require_group_column=bool(group_column),
        )
        if not validation.passed:
            errors = [issue.to_dict() for issue in validation.errors]
            raise ValueError(
                f"Feature-set EDA validation failed for '{feature_set.name}': {errors}"
            )
        eda_df, transform_manifest = apply_feature_engineering(
            df,
            transforms=list(feature_set.transforms),
        )
        final_feature_columns = list(feature_set.columns)
        feature_set_provenance: dict[str, Any] = {
            "feature_set_name": feature_set.name,
            "feature_set_applied": True,
            "feature_set": feature_set.to_dict(),
            "raw_source_columns": list(feature_set.raw_columns),
            "engineered_columns": list(feature_set.engineered_columns),
            "final_feature_columns": final_feature_columns,
            "transforms_requested": list(feature_set.transforms),
            "transform_manifest": transform_manifest,
            "validation": validation.to_dict(),
        }
    else:
        final_feature_columns = list(feature_columns or [])
        feature_set_provenance = {
            "feature_set_name": None,
            "feature_set_applied": False,
            "feature_set": None,
            "raw_source_columns": final_feature_columns,
            "engineered_columns": [],
            "final_feature_columns": final_feature_columns,
            "transforms_requested": [],
            "transform_manifest": None,
            "validation": None,
        }

    out_dir = Path(output_dir).expanduser().resolve() if output_dir is not None else dataset_root_path / "eda"
    plots_dir = out_dir / "plots"
    report_path = out_dir / "eda_report.json"
    summary_path = out_dir / "eda_summary.md"

    report = run_eda(
        eda_df,
        feature_columns=final_feature_columns,
        target_columns=target_columns,
        group_column=group_column,
        outlier_sigma=outlier_sigma,
        output_path=None,
    )
    report["feature_set"] = feature_set_provenance
    report["metadata"] = {
        "dataset_root": str(dataset_root_path),
        "curated_csv_path": str(curated_csv),
        "row_count": int(report.get("shape", {}).get("n_rows", len(eda_df))),
        "column_count": int(report.get("shape", {}).get("n_columns", len(eda_df.columns))),
        "promotion_manifest_path": context.get("promotion_manifest_path"),
        "promotion_forced": bool((context.get("promotion_manifest", {}) or {}).get("promotion_forced", False)),
        "feature_columns": list(final_feature_columns),
        "target_columns": list(target_columns),
        "group_column": group_column,
        "outlier_sigma": outlier_sigma,
        "feature_set_name": feature_set_provenance["feature_set_name"],
        "feature_set_applied": feature_set_provenance["feature_set_applied"],
        "raw_source_columns": feature_set_provenance["raw_source_columns"],
        "engineered_columns": feature_set_provenance["engineered_columns"],
        "final_feature_columns": feature_set_provenance["final_feature_columns"],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    _json_dump(report_path, report)
    write_eda_summary_markdown(report, summary_path)

    plot_artifacts: list[dict[str, Any]] = []
    if write_plots:
        plot_artifacts = write_eda_plots(
            eda_df,
            feature_columns=final_feature_columns,
            target_columns=target_columns,
            output_dir=plots_dir,
            group_column=group_column,
        )
        report["plot_artifacts"] = plot_artifacts
        _json_dump(report_path, report)

    return {
        "dataset_root": dataset_root_path,
        "curated_csv": curated_csv,
        "output_dir": out_dir,
        "report_path": report_path,
        "summary_path": summary_path,
        "plots_dir": plots_dir if write_plots else None,
        "plot_artifacts": plot_artifacts,
        "report": report,
    }

