from __future__ import annotations
from collections.abc import Mapping

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.feature_set_inference import prepare_dataframe_for_feature_set_inference
from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.model_promotion import require_promoted_model

ENVELOPE_METRICS_SCHEMA_VERSION = "aeris.envelope_metrics_report.v1"


@dataclass(frozen=True)
class EnvelopeMetricsArtifacts:
    output_dir: Path
    report_path: Path
    predictions_csv_path: Path
    by_target_csv_path: Path
    by_feature_violation_csv_path: Path
    plots_dir: Path
    inside_vs_outside_rmse_png: Path
    inside_vs_outside_r2_png: Path
    outside_count_by_feature_png: Path


@dataclass(frozen=True)
class EnvelopeMetricsResult:
    output_df: pd.DataFrame
    report: dict[str, Any]
    artifacts: EnvelopeMetricsArtifacts


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _sanitize_json_for_strict_dump(value: Any) -> Any:
    # Recursively replace NaN/Inf values with None before strict JSON output.
    # sklearn metrics can legitimately produce NaN for tiny partitions.
    if isinstance(value, Mapping):
        return {str(k): _sanitize_json_for_strict_dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json_for_strict_dump(v) for v in value]
    if isinstance(value, np.ndarray):
        return _sanitize_json_for_strict_dump(value.tolist())
    if isinstance(value, pd.Series):
        return _sanitize_json_for_strict_dump(value.tolist())
    if isinstance(value, pd.DataFrame):
        return _sanitize_json_for_strict_dump(value.to_dict(orient="records"))
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return f if np.isfinite(f) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    return value

def _write_json(path: Path, data: dict[str, Any]) -> None:
    clean = _sanitize_json_for_strict_dump(data)
    path.write_text(json.dumps(clean, indent=2, default=_json_default, allow_nan=False), encoding="utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        return None if not np.isfinite(v) else v
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    return value


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if np.isfinite(out) else None


def _resolve_model_path(model_run_dir: Path) -> Path:
    candidates = [model_run_dir / "models" / "model.pkl", model_run_dir / "model.pkl"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find model.pkl under model run dir: {model_run_dir}")


def _load_model(model_path: Path) -> Any:
    with model_path.open("rb") as f:
        return pickle.load(f)


def _require_columns(df: pd.DataFrame, columns: list[str], *, label: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def _numeric_frame(df: pd.DataFrame, columns: list[str], *, label: str) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        numeric = pd.to_numeric(out[col], errors="coerce")
        arr = numeric.to_numpy(dtype=float, na_value=np.nan)
        bad = ~np.isfinite(arr)
        if bad.any():
            raise ValueError(f"{label} column '{col}' contains {int(bad.sum())} non-finite/non-numeric values")
        out[col] = numeric.astype(float)
    return out


def _predict(model: Any, X: np.ndarray, target_columns: list[str]) -> np.ndarray:
    pred = np.asarray(model.predict(X), dtype=float)
    if pred.ndim == 1:
        pred = pred.reshape(-1, 1)
    if pred.shape[1] != len(target_columns):
        raise ValueError(
            f"Model predicted {pred.shape[1]} target columns but train_config declares {len(target_columns)} targets."
        )
    return pred


def _feature_ranges_from_envelope(envelope: dict[str, Any], feature_columns: list[str]) -> tuple[dict[str, dict[str, float | None]], list[str]]:
    raw = envelope.get("feature_ranges", {}) or {}
    ranges: dict[str, dict[str, float | None]] = {}
    missing: list[str] = []
    for col in feature_columns:
        item = raw.get(col, {}) or {}
        lo = _safe_float(item.get("min"))
        hi = _safe_float(item.get("max"))
        if lo is None or hi is None:
            missing.append(col)
        ranges[col] = {"min": lo, "max": hi}
    return ranges, missing


def _range_arrays(feature_ranges: dict[str, dict[str, float | None]], feature_columns: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    lows: list[float] = []
    highs: list[float] = []
    widths: list[float] = []
    valid: list[bool] = []
    for col in feature_columns:
        item = feature_ranges.get(col, {}) or {}
        lo_raw = item.get("min")
        hi_raw = item.get("max")
        if lo_raw is None or hi_raw is None:
            lows.append(0.0)
            highs.append(0.0)
            widths.append(1.0)
            valid.append(False)
            continue
        lo = float(lo_raw)
        hi = float(hi_raw)
        width = abs(hi - lo)
        if not np.isfinite(width) or width <= 0.0:
            width = 1.0
        lows.append(lo)
        highs.append(hi)
        widths.append(width)
        valid.append(True)
    return (
        np.asarray(lows, dtype=float),
        np.asarray(highs, dtype=float),
        np.asarray(widths, dtype=float),
        np.asarray(valid, dtype=bool),
    )


def _envelope_row_diagnostics(
    values: np.ndarray,
    lows: np.ndarray,
    highs: np.ndarray,
    widths: np.ndarray,
    valid_mask: np.ndarray,
    feature_columns: list[str],
    *,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    lower_excess = np.maximum((lows.reshape(1, -1) - float(tolerance)) - values, 0.0)
    upper_excess = np.maximum(values - (highs.reshape(1, -1) + float(tolerance)), 0.0)
    excess_abs = lower_excess + upper_excess
    excess_abs[:, ~valid_mask] = 0.0
    excess_norm = excess_abs / widths.reshape(1, -1)
    violations = excess_abs > 0.0
    violation_count = np.sum(violations, axis=1).astype(int)
    excess_sum = np.sum(excess_norm, axis=1)
    excess_max = np.max(excess_norm, axis=1) if excess_norm.size else np.zeros(values.shape[0])
    violated_features: list[str] = []
    for row_idx in range(values.shape[0]):
        names = [feature_columns[j] for j in np.where(violations[row_idx])[0]]
        violated_features.append(";".join(names))
    return violation_count, excess_sum, excess_max, violated_features


def _target_scale_summary(y_true: np.ndarray, target_columns: list[str]) -> dict[str, dict[str, float | None]]:
    scales: dict[str, dict[str, float | None]] = {}
    for idx, target in enumerate(target_columns):
        vals = np.asarray(y_true[:, idx], dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            scales[target] = {"iqr": None, "std": None, "range": None, "scale": None, "scale_source": "missing"}
            continue
        q25, q75 = np.percentile(vals, [25, 75])
        iqr = float(q75 - q25)
        std = float(np.std(vals))
        rng = float(np.max(vals) - np.min(vals))
        if iqr > 0:
            scale, source = iqr, "iqr"
        elif std > 0:
            scale, source = std, "std"
        elif rng > 0:
            scale, source = rng, "range"
        else:
            scale, source = 1.0, "constant_fallback"
        scales[target] = {"iqr": iqr, "std": std, "range": rng, "scale": float(scale), "scale_source": source}
    return scales


def _metrics_or_none(y_true: np.ndarray, y_pred: np.ndarray, target_columns: list[str]) -> dict[str, Any]:
    if y_true.shape[0] == 0:
        return {
            "overall": {"n_rows": 0, "rmse_mean": None, "mae_mean": None, "r2_mean": None, "max_abs_error_mean": None},
            "per_target": {t: {"rmse": None, "mae": None, "r2": None, "bias_mean": None, "error_p95": None} for t in target_columns},
        }
    try:
        return evaluate_regression_metrics(y_true, y_pred, target_columns)
    except Exception:
        # Keep this report-producing tool robust for very small slices.
        return _manual_metrics(y_true, y_pred, target_columns)


def _manual_metrics(y_true: np.ndarray, y_pred: np.ndarray, target_columns: list[str]) -> dict[str, Any]:
    per: dict[str, Any] = {}
    rmse_values: list[float] = []
    mae_values: list[float] = []
    r2_values: list[float] = []
    max_abs_values: list[float] = []
    for idx, target in enumerate(target_columns):
        yt = np.asarray(y_true[:, idx], dtype=float)
        yp = np.asarray(y_pred[:, idx], dtype=float)
        err = yp - yt
        abs_err = np.abs(err)
        rmse = float(np.sqrt(np.mean(err ** 2))) if err.size else None
        mae = float(np.mean(abs_err)) if err.size else None
        denom = float(np.sum((yt - np.mean(yt)) ** 2)) if yt.size else 0.0
        r2 = None if yt.size < 2 or denom <= 0 else float(1.0 - np.sum(err ** 2) / denom)
        max_abs = float(np.max(abs_err)) if abs_err.size else None
        per[target] = {
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
            "max_abs_error": max_abs,
            "error_p50": float(np.percentile(abs_err, 50)) if abs_err.size else None,
            "error_p90": float(np.percentile(abs_err, 90)) if abs_err.size else None,
            "error_p95": float(np.percentile(abs_err, 95)) if abs_err.size else None,
            "error_p99": float(np.percentile(abs_err, 99)) if abs_err.size else None,
            "bias_mean": float(np.mean(err)) if err.size else None,
        }
        if rmse is not None:
            rmse_values.append(rmse)
        if mae is not None:
            mae_values.append(mae)
        if r2 is not None:
            r2_values.append(r2)
        if max_abs is not None:
            max_abs_values.append(max_abs)
    return {
        "per_target": per,
        "overall": {
            "rmse_mean": float(np.mean(rmse_values)) if rmse_values else None,
            "mae_mean": float(np.mean(mae_values)) if mae_values else None,
            "r2_mean": float(np.mean(r2_values)) if r2_values else None,
            "max_abs_error_mean": float(np.mean(max_abs_values)) if max_abs_values else None,
            "n_rows": int(y_true.shape[0]),
            "n_targets": int(y_true.shape[1]) if y_true.ndim == 2 else len(target_columns),
        },
    }


def _enrich_metrics(metrics: dict[str, Any], y_true: np.ndarray, y_pred: np.ndarray, target_columns: list[str], target_scales: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if y_true.shape[0] == 0:
        return metrics
    nrmse_values: list[float] = []
    bias_values: list[float] = []
    p95_values: list[float] = []
    for idx, target in enumerate(target_columns):
        yt = y_true[:, idx]
        yp = y_pred[:, idx]
        err = yp - yt
        abs_err = np.abs(err)
        scale = target_scales.get(target, {}).get("scale")
        rmse = _safe_float(metrics.get("per_target", {}).get(target, {}).get("rmse"))
        nrmse = (rmse / float(scale)) if rmse is not None and scale not in (None, 0) else None
        bias = float(np.mean(err)) if err.size else None
        p95 = float(np.percentile(abs_err, 95)) if abs_err.size else None
        metrics["per_target"].setdefault(target, {})["nrmse_scale"] = _safe_float(nrmse)
        metrics["per_target"][target]["bias_mean"] = _safe_float(bias)
        metrics["per_target"][target]["error_p95"] = _safe_float(p95)
        if nrmse is not None and np.isfinite(nrmse):
            nrmse_values.append(float(nrmse))
        if bias is not None and np.isfinite(bias):
            bias_values.append(float(abs(bias)))
        if p95 is not None and np.isfinite(p95):
            p95_values.append(float(p95))
    metrics.setdefault("derived", {})["nrmse_scale_mean"] = float(np.mean(nrmse_values)) if nrmse_values else None
    metrics["derived"]["abs_bias_mean"] = float(np.mean(bias_values)) if bias_values else None
    metrics["derived"]["error_p95_mean"] = float(np.mean(p95_values)) if p95_values else None
    return metrics


def _metrics_rows(partition_metrics: dict[str, dict[str, Any]], target_columns: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for partition, metrics in partition_metrics.items():
        for target in target_columns:
            item = metrics.get("per_target", {}).get(target, {}) or {}
            rows.append({
                "partition": partition,
                "target": target,
                "n_rows": metrics.get("overall", {}).get("n_rows"),
                "rmse": item.get("rmse"),
                "mae": item.get("mae"),
                "r2": item.get("r2"),
                "nrmse_scale": item.get("nrmse_scale"),
                "bias_mean": item.get("bias_mean"),
                "error_p95": item.get("error_p95"),
                "target_scale": item.get("target_scale"),
            })
    return rows


def _feature_violation_rows(output_df: pd.DataFrame, feature_columns: list[str], target_columns: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in feature_columns:
        mask = output_df["envelope_violated_features"].fillna("").astype(str).str.split(";").apply(lambda items: feature in items)
        count = int(mask.sum())
        if count == 0:
            continue
        row: dict[str, Any] = {"feature": feature, "outside_row_count": count}
        for target in target_columns:
            col = f"abs_error__{target}"
            if col in output_df.columns:
                vals = pd.to_numeric(output_df.loc[mask, col], errors="coerce")
                vals = vals[np.isfinite(vals.to_numpy(dtype=float, na_value=np.nan))]
                row[f"mean_abs_error__{target}"] = None if vals.empty else float(vals.mean())
                row[f"p95_abs_error__{target}"] = None if vals.empty else float(np.percentile(vals, 95))
        rows.append(row)
    return sorted(rows, key=lambda r: int(r.get("outside_row_count", 0)), reverse=True)


def _plot_bar(df: pd.DataFrame, *, x: str, y: str, title: str, ylabel: str, path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return
    if df.empty or x not in df.columns or y not in df.columns:
        return
    work = df[[x, y]].dropna()
    if work.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(work[x].astype(str), pd.to_numeric(work[y], errors="coerce"))
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _write_plots(by_target_df: pd.DataFrame, by_feature_df: pd.DataFrame, artifacts: EnvelopeMetricsArtifacts) -> None:
    if not by_target_df.empty:
        summary = by_target_df.groupby("partition", as_index=False).agg(rmse=("rmse", "mean"), r2=("r2", "mean"))
        _plot_bar(summary, x="partition", y="rmse", title="AERIS inside/outside RMSE mean", ylabel="RMSE mean [target units]", path=artifacts.inside_vs_outside_rmse_png)
        _plot_bar(summary, x="partition", y="r2", title="AERIS inside/outside R² mean", ylabel="R² [-]", path=artifacts.inside_vs_outside_r2_png)
    if not by_feature_df.empty:
        top = by_feature_df.head(20)
        _plot_bar(top, x="feature", y="outside_row_count", title="Outside-envelope row count by feature", ylabel="outside row count", path=artifacts.outside_count_by_feature_png)


def compute_envelope_metrics(
    *,
    model_run_dir: str | Path,
    input_csv: str | Path | None = None,
    output_dir: str | Path | None = None,
    require_promoted_model_gate: bool = True,
    include_truth_if_available: bool = True,
    tolerance: float = 0.0,
    feature_set_name: str | None = None,
    allow_feature_set_mismatch: bool = False,
) -> EnvelopeMetricsResult:
    """Evaluate model metrics separately inside and outside the training envelope."""
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    if input_csv is None:
        input_csv = model_run_dir / "test_rows.csv"
    input_csv = Path(input_csv).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    if not input_csv.exists() or not input_csv.is_file():
        raise FileNotFoundError(f"Input CSV does not exist: {input_csv}")

    promotion_manifest: dict[str, Any] | None = None
    if require_promoted_model_gate:
        promotion_manifest = require_promoted_model(model_run_dir)

    train_config = _load_json(model_run_dir / "train_config.json")
    envelope = _load_json(model_run_dir / "training_envelope.json")
    feature_columns = list(train_config.get("feature_columns", []))
    target_columns = list(train_config.get("target_columns", []))
    if not feature_columns:
        raise ValueError("train_config.json does not define feature_columns")
    if not target_columns:
        raise ValueError("train_config.json does not define target_columns")

    raw_df = pd.read_csv(input_csv)
    if raw_df.empty:
        raise ValueError(f"Input CSV is empty: {input_csv}")
    prepared = prepare_dataframe_for_feature_set_inference(
        raw_df,
        train_config=train_config,
        feature_set_name=feature_set_name,
        allow_feature_set_mismatch=allow_feature_set_mismatch,
    )
    df = prepared.dataframe
    _require_columns(df, feature_columns, label="Input CSV")
    numeric_df = _numeric_frame(df, feature_columns, label="Input CSV")
    X = numeric_df[feature_columns].to_numpy(dtype=float)

    model_path = _resolve_model_path(model_run_dir)
    model = _load_model(model_path)
    pred = _predict(model, X, target_columns)

    feature_ranges, missing_range_features = _feature_ranges_from_envelope(envelope, feature_columns)
    lows, highs, widths, valid_mask = _range_arrays(feature_ranges, feature_columns)
    violation_count, excess_sum, excess_max, violated_features = _envelope_row_diagnostics(
        X, lows, highs, widths, valid_mask, feature_columns, tolerance=float(tolerance)
    )

    output_df = raw_df.copy()
    for idx, target in enumerate(target_columns):
        output_df[f"pred__{target}"] = pred[:, idx]
    output_df["envelope_violation_count"] = violation_count
    output_df["envelope_excess_sum"] = excess_sum
    output_df["envelope_excess_max"] = excess_max
    output_df["envelope_status"] = np.where(violation_count > 0, "outside", "inside")
    output_df["envelope_violated_features"] = violated_features

    truth_available = include_truth_if_available and all(col in raw_df.columns for col in target_columns)
    partition_metrics: dict[str, dict[str, Any]] = {}
    target_scales: dict[str, dict[str, Any]] = {}
    if truth_available:
        truth_df = _numeric_frame(raw_df, target_columns, label="Input CSV truth")
        y_true = truth_df[target_columns].to_numpy(dtype=float)
        target_scales = _target_scale_summary(y_true, target_columns)
        for idx, target in enumerate(target_columns):
            err = pred[:, idx] - y_true[:, idx]
            output_df[f"error__{target}"] = err
            output_df[f"abs_error__{target}"] = np.abs(err)
        masks = {
            "all": np.ones(len(output_df), dtype=bool),
            "inside": violation_count == 0,
            "outside": violation_count > 0,
        }
        for partition, mask in masks.items():
            metrics = _metrics_or_none(y_true[mask], pred[mask], target_columns)
            metrics = _enrich_metrics(metrics, y_true[mask], pred[mask], target_columns, target_scales)
            for target, scale in target_scales.items():
                metrics.get("per_target", {}).setdefault(target, {})["target_scale"] = scale.get("scale")
            partition_metrics[partition] = metrics

    if output_dir is None:
        output_dir_resolved = model_run_dir / "quality" / f"envelope_metrics__{input_csv.stem}"
    else:
        output_dir_resolved = Path(output_dir).expanduser().resolve()
    output_dir_resolved = _ensure_dir(output_dir_resolved)
    plots_dir = _ensure_dir(output_dir_resolved / "plots")
    artifacts = EnvelopeMetricsArtifacts(
        output_dir=output_dir_resolved,
        report_path=output_dir_resolved / "envelope_metrics_report.json",
        predictions_csv_path=output_dir_resolved / "envelope_metrics_predictions.csv",
        by_target_csv_path=output_dir_resolved / "envelope_metrics_by_target.csv",
        by_feature_violation_csv_path=output_dir_resolved / "envelope_metrics_by_feature_violation.csv",
        plots_dir=plots_dir,
        inside_vs_outside_rmse_png=plots_dir / "inside_vs_outside_rmse.png",
        inside_vs_outside_r2_png=plots_dir / "inside_vs_outside_r2.png",
        outside_count_by_feature_png=plots_dir / "outside_count_by_feature.png",
    )

    output_df.to_csv(artifacts.predictions_csv_path, index=False)
    by_target_df = pd.DataFrame(_metrics_rows(partition_metrics, target_columns))
    if by_target_df.empty:
        by_target_df = pd.DataFrame(columns=["partition", "target", "n_rows", "rmse", "mae", "r2", "nrmse_scale", "bias_mean", "error_p95", "target_scale"])
    by_target_df.to_csv(artifacts.by_target_csv_path, index=False)
    by_feature_df = pd.DataFrame(_feature_violation_rows(output_df, feature_columns, target_columns))
    if by_feature_df.empty:
        by_feature_df = pd.DataFrame(columns=["feature", "outside_row_count"])
    by_feature_df.to_csv(artifacts.by_feature_violation_csv_path, index=False)
    _write_plots(by_target_df, by_feature_df, artifacts)

    inside_rows = int((output_df["envelope_status"] == "inside").sum())
    outside_rows = int((output_df["envelope_status"] == "outside").sum())
    report: dict[str, Any] = {
        "schema_version": ENVELOPE_METRICS_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "status": "success",
        "purpose": "split prediction quality by training-envelope status; no retraining or solver execution performed",
        "model_run_dir": str(model_run_dir),
        "model_path": str(model_path),
        "input_csv": str(input_csv),
        "output_dir": str(output_dir_resolved),
        "require_promoted_model_gate": bool(require_promoted_model_gate),
        "promotion_manifest_status": None if promotion_manifest is None else promotion_manifest.get("status"),
        "include_truth_if_available": bool(include_truth_if_available),
        "truth_available": bool(truth_available),
        "tolerance": float(tolerance),
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "feature_set": prepared.to_summary(),
        "missing_envelope_features": missing_range_features,
        "row_counts": {
            "total": int(len(output_df)),
            "inside": inside_rows,
            "outside": outside_rows,
            "inside_fraction": float(inside_rows / len(output_df)) if len(output_df) else None,
            "outside_fraction": float(outside_rows / len(output_df)) if len(output_df) else None,
        },
        "partition_metrics": partition_metrics,
        "feature_violation_summary": by_feature_df.to_dict(orient="records"),
        "interpretation": {
            "outside_envelope_warning": outside_rows > 0,
            "message": (
                "Compare inside vs outside metrics before trusting extrapolated predictions. "
                "Outside-envelope failures usually mean the model is extrapolating or the train split coverage is weak."
            ),
        },
        "artifacts": {
            "report_json": str(artifacts.report_path),
            "predictions_csv": str(artifacts.predictions_csv_path),
            "by_target_csv": str(artifacts.by_target_csv_path),
            "by_feature_violation_csv": str(artifacts.by_feature_violation_csv_path),
            "plots_dir": str(artifacts.plots_dir),
            "inside_vs_outside_rmse_png": str(artifacts.inside_vs_outside_rmse_png),
            "inside_vs_outside_r2_png": str(artifacts.inside_vs_outside_r2_png),
            "outside_count_by_feature_png": str(artifacts.outside_count_by_feature_png),
            "input_csv_sha256": file_sha256(input_csv),
            "model_sha256": file_sha256(model_path),
        },
    }
    _write_json(artifacts.report_path, report)
    return EnvelopeMetricsResult(output_df=output_df, report=report, artifacts=artifacts)
