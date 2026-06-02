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
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- group count: `{coverage.get('n_geometries', 'n/a')}`")
    lines.append(f"- rows/group min: `{coverage.get('rows_per_geometry_min', 'n/a')}`")
    lines.append(f"- rows/group max: `{coverage.get('rows_per_geometry_max', 'n/a')}`")
    lines.append(f"- uniform coverage: `{coverage.get('uniform_coverage', 'n/a')}`")
    lines.append(f"- alpha values: `{alpha_control.get('alpha_values')}`")
    lines.append(f"- control values: `{alpha_control.get('control_input_values')}`")
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

    numeric_cols = _available_numeric_columns(df, list(dict.fromkeys(feature_columns + target_columns)))

    # 1) Full correlation heatmap.
    try:
        if len(numeric_cols) >= 2:
            corr = df[numeric_cols].apply(pd.to_numeric, errors="coerce").corr()
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
    except Exception as exc:
        _record_error("correlation_heatmap", exc)

    # 2) Feature-target correlation heatmap.
    try:
        fcols = _available_numeric_columns(df, feature_columns)
        tcols = _available_numeric_columns(df, target_columns)
        if fcols and tcols:
            corr = df[fcols + tcols].apply(pd.to_numeric, errors="coerce").corr().loc[fcols, tcols]
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

    return artifacts


def run_promoted_dataset_eda(
    *,
    dataset_root: str | Path,
    feature_columns: list[str],
    target_columns: list[str],
    group_column: str = "geometry_id",
    allow_forced: bool = False,
    outlier_sigma: float = 4.0,
    output_dir: str | Path | None = None,
    write_plots: bool = False,
) -> dict[str, Any]:
    """Run EDA on a promoted AERIS aero dataset and write operator artifacts.

    This is the CLI/GUI-friendly wrapper around run_eda(). It resolves the
    promoted dataset, loads the curated CSV path from promotion_manifest.json,
    writes JSON/Markdown reports, and optionally writes basic plots.
    """
    from aeris.dataset.promoted_dataset import load_promoted_aero_dataset

    dataset_root_path = Path(dataset_root).expanduser().resolve()
    context = load_promoted_aero_dataset(
        dataset_root=dataset_root_path,
        allow_forced=allow_forced,
    )
    df = context["dataframe"]
    curated_csv = Path(context["curated_aero_dataset_csv"]).expanduser().resolve()

    out_dir = Path(output_dir).expanduser().resolve() if output_dir is not None else dataset_root_path / "eda"
    plots_dir = out_dir / "plots"
    report_path = out_dir / "eda_report.json"
    summary_path = out_dir / "eda_summary.md"

    report = run_eda(
        df,
        feature_columns=feature_columns,
        target_columns=target_columns,
        group_column=group_column,
        outlier_sigma=outlier_sigma,
        output_path=None,
    )
    report["metadata"] = {
        "dataset_root": str(dataset_root_path),
        "curated_csv_path": str(curated_csv),
        "promotion_manifest_path": context.get("promotion_manifest_path"),
        "promotion_forced": bool((context.get("promotion_manifest", {}) or {}).get("promotion_forced", False)),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "group_column": group_column,
        "outlier_sigma": outlier_sigma,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    _json_dump(report_path, report)
    write_eda_summary_markdown(report, summary_path)

    plot_artifacts: list[dict[str, Any]] = []
    if write_plots:
        plot_artifacts = write_eda_plots(
            df,
            feature_columns=feature_columns,
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

