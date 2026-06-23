from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Sequence

import numpy as np
import pandas as pd

from aeris.dataset.splitting import split_dataset
from aeris.ml.learning_curves import (
    _evaluate_model,
    _flatten_metrics_row,
    _make_output_dir,
    _stats,
    _to_jsonable,
    _write_csv,
    _write_json,
    parse_int_csv,
    resolve_target_columns_for_dataset,
)
from aeris.ml.model_registry import build_model, get_model_spec
from aeris.ml.learning_curves import _materialize_dataset_for_learning_curves


REPEATED_GROUPED_CV_SCHEMA_VERSION = "aeris.repeated_grouped_cv.v1"


def _classify_cv_target(row: dict[str, Any]) -> str:
    r2 = row.get("test_r2_mean")
    std = row.get("test_r2_std")
    gap = row.get("train_test_r2_gap_mean")
    if r2 is None:
        return "unknown"
    r2 = float(r2)
    std = 0.0 if std is None else float(std)
    gap = 0.0 if gap is None else float(gap)
    if r2 < 0.5:
        return "weak"
    if r2 < 0.8:
        return "moderate"
    if gap > 0.25:
        return "overfit_risk"
    if std > 0.10:
        return "unstable"
    return "strong_stable"


def _target_recommendation(target: str, row: dict[str, Any]) -> str:
    state = row.get("cv_state", "unknown")
    r2 = row.get("test_r2_mean")
    std = row.get("test_r2_std")
    gap = row.get("train_test_r2_gap_mean")
    value = "unknown" if r2 is None else f"{float(r2):.3f}"
    spread = "unknown" if std is None else f"{float(std):.3f}"
    gap_s = "unknown" if gap is None else f"{float(gap):.3f}"
    if state == "weak":
        return f"Target '{target}' is weak across repeated grouped CV (test R²={value}); do not promote this target before feature/regime diagnosis."
    if state == "moderate":
        return f"Target '{target}' is moderate across repeated grouped CV (test R²={value}); useful for pilot insight but not strong evidence yet."
    if state == "overfit_risk":
        return f"Target '{target}' has strong mean score but a large train-test gap ({gap_s}); inspect overfit or geometry-distribution mismatch."
    if state == "unstable":
        return f"Target '{target}' has good mean score but high split variability (test R² std={spread}); run more geometries or repeated splits."
    if state == "strong_stable":
        return f"Target '{target}' is strong and stable across grouped splits (test R²={value}, std={spread})."
    return f"Target '{target}' could not be classified; inspect repeated-CV rows."


def _build_overall_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    computed = [r for r in rows if r.get("status") == "computed"]
    out: dict[str, Any] = {"n_runs": len(computed)}
    for split_name in ["train", "val", "test"]:
        for metric in ["r2_mean", "rmse_mean", "mae_mean", "max_abs_error_mean"]:
            s = _stats(r.get(f"{split_name}_{metric}") for r in computed)
            out[f"{split_name}_{metric}_mean"] = s["mean"]
            out[f"{split_name}_{metric}_std"] = s["std"]
            out[f"{split_name}_{metric}_min"] = s["min"]
            out[f"{split_name}_{metric}_max"] = s["max"]
    if out.get("train_r2_mean_mean") is not None and out.get("test_r2_mean_mean") is not None:
        out["train_test_r2_gap_mean"] = float(out["train_r2_mean_mean"]) - float(out["test_r2_mean_mean"])
    else:
        out["train_test_r2_gap_mean"] = None
    return out


def _build_per_target_summary(rows: list[dict[str, Any]], target_columns: list[str]) -> list[dict[str, Any]]:
    computed = [r for r in rows if r.get("status") == "computed"]
    out: list[dict[str, Any]] = []
    for target in target_columns:
        row: dict[str, Any] = {"target": target, "n_runs": len(computed)}
        for split_name in ["train", "val", "test"]:
            for metric in ["r2", "rmse", "mae", "max_abs_error"]:
                key = f"{split_name}_{metric}__{target}"
                s = _stats(r.get(key) for r in computed)
                row[f"{split_name}_{metric}_mean"] = s["mean"]
                row[f"{split_name}_{metric}_std"] = s["std"]
                row[f"{split_name}_{metric}_min"] = s["min"]
                row[f"{split_name}_{metric}_max"] = s["max"]
        if row.get("train_r2_mean") is not None and row.get("test_r2_mean") is not None:
            row["train_test_r2_gap_mean"] = float(row["train_r2_mean"]) - float(row["test_r2_mean"])
        else:
            row["train_test_r2_gap_mean"] = None
        row["cv_state"] = _classify_cv_target(row)
        row["recommendation"] = _target_recommendation(target, row)
        out.append(row)
    return out


def _recommendations(overall: dict[str, Any], per_target: list[dict[str, Any]]) -> list[str]:
    recs: list[str] = []
    test_r2 = overall.get("test_r2_mean_mean")
    test_std = overall.get("test_r2_mean_std")
    gap = overall.get("train_test_r2_gap_mean")
    if test_r2 is None:
        recs.append("No repeated-CV score was computed. Check split sizes and selected targets.")
    elif float(test_r2) >= 0.8:
        recs.append(f"Overall repeated grouped-CV test R² is strong ({float(test_r2):.3f}); inspect per-target stability before promotion.")
    elif float(test_r2) >= 0.5:
        recs.append(f"Overall repeated grouped-CV test R² is moderate ({float(test_r2):.3f}); keep as pilot evidence, not final evidence.")
    else:
        recs.append(f"Overall repeated grouped-CV test R² is weak ({float(test_r2):.3f}); do not promote before diagnosis.")
    if test_std is not None and float(test_std) > 0.10:
        recs.append(f"Overall score varies strongly across grouped splits (test R² std={float(test_std):.3f}); increase geometry count or inspect family leakage/distribution shift.")
    if gap is not None and float(gap) > 0.25:
        recs.append(f"Overall train-test R² gap is large ({float(gap):.3f}); possible overfit or grouped-distribution mismatch.")
    for row in per_target:
        recs.append(str(row.get("recommendation")))
    return recs


def _write_summary_markdown(path: Path, report: dict[str, Any]) -> None:
    cfg = report.get("config", {})
    overall = report.get("overall_summary", {})
    lines: list[str] = [
        "# AERIS Repeated Grouped CV Summary",
        "",
        "## Run",
        f"- dataset: `{cfg.get('dataset_path')}`",
        f"- model_type: `{cfg.get('model_type')}`",
        f"- group_column: `{cfg.get('group_column')}`",
        f"- seeds: `{cfg.get('seeds')}`",
        f"- targets: `{cfg.get('target_columns')}`",
        "",
        "## Overall repeated-CV result",
        f"- runs: `{overall.get('n_runs')}`",
        f"- test R² mean/std: `{overall.get('test_r2_mean_mean')}` / `{overall.get('test_r2_mean_std')}`",
        f"- test RMSE mean/std: `{overall.get('test_rmse_mean_mean')}` / `{overall.get('test_rmse_mean_std')}`",
        f"- train-test R² gap mean: `{overall.get('train_test_r2_gap_mean')}`",
        "",
        "## Per-target stability",
    ]
    per_target = report.get("per_target_summary", [])
    if per_target:
        lines.append("| target | state | test R² mean | test R² std | test RMSE mean | train-test gap | recommendation |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for row in per_target:
            lines.append(
                f"| {row.get('target')} | {row.get('cv_state')} | {row.get('test_r2_mean')} | {row.get('test_r2_std')} | {row.get('test_rmse_mean')} | {row.get('train_test_r2_gap_mean')} | {row.get('recommendation')} |"
            )
    else:
        lines.append("- no per-target summary available")
    lines.append("")
    lines.append("## Recommendations")
    for rec in report.get("operator_recommendations", []):
        lines.append(f"- {rec}")
    lines.append("")
    lines.append("## Notes")
    lines.append("- Repeated grouped CV repeats leakage-safe geometry-level splits across seeds.")
    lines.append("- Use this after learning curves: learning curves test data need; repeated CV tests score stability.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plot_repeated_cv(summary: dict[str, Any], per_target: list[dict[str, Any]], rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt

        if per_target:
            labels = [str(r.get("target")) for r in per_target]
            xs = np.arange(len(labels))
            means = [np.nan if r.get("test_r2_mean") is None else float(r.get("test_r2_mean")) for r in per_target]
            stds = [0.0 if r.get("test_r2_std") is None else float(r.get("test_r2_std")) for r in per_target]
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.bar(xs, means, yerr=stds, capsize=4)
            ax.axhline(0.8, linewidth=1, linestyle="--")
            ax.axhline(0.5, linewidth=1, linestyle=":")
            ax.set_xticks(xs)
            ax.set_xticklabels(labels, rotation=30, ha="right")
            ax.set_ylabel("Repeated grouped-CV test R²")
            ax.set_title("Per-target repeated grouped-CV stability")
            ax.grid(True, axis="y", alpha=0.3)
            fig.tight_layout()
            path = plots_dir / "per_target_repeated_cv_r2.png"
            fig.savefig(path, dpi=180)
            plt.close(fig)
            artifacts.append({"kind": "per_target_repeated_cv_r2", "status": "written", "path": str(path)})

        computed = [r for r in rows if r.get("status") == "computed"]
        if computed:
            seeds = [int(r.get("seed")) for r in computed]
            scores = [np.nan if r.get("test_r2_mean") is None else float(r.get("test_r2_mean")) for r in computed]
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.plot(seeds, scores, marker="o")
            ax.axhline(float(summary.get("test_r2_mean_mean") or np.nan), linewidth=1, linestyle="--")
            ax.set_xlabel("Seed")
            ax.set_ylabel("Overall test R²")
            ax.set_title("Repeated grouped-CV score variability")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            path = plots_dir / "split_score_variability.png"
            fig.savefig(path, dpi=180)
            plt.close(fig)
            artifacts.append({"kind": "split_score_variability", "status": "written", "path": str(path)})
    except Exception as exc:  # pragma: no cover - plotting should not block reports
        artifacts.append({"kind": "plot_error", "status": "failed", "reason": str(exc)})
    return artifacts


def run_repeated_grouped_cv(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str = "extra_trees",
    seeds: Sequence[int] = (101, 202, 303, 404, 505),
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    allow_forced: bool = False,
    model_params: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    write_plots: bool = True,
    feature_set_name: str | None = None,
    feature_preset_name: str | None = None,
) -> dict[str, Any]:
    """Run repeated grouped train/val/test splits and summarize score stability."""
    dataset_path = Path(dataset_path).expanduser().resolve()
    seeds = parse_int_csv(list(seeds), option_name="seeds")
    spec = get_model_spec(model_type)
    if output_dir is None:
        output_dir = dataset_path / "repeated_grouped_cv"
    else:
        output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    df, final_features, materialization = _materialize_dataset_for_learning_curves(
        dataset_path=dataset_path,
        feature_columns=feature_columns,
        target_columns=target_columns,
        allow_forced=allow_forced,
        feature_set_name=feature_set_name,
        group_column=group_column,
    )

    rows: list[dict[str, Any]] = []
    split_metadata: list[dict[str, Any]] = []
    for seed in seeds:
        split = split_dataset(
            df,
            method="grouped",  # type: ignore[arg-type]
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=int(seed),
        )
        split_metadata.append({"seed": int(seed), "metadata": split.metadata})
        row: dict[str, Any] = {
            "seed": int(seed),
            "status": "computed",
            "n_train_rows": int(len(split.train_df)),
            "n_val_rows": int(len(split.val_df)),
            "n_test_rows": int(len(split.test_df)),
            "n_train_groups": int(split.train_df[group_column].nunique()) if group_column in split.train_df.columns else None,
            "n_val_groups": int(split.val_df[group_column].nunique()) if group_column in split.val_df.columns else None,
            "n_test_groups": int(split.test_df[group_column].nunique()) if group_column in split.test_df.columns else None,
        }
        model = build_model(model_type=model_type, random_seed=int(seed), model_params=model_params)
        metrics = _evaluate_model(
            model=model,
            train_df=split.train_df,
            val_df=split.val_df,
            test_df=split.test_df,
            feature_columns=final_features,
            target_columns=target_columns,
        )
        row.update(_flatten_metrics_row(prefix="train", metrics=metrics, target_columns=target_columns))
        row.update(_flatten_metrics_row(prefix="val", metrics=metrics, target_columns=target_columns))
        row.update(_flatten_metrics_row(prefix="test", metrics=metrics, target_columns=target_columns))
        rows.append(row)

    overall_summary = _build_overall_summary(rows)
    per_target_summary = _build_per_target_summary(rows, target_columns)
    plot_artifacts = _plot_repeated_cv(overall_summary, per_target_summary, rows, output_dir) if write_plots else []

    rows_csv = output_dir / "repeated_grouped_cv.csv"
    summary_csv = output_dir / "repeated_grouped_cv_summary.csv"
    per_target_csv = output_dir / "repeated_grouped_cv_per_target_summary.csv"
    report_json = output_dir / "repeated_grouped_cv_report.json"
    summary_md = output_dir / "repeated_grouped_cv_summary.md"

    report: dict[str, Any] = {
        "schema_version": REPEATED_GROUPED_CV_SCHEMA_VERSION,
        "status": "completed",
        "config": {
            "dataset_path": str(dataset_path),
            "feature_columns": list(final_features),
            "target_columns": list(target_columns),
            "feature_set_name": feature_set_name,
            "feature_preset_name": feature_preset_name,
            "model_type": model_type,
            "model_display_name": spec.display_name,
            "model_family_name": spec.family_name,
            "model_params": dict(model_params or {}),
            "group_column": group_column,
            "seeds": list(seeds),
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "allow_forced": allow_forced,
        },
        "shape": {
            "n_rows": int(len(df)),
            "n_features": int(len(final_features)),
            "n_targets": int(len(target_columns)),
            "n_groups": int(df[group_column].nunique()) if group_column in df.columns else None,
        },
        "materialization": materialization,
        "split_metadata": split_metadata,
        "rows": rows,
        "overall_summary": overall_summary,
        "per_target_summary": per_target_summary,
        "operator_recommendations": _recommendations(overall_summary, per_target_summary),
        "plot_artifacts": plot_artifacts,
        "artifacts": {
            "output_dir": str(output_dir),
            "repeated_grouped_cv_csv": str(rows_csv),
            "repeated_grouped_cv_summary_csv": str(summary_csv),
            "repeated_grouped_cv_per_target_summary_csv": str(per_target_csv),
            "repeated_grouped_cv_report_json": str(report_json),
            "repeated_grouped_cv_summary_md": str(summary_md),
            "plots_dir": str(output_dir / "plots") if write_plots else None,
        },
    }
    _write_csv(rows_csv, rows)
    _write_csv(summary_csv, [overall_summary])
    _write_csv(per_target_csv, per_target_summary)
    _write_summary_markdown(summary_md, report)
    _write_json(report_json, report)
    return report
