from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from aeris.dataset.splitting import split_dataset
from aeris.ml.learning_curves import (
    _materialize_dataset_for_learning_curves,
    parse_int_csv,
)
from aeris.ml.model_registry import build_model, get_model_spec


PER_REGIME_RESIDUALS_SCHEMA_VERSION = "aeris.per_regime_residuals.v1"


def parse_regime_columns(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return ["alpha_deg", "control_input_deg"]
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
    else:
        parts = [str(v).strip() for v in value if str(v).strip()]
    if not parts:
        return ["alpha_deg", "control_input_deg"]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            out.append(part)
    return out


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        return v if np.isfinite(v) else None
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_to_jsonable(payload), indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _to_jsonable(row.get(k)) for k in fieldnames})


def _finite_values(values: Iterable[Any]) -> list[float]:
    out: list[float] = []
    for value in values:
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(v):
            out.append(v)
    return out


def _stats(values: Iterable[Any]) -> dict[str, float | int | None]:
    vals = _finite_values(values)
    if not vals:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
    return {
        "n": int(len(vals)),
        "mean": float(mean(vals)),
        "std": float(pstdev(vals)) if len(vals) > 1 else 0.0,
        "min": float(min(vals)),
        "max": float(max(vals)),
    }


def _rmse(values: Iterable[Any]) -> float | None:
    vals = _finite_values(values)
    if not vals:
        return None
    return float(np.sqrt(np.mean(np.square(vals))))


def _mae(values: Iterable[Any]) -> float | None:
    vals = _finite_values(values)
    if not vals:
        return None
    return float(np.mean(np.abs(vals)))


def _make_output_dir(dataset_path: Path, output_dir: Path | None) -> Path:
    if output_dir is None:
        out = dataset_path / "per_regime_residuals"
    else:
        out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def _existing_regime_columns(df: pd.DataFrame, requested: Sequence[str], group_column: str) -> tuple[list[str], list[str]]:
    """Return only explicitly requested regime columns that exist.

    The grouped split column is intentionally not appended automatically.
    For per-regime residuals, geometry_id is a split/leakage-control key, not
    normally a regime bucket. Operators can still request it explicitly with:
    --regime-columns alpha_deg,control_input_deg,geometry_id
    """
    del group_column  # kept for API compatibility and future explicit geometry diagnostics.
    existing = [c for c in requested if c in df.columns]
    skipped = [c for c in requested if c not in df.columns]
    return existing, skipped


def _fit_predict_residual_rows(
    *,
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    regime_columns: list[str],
    group_column: str,
    model_type: str,
    model_params: dict[str, Any] | None,
    seeds: list[int],
    train_fraction: float,
    val_fraction: float,
    test_fraction: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    residual_rows: list[dict[str, Any]] = []
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
        train_df = split.train_df.copy()
        test_df = split.test_df.copy()
        model = build_model(model_type=model_type, random_seed=int(seed), model_params=model_params)
        X_train = train_df[feature_columns].to_numpy(dtype=float)
        y_train = train_df[target_columns].to_numpy(dtype=float)
        model.fit(X_train, y_train)

        X_test = test_df[feature_columns].to_numpy(dtype=float)
        y_test = test_df[target_columns].to_numpy(dtype=float)
        y_pred = np.asarray(model.predict(X_test), dtype=float)
        if y_pred.ndim == 1:
            y_pred = y_pred.reshape(-1, 1)

        for row_pos, (_, source_row) in enumerate(test_df.reset_index(drop=False).iterrows()):
            base: dict[str, Any] = {
                "seed": int(seed),
                "source_index": _to_jsonable(source_row.get("index")),
            }
            for col in regime_columns:
                base[col] = _to_jsonable(source_row.get(col))
            for target_idx, target in enumerate(target_columns):
                actual = float(y_test[row_pos, target_idx])
                pred = float(y_pred[row_pos, target_idx])
                residual = pred - actual
                residual_rows.append(
                    {
                        **base,
                        "target": target,
                        "actual": actual,
                        "prediction": pred,
                        "residual": residual,
                        "abs_error": abs(residual),
                        "squared_error": residual * residual,
                    }
                )
    return residual_rows, split_metadata


def _summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    residuals = [r.get("residual") for r in rows]
    abs_errors = [r.get("abs_error") for r in rows]
    squared_errors = [r.get("squared_error") for r in rows]
    actual = [r.get("actual") for r in rows]
    pred = [r.get("prediction") for r in rows]
    residual_stats = _stats(residuals)
    return {
        "n": int(len(rows)),
        "bias_mean": residual_stats["mean"],
        "residual_std": residual_stats["std"],
        "mae": _mae(abs_errors),
        "rmse": float(np.sqrt(float(mean(_finite_values(squared_errors))))) if _finite_values(squared_errors) else None,
        "max_abs_error": _stats(abs_errors)["max"],
        "actual_mean": _stats(actual)["mean"],
        "prediction_mean": _stats(pred)["mean"],
    }


def _build_target_summary(residual_rows: list[dict[str, Any]], target_columns: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for target in target_columns:
        rows = [r for r in residual_rows if r.get("target") == target]
        summary = _summarize_group(rows)
        state = _classify_target_residuals(summary)
        out.append({"target": target, **summary, "residual_state": state, "recommendation": _target_recommendation(target, summary, state)})
    return out


def _regime_key(row: dict[str, Any], target: str, regime_columns: list[str]) -> tuple[Any, ...]:
    return tuple([target] + [row.get(col) for col in regime_columns])


def _build_regime_summary(residual_rows: list[dict[str, Any]], regime_columns: list[str], min_count: int) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in residual_rows:
        key = _regime_key(row, str(row.get("target")), regime_columns)
        groups.setdefault(key, []).append(row)

    out: list[dict[str, Any]] = []
    for key, rows in groups.items():
        if len(rows) < min_count:
            continue
        target = key[0]
        payload: dict[str, Any] = {"target": target}
        for col, value in zip(regime_columns, key[1:]):
            payload[col] = value
        payload.update(_summarize_group(rows))
        out.append(payload)
    out.sort(key=lambda r: (float(r.get("rmse") or -1.0), float(r.get("mae") or -1.0)), reverse=True)
    return out


def _classify_target_residuals(summary: dict[str, Any]) -> str:
    rmse = summary.get("rmse")
    mae = summary.get("mae")
    bias = summary.get("bias_mean")
    actual_mean = summary.get("actual_mean")
    if rmse is None:
        return "unknown"
    rmse_f = float(rmse)
    scale = abs(float(actual_mean)) if actual_mean is not None and np.isfinite(float(actual_mean)) else 1.0
    normalized = rmse_f / max(scale, 1e-9)
    bias_ratio = abs(float(bias or 0.0)) / max(rmse_f, 1e-9)
    if normalized > 0.75:
        return "large_residuals"
    if bias_ratio > 0.5 and mae is not None:
        return "biased"
    return "acceptable"


def _target_recommendation(target: str, summary: dict[str, Any], state: str) -> str:
    rmse = summary.get("rmse")
    bias = summary.get("bias_mean")
    if state == "large_residuals":
        return f"Target '{target}' has large residuals (RMSE={rmse}); inspect worst alpha/control regimes and consider target-specific features/modeling."
    if state == "biased":
        return f"Target '{target}' residuals are biased (mean residual={bias}); inspect calibration and regime coverage."
    if state == "acceptable":
        return f"Target '{target}' residuals look acceptable at this pilot scale; inspect worst regimes before promotion."
    return f"Target '{target}' residual state is unknown; inspect residual rows."


def _recommendations(target_summary: list[dict[str, Any]], regime_summary: list[dict[str, Any]], regime_columns: list[str]) -> list[str]:
    recs: list[str] = []
    weak = [r for r in target_summary if r.get("residual_state") in {"large_residuals", "biased"}]
    if weak:
        recs.append("Some targets show residual risk: " + ", ".join(str(r.get("target")) for r in weak[:8]) + ".")
    if regime_summary:
        worst = regime_summary[0]
        regime_desc = ", ".join(f"{c}={worst.get(c)}" for c in regime_columns if c in worst)
        recs.append(f"Worst residual regime: target={worst.get('target')}, {regime_desc}, RMSE={worst.get('rmse')}.")
    if not recs:
        recs.append("No major residual issues detected by this pilot per-regime residual scan.")
    return recs


def _plot_residuals(
    *,
    target_summary: list[dict[str, Any]],
    regime_summary: list[dict[str, Any]],
    residual_rows: list[dict[str, Any]],
    regime_columns: list[str],
    output_dir: Path,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        return [{"kind": "plot_backend", "status": "skipped", "reason": str(exc)}]

    if target_summary:
        labels = [str(r["target"]) for r in target_summary]
        rmse = [float(r.get("rmse") or 0.0) for r in target_summary]
        fig, ax = plt.subplots(figsize=(max(7, len(labels) * 0.65), 4.5))
        ax.bar(labels, rmse)
        ax.set_ylabel("RMSE")
        ax.set_title("Per-target residual RMSE")
        ax.tick_params(axis="x", labelrotation=45)
        fig.tight_layout()
        path = plots_dir / "per_target_residual_rmse.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        artifacts.append({"kind": "per_target_residual_rmse", "path": str(path), "status": "written"})

        bias = [float(r.get("bias_mean") or 0.0) for r in target_summary]
        fig, ax = plt.subplots(figsize=(max(7, len(labels) * 0.65), 4.5))
        ax.bar(labels, bias)
        ax.axhline(0.0, linewidth=1.0)
        ax.set_ylabel("Mean residual (prediction - actual)")
        ax.set_title("Per-target residual bias")
        ax.tick_params(axis="x", labelrotation=45)
        fig.tight_layout()
        path = plots_dir / "per_target_residual_bias.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        artifacts.append({"kind": "per_target_residual_bias", "path": str(path), "status": "written"})

    if len(residual_rows) > 0:
        sample = residual_rows[:5000]
        fig, ax = plt.subplots(figsize=(6.5, 5.0))
        ax.scatter([r["actual"] for r in sample], [r["residual"] for r in sample], s=8, alpha=0.45)
        ax.axhline(0.0, linewidth=1.0)
        ax.set_xlabel("Actual")
        ax.set_ylabel("Residual (prediction - actual)")
        ax.set_title("Residuals vs actual values")
        fig.tight_layout()
        path = plots_dir / "residuals_vs_actual.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        artifacts.append({"kind": "residuals_vs_actual", "path": str(path), "status": "written"})

    if {"alpha_deg", "control_input_deg"}.issubset(set(regime_columns)) and regime_summary:
        # Aggregate RMSE across targets for each alpha/control cell.
        df = pd.DataFrame(regime_summary)
        if {"alpha_deg", "control_input_deg", "rmse"}.issubset(df.columns):
            pivot = df.pivot_table(index="control_input_deg", columns="alpha_deg", values="rmse", aggfunc="mean")
            if not pivot.empty:
                fig, ax = plt.subplots(figsize=(7.0, 5.0))
                im = ax.imshow(pivot.to_numpy(dtype=float), aspect="auto")
                ax.set_xticks(range(len(pivot.columns)))
                ax.set_xticklabels([str(v) for v in pivot.columns])
                ax.set_yticks(range(len(pivot.index)))
                ax.set_yticklabels([str(v) for v in pivot.index])
                ax.set_xlabel("alpha_deg")
                ax.set_ylabel("control_input_deg")
                ax.set_title("Mean residual RMSE by alpha/control")
                fig.colorbar(im, ax=ax, label="RMSE")
                fig.tight_layout()
                path = plots_dir / "regime_rmse_alpha_control.png"
                fig.savefig(path, dpi=160)
                plt.close(fig)
                artifacts.append({"kind": "regime_rmse_alpha_control", "path": str(path), "status": "written"})
    return artifacts


def _write_summary_markdown(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# AERIS Per-Regime Residual Summary")
    lines.append("")
    lines.append("## Dataset")
    lines.append(f"- dataset: `{report.get('config', {}).get('dataset_path')}`")
    lines.append(f"- model: `{report.get('config', {}).get('model_type')}`")
    lines.append(f"- targets: `{', '.join(report.get('config', {}).get('target_columns', []))}`")
    lines.append(f"- regime columns: `{', '.join(report.get('config', {}).get('regime_columns', []))}`")
    lines.append("")
    lines.append("## Target residuals")
    lines.append("| target | RMSE | MAE | bias | state |")
    lines.append("|---|---:|---:|---:|---|")
    for row in report.get("target_summary", []):
        lines.append(
            f"| {row.get('target')} | {row.get('rmse')} | {row.get('mae')} | {row.get('bias_mean')} | {row.get('residual_state')} |"
        )
    lines.append("")
    lines.append("## Worst regimes")
    for row in report.get("worst_regimes", [])[:10]:
        regime = ", ".join(
            f"{c}={row.get(c)}" for c in report.get("config", {}).get("regime_columns", []) if c in row
        )
        lines.append(f"- target `{row.get('target')}` | {regime} | RMSE `{row.get('rmse')}` | n `{row.get('n')}`")
    lines.append("")
    lines.append("## Operator recommendations")
    for rec in report.get("operator_recommendations", []):
        lines.append(f"- {rec}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_per_regime_residuals(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str = "extra_trees",
    seeds: Sequence[int] = (101, 202, 303, 404, 505),
    group_column: str = "geometry_id",
    regime_columns: Sequence[str] = ("alpha_deg", "control_input_deg"),
    min_regime_count: int = 3,
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
    """Train repeated grouped models and summarize residuals by target and regime."""
    dataset_path = Path(dataset_path).expanduser().resolve()
    seeds = parse_int_csv(list(seeds), option_name="seeds")
    min_regime_count = int(min_regime_count)
    if min_regime_count <= 0:
        raise ValueError("min_regime_count must be positive.")
    spec = get_model_spec(model_type)
    output_dir = _make_output_dir(dataset_path, output_dir)

    df, final_features, materialization = _materialize_dataset_for_learning_curves(
        dataset_path=dataset_path,
        feature_columns=feature_columns,
        target_columns=target_columns,
        allow_forced=allow_forced,
        feature_set_name=feature_set_name,
        group_column=group_column,
    )
    requested_regime_columns = parse_regime_columns(regime_columns)
    final_regime_columns, skipped_regime_columns = _existing_regime_columns(df, requested_regime_columns, group_column)
    if not final_regime_columns:
        raise ValueError("No requested regime columns exist in the materialized dataset.")

    residual_rows, split_metadata = _fit_predict_residual_rows(
        df=df,
        feature_columns=final_features,
        target_columns=target_columns,
        regime_columns=final_regime_columns,
        group_column=group_column,
        model_type=model_type,
        model_params=model_params,
        seeds=seeds,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
    )
    target_summary = _build_target_summary(residual_rows, target_columns)
    regime_summary = _build_regime_summary(residual_rows, final_regime_columns, min_regime_count)
    worst_regimes = regime_summary[:25]
    plot_artifacts = _plot_residuals(
        target_summary=target_summary,
        regime_summary=regime_summary,
        residual_rows=residual_rows,
        regime_columns=final_regime_columns,
        output_dir=output_dir,
    ) if write_plots else []

    residuals_csv = output_dir / "per_regime_residuals.csv"
    target_csv = output_dir / "per_target_residual_summary.csv"
    regime_csv = output_dir / "regime_residual_summary.csv"
    report_json = output_dir / "per_regime_residuals_report.json"
    summary_md = output_dir / "per_regime_residuals_summary.md"

    report: dict[str, Any] = {
        "schema_version": PER_REGIME_RESIDUALS_SCHEMA_VERSION,
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
            "regime_columns": list(final_regime_columns),
            "requested_regime_columns": list(requested_regime_columns),
            "skipped_regime_columns": list(skipped_regime_columns),
            "seeds": list(seeds),
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "min_regime_count": min_regime_count,
            "allow_forced": allow_forced,
        },
        "shape": {
            "n_rows": int(len(df)),
            "n_features": int(len(final_features)),
            "n_targets": int(len(target_columns)),
            "n_groups": int(df[group_column].nunique()) if group_column in df.columns else None,
            "n_residual_rows": int(len(residual_rows)),
            "n_regime_rows": int(len(regime_summary)),
        },
        "materialization": materialization,
        "split_metadata": split_metadata,
        "target_summary": target_summary,
        "regime_summary": regime_summary,
        "worst_regimes": worst_regimes,
        "operator_recommendations": _recommendations(target_summary, regime_summary, final_regime_columns),
        "plot_artifacts": plot_artifacts,
        "artifacts": {
            "output_dir": str(output_dir),
            "per_regime_residuals_csv": str(residuals_csv),
            "per_target_residual_summary_csv": str(target_csv),
            "regime_residual_summary_csv": str(regime_csv),
            "per_regime_residuals_report_json": str(report_json),
            "per_regime_residuals_summary_md": str(summary_md),
            "plots_dir": str(output_dir / "plots") if write_plots else None,
        },
    }
    _write_csv(residuals_csv, residual_rows)
    _write_csv(target_csv, target_summary)
    _write_csv(regime_csv, regime_summary)
    _write_summary_markdown(summary_md, report)
    _write_json(report_json, report)
    return report
