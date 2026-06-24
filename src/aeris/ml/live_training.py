from __future__ import annotations

import json
import math
import pickle
import time
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from aeris.dataset.splitting import DatasetSplit, split_dataset
from aeris.dataset.training_data import TrainingData, load_training_data
from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import FeatureSet, get_feature_set, validate_feature_set_dataframe
from aeris.ml.experiment_tracking import build_experiment_tracker

LIVE_TRAINING_SCHEMA_VERSION = "aeris.live_training_monitor.v2.1"
EpochCallback = Callable[[dict[str, Any]], None]
_EPS = 1.0e-12


@dataclass(frozen=True)
class LiveTrainingArtifacts:
    output_dir: Path
    models_dir: Path
    model_path: Path
    monitor_dir: Path
    report_json: Path
    history_csv: Path
    history_long_csv: Path
    plots_dir: Path
    loss_curve_png: Path
    rmse_mean_curve_png: Path
    r2_mean_curve_png: Path
    per_target_rmse_curve_png: Path
    per_target_r2_curve_png: Path
    normalized_error_curve_png: Path
    generalization_gap_curve_png: Path
    metrics_json: Path
    train_rows_csv: Path | None = None
    val_rows_csv: Path | None = None
    test_rows_csv: Path | None = None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return str(value)


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _safe_name(name: str) -> str:
    out = "".join(ch if ch.isalnum() else "_" for ch in str(name)).strip("_")
    return out or "target"


def _parse_hidden_layer_sizes(value: Any) -> tuple[int, ...]:
    if value is None:
        return (64, 64)
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("hidden_layer_sizes must contain positive integers")
        return (int(value),)
    if isinstance(value, (list, tuple)):
        out = tuple(int(v) for v in value)
    else:
        text = str(value).strip()
        if not text:
            return (64, 64)
        text = text.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
        out = tuple(int(part.strip()) for part in text.split(",") if part.strip())
    if not out or any(v <= 0 for v in out):
        raise ValueError("hidden_layer_sizes must contain positive integers")
    return out


def _make_live_mlp(*, random_seed: int, model_params: dict[str, Any] | None) -> Pipeline:
    params = dict(model_params or {})
    hidden_layer_sizes = _parse_hidden_layer_sizes(params.pop("hidden_layer_sizes", (64, 64)))
    params.pop("max_iter", None)
    params.pop("warm_start", None)
    params.pop("early_stopping", None)

    mlp_params: dict[str, Any] = {
        "hidden_layer_sizes": hidden_layer_sizes,
        "activation": params.pop("activation", "relu"),
        "solver": params.pop("solver", "adam"),
        "alpha": float(params.pop("alpha", 1.0e-4)),
        "batch_size": params.pop("batch_size", "auto"),
        "learning_rate": params.pop("learning_rate", "adaptive"),
        "learning_rate_init": float(params.pop("learning_rate_init", 1.0e-3)),
        "max_iter": 1,
        "warm_start": True,
        "early_stopping": False,
        "shuffle": bool(params.pop("shuffle", True)),
        "tol": 0.0,
        "random_state": int(params.pop("random_state", random_seed)),
    }
    for key in ("beta_1", "beta_2", "epsilon", "nesterovs_momentum", "momentum", "power_t"):
        if key in params:
            mlp_params[key] = params.pop(key)
    if params:
        unknown = ", ".join(sorted(params))
        raise ValueError(f"Unsupported live neural_mlp parameter(s): {unknown}")

    return Pipeline([("scaler", StandardScaler()), ("model", MLPRegressor(**mlp_params))])


def _predict_2d(model: Any, X: np.ndarray) -> np.ndarray:
    pred = np.asarray(model.predict(X), dtype=float)
    if pred.ndim == 1:
        pred = pred.reshape(-1, 1)
    return pred


def _target_scale_summary(y_train: np.ndarray, target_columns: list[str]) -> dict[str, dict[str, float | str]]:
    scales: dict[str, dict[str, float | str]] = {}
    for idx, target in enumerate(target_columns):
        values = np.asarray(y_train[:, idx], dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            scales[target] = {
                "iqr": 0.0,
                "std": 0.0,
                "range": 0.0,
                "scale": 1.0,
                "scale_source": "fallback_1",
            }
            continue
        q25, q75 = np.percentile(finite, [25, 75])
        iqr = float(q75 - q25)
        std = float(np.std(finite))
        data_range = float(np.max(finite) - np.min(finite))
        if iqr > _EPS:
            scale = iqr
            source = "iqr"
        elif std > _EPS:
            scale = std
            source = "std"
        elif data_range > _EPS:
            scale = data_range
            source = "range"
        else:
            scale = 1.0
            source = "fallback_1"
        scales[target] = {
            "iqr": iqr,
            "std": std,
            "range": data_range,
            "scale": float(scale),
            "scale_source": source,
        }
    return scales


def _partition_metrics(
    *,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_columns: list[str],
    target_scales: dict[str, dict[str, float | str]],
) -> tuple[dict[str, float | None], dict[str, dict[str, float | None]]]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.ndim == 1:
        y_true = y_true.reshape(-1, 1)
    if y_pred.ndim == 1:
        y_pred = y_pred.reshape(-1, 1)

    per_target: dict[str, dict[str, float | None]] = {}
    if y_true.shape[0] == 0 or y_pred.shape[0] == 0:
        empty_summary = {
            "rmse_mean": None,
            "mae_mean": None,
            "r2_mean": None,
            "loss_mse_mean": None,
            "nrmse_scale_mean": None,
            "nmae_scale_mean": None,
            "bias_mean": None,
            "error_p95_mean": None,
        }
        return empty_summary, per_target

    for idx, target in enumerate(target_columns):
        err = y_pred[:, idx] - y_true[:, idx]
        mask = np.isfinite(err) & np.isfinite(y_true[:, idx]) & np.isfinite(y_pred[:, idx])
        if not np.any(mask):
            per_target[target] = {
                "rmse": None,
                "mae": None,
                "r2": None,
                "loss_mse": None,
                "nrmse_scale": None,
                "nmae_scale": None,
                "bias": None,
                "error_p95": None,
            }
            continue
        e = err[mask]
        yt = y_true[:, idx][mask]
        mse = float(np.mean(e**2))
        rmse = float(np.sqrt(mse))
        mae = float(np.mean(np.abs(e)))
        bias = float(np.mean(e))
        p95 = float(np.percentile(np.abs(e), 95))
        denom = float(np.sum((yt - np.mean(yt)) ** 2))
        r2 = float(1.0 - float(np.sum(e**2)) / denom) if denom > _EPS else None
        scale = float(target_scales[target].get("scale", 1.0) or 1.0)
        per_target[target] = {
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
            "loss_mse": mse,
            "nrmse_scale": rmse / scale if scale > _EPS else None,
            "nmae_scale": mae / scale if scale > _EPS else None,
            "bias": bias,
            "error_p95": p95,
        }

    def _mean(metric: str) -> float | None:
        vals = [v.get(metric) for v in per_target.values()]
        finite = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
        return float(np.mean(finite)) if finite else None

    summary = {
        "rmse_mean": _mean("rmse"),
        "mae_mean": _mean("mae"),
        "r2_mean": _mean("r2"),
        "loss_mse_mean": _mean("loss_mse"),
        "nrmse_scale_mean": _mean("nrmse_scale"),
        "nmae_scale_mean": _mean("nmae_scale"),
        "bias_mean": _mean("bias"),
        "error_p95_mean": _mean("error_p95"),
    }
    return summary, per_target


def _flatten_partition_metrics(prefix: str, summary: dict[str, Any], per_target: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {f"{prefix}_{key}": value for key, value in summary.items()}
    for target, metrics in per_target.items():
        safe = _safe_name(target)
        for metric, value in metrics.items():
            row[f"{prefix}_{metric}__{safe}"] = value
    return row


def _history_long_rows(epoch: int, partition: str, per_target: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target, metrics in per_target.items():
        row = {"epoch": int(epoch), "partition": partition, "target": target}
        row.update(metrics)
        rows.append(row)
    return rows


def _get_learning_rate(inner: Any) -> float | None:
    optimizer = getattr(inner, "_optimizer", None)
    for obj in (optimizer, inner):
        value = getattr(obj, "learning_rate", None)
        if value is not None:
            return _safe_float(value)
    return None


def _finite_series(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _diagnose_history(history_df: pd.DataFrame, *, patience: int = 8, min_delta_rel: float = 0.01) -> dict[str, Any]:
    warnings_out: list[str] = []
    status: dict[str, Any] = {
        "best_val_rmse_epoch": None,
        "best_val_rmse_mean": None,
        "epochs_since_best_val_rmse": None,
        "overfit_warning": False,
        "plateau_warning": False,
        "validation_metrics_available": False,
        "warnings": warnings_out,
    }
    if history_df.empty or "val_rmse_mean" not in history_df.columns:
        warnings_out.append("validation_metrics_missing")
        return status
    val = _finite_series(history_df["val_rmse_mean"])
    if val.empty:
        warnings_out.append("validation_metrics_nan")
        return status
    status["validation_metrics_available"] = True
    best_idx = int(val.idxmin())
    best_epoch = int(history_df.loc[best_idx, "epoch"])
    best_val = float(val.loc[best_idx])
    last_epoch = int(history_df["epoch"].iloc[-1])
    epochs_since_best = max(0, last_epoch - best_epoch)
    status["best_val_rmse_epoch"] = best_epoch
    status["best_val_rmse_mean"] = best_val
    status["epochs_since_best_val_rmse"] = epochs_since_best
    if "train_rmse_mean" in history_df.columns:
        train_last = _safe_float(history_df["train_rmse_mean"].iloc[-1])
        val_last = _safe_float(history_df["val_rmse_mean"].iloc[-1])
        if train_last is not None and val_last is not None and train_last > _EPS:
            gap_rel = (val_last - train_last) / train_last
            status["final_generalization_gap_rel"] = gap_rel
            if gap_rel > 0.35:
                status["overfit_warning"] = True
                warnings_out.append("possible_overfit_large_val_train_rmse_gap")
    if len(val) >= patience + 1:
        recent = val.tail(patience)
        recent_best = float(recent.min())
        previous_best = float(val.iloc[: -patience].min()) if len(val) > patience else float(val.min())
        required_improvement = abs(previous_best) * float(min_delta_rel)
        if previous_best - recent_best < required_improvement:
            status["plateau_warning"] = True
            warnings_out.append("possible_plateau_no_recent_val_rmse_improvement")
    return status


def _write_history(history_rows: list[dict[str, Any]], history_csv: Path) -> pd.DataFrame:
    history_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(history_rows)
    df.to_csv(history_csv, index=False)
    return df


def _write_long_history(long_rows: list[dict[str, Any]], history_long_csv: Path) -> pd.DataFrame:
    history_long_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(long_rows)
    df.to_csv(history_long_csv, index=False)
    return df


def _write_report(report: dict[str, Any], report_json: Path) -> None:
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, default=_json_default, allow_nan=False), encoding="utf-8")


def _plot_columns(history_df: pd.DataFrame, columns: list[str], out_path: Path, *, title: str, ylabel: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return
    cols = [c for c in columns if c in history_df.columns and not _finite_series(history_df[c]).empty]
    if not cols:
        return
    fig = plt.figure(figsize=(9, 5))
    ax = fig.add_subplot(111)
    for col in cols:
        ax.plot(history_df["epoch"], pd.to_numeric(history_df[col], errors="coerce"), label=col)
    ax.set_xlabel("epoch")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize="small")
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _write_all_plots(history_df: pd.DataFrame, artifacts: LiveTrainingArtifacts) -> None:
    _plot_columns(
        history_df,
        ["train_loss", "train_loss_mse_mean", "val_loss_mse_mean", "test_loss_mse_mean"],
        artifacts.loss_curve_png,
        title="AERIS live training loss curves",
        ylabel="loss / MSE",
    )
    _plot_columns(
        history_df,
        ["train_rmse_mean", "val_rmse_mean", "test_rmse_mean"],
        artifacts.rmse_mean_curve_png,
        title="AERIS live RMSE mean curves",
        ylabel="RMSE mean",
    )
    _plot_columns(
        history_df,
        ["train_r2_mean", "val_r2_mean", "test_r2_mean"],
        artifacts.r2_mean_curve_png,
        title="AERIS live R² mean curves",
        ylabel="R² mean",
    )
    _plot_columns(
        history_df,
        ["train_nrmse_scale_mean", "val_nrmse_scale_mean", "test_nrmse_scale_mean"],
        artifacts.normalized_error_curve_png,
        title="AERIS live normalized RMSE curves",
        ylabel="NRMSE / train target scale",
    )
    rmse_target_cols = [c for c in history_df.columns if c.startswith("val_rmse__")]
    _plot_columns(
        history_df,
        rmse_target_cols,
        artifacts.per_target_rmse_curve_png,
        title="AERIS live per-target validation RMSE",
        ylabel="validation RMSE",
    )
    r2_target_cols = [c for c in history_df.columns if c.startswith("val_r2__")]
    _plot_columns(
        history_df,
        r2_target_cols,
        artifacts.per_target_r2_curve_png,
        title="AERIS live per-target validation R²",
        ylabel="validation R²",
    )
    gap_cols = ["val_minus_train_rmse_mean", "val_minus_train_loss_mse_mean", "test_minus_train_rmse_mean"]
    _plot_columns(
        history_df,
        gap_cols,
        artifacts.generalization_gap_curve_png,
        title="AERIS live generalization gaps",
        ylabel="validation/test minus train",
    )


def _make_artifacts(output_dir: Path) -> LiveTrainingArtifacts:
    monitor_dir = output_dir / "training_monitor"
    plots_dir = monitor_dir / "plots"
    return LiveTrainingArtifacts(
        output_dir=output_dir,
        models_dir=output_dir / "models",
        model_path=output_dir / "models" / "model.pkl",
        monitor_dir=monitor_dir,
        report_json=monitor_dir / "training_monitor_report.json",
        history_csv=monitor_dir / "training_history.csv",
        history_long_csv=monitor_dir / "training_history_long.csv",
        plots_dir=plots_dir,
        loss_curve_png=plots_dir / "loss_curves.png",
        rmse_mean_curve_png=plots_dir / "rmse_mean_curves.png",
        r2_mean_curve_png=plots_dir / "r2_mean_curves.png",
        per_target_rmse_curve_png=plots_dir / "per_target_rmse_curves.png",
        per_target_r2_curve_png=plots_dir / "per_target_r2_curves.png",
        normalized_error_curve_png=plots_dir / "normalized_error_curves.png",
        generalization_gap_curve_png=plots_dir / "generalization_gap_curves.png",
        metrics_json=output_dir / "metrics.json",
    )




# ---------------------------------------------------------------------------
# AERIS_LIVE_TRAINING_V2_2_TARGET_SCALING
# ---------------------------------------------------------------------------
def _target_scale_vectors(y_train: np.ndarray, target_columns: list[str], target_scales: dict[str, dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Return target centering/scaling vectors for neural training.

    The model is trained on scaled targets, but all reported metrics remain in
    physical units after inverse transformation. This prevents degree-valued
    targets from dominating MSE while preserving engineering interpretability.
    """
    y_train = np.asarray(y_train, dtype=float)
    offsets = np.nanmean(y_train, axis=0)
    scales: list[float] = []
    for i, target in enumerate(target_columns):
        info = dict(target_scales.get(target, {}))
        scale = info.get("scale")
        try:
            scale_f = float(scale)
        except Exception:
            scale_f = float("nan")
        if not np.isfinite(scale_f) or scale_f <= 0.0:
            std = float(np.nanstd(y_train[:, i])) if y_train.size else float("nan")
            scale_f = std if np.isfinite(std) and std > 0.0 else 1.0
        scales.append(scale_f)
    scale_arr = np.asarray(scales, dtype=float).reshape(1, -1)
    offset_arr = np.asarray(offsets, dtype=float).reshape(1, -1)
    manifest = {
        "enabled": True,
        "method": "center_by_train_mean_scale_by_target_iqr_or_std",
        "offsets": {target: float(offset_arr[0, i]) for i, target in enumerate(target_columns)},
        "scales": {target: float(scale_arr[0, i]) for i, target in enumerate(target_columns)},
        "training_loss_units": "scaled_target_mse",
        "reported_metric_units": "physical_units_after_inverse_transform",
    }
    return offset_arr, scale_arr, manifest


def _scale_targets(y: np.ndarray, offsets: np.ndarray, scales: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    return (y - offsets) / scales


def _inverse_scale_targets(y_scaled: np.ndarray, offsets: np.ndarray, scales: np.ndarray) -> np.ndarray:
    y_scaled = np.asarray(y_scaled, dtype=float)
    if y_scaled.ndim == 1:
        y_scaled = y_scaled.reshape(-1, 1)
    return y_scaled * scales + offsets


def _write_residual_artifacts(
    *,
    artifacts: Any,
    target_columns: list[str],
    partitions: dict[str, tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    """Write final residual table and histogram artifacts."""
    residual_csv = Path(artifacts.monitor_dir) / "residuals_long.csv"
    residual_hist_png = Path(artifacts.plots_dir) / "residual_distribution_histogram.png"
    rows: list[dict[str, Any]] = []
    for partition, (y_true, y_pred) in partitions.items():
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)
        for target_idx, target in enumerate(target_columns):
            truth = y_true[:, target_idx]
            pred = y_pred[:, target_idx]
            residual = pred - truth
            for row_idx, (t, p, r) in enumerate(zip(truth, pred, residual)):
                rows.append({
                    "partition": partition,
                    "row_index": int(row_idx),
                    "target": target,
                    "truth": _safe_float(t),
                    "prediction": _safe_float(p),
                    "residual": _safe_float(r),
                    "abs_error": _safe_float(abs(r)),
                })
    df = pd.DataFrame(rows)
    residual_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(residual_csv, index=False)
    try:
        import matplotlib.pyplot as plt
        residual_hist_png.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(9, 5))
        for target in target_columns:
            s = pd.to_numeric(df.loc[df["target"] == target, "residual"], errors="coerce").dropna()
            if not s.empty:
                ax.hist(s, bins=30, alpha=0.45, label=target)
        ax.axvline(0.0, linestyle="--", linewidth=1.0)
        ax.set_title("AERIS live neural MLP residual distribution")
        ax.set_xlabel("Residual = prediction - truth [target units]")
        ax.set_ylabel("Count")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(residual_hist_png, dpi=160)
        plt.close(fig)
    except Exception:
        # The CSV is the required artifact; PNG is best-effort in headless/minimal environments.
        pass
    return {
        "residuals_long_csv": str(residual_csv),
        "residual_distribution_histogram_png": str(residual_hist_png),
    }


def _live_training_quality_warnings(final_row: dict[str, Any] | None) -> list[str]:
    """Return operator-facing warnings for non-promotable neural smoke runs."""
    if not isinstance(final_row, dict):
        return ["No final epoch metrics available; do not promote this model."]
    warnings_out: list[str] = []
    val_r2 = final_row.get("val_r2_mean")
    test_r2 = final_row.get("test_r2_mean")
    val_nrmse = final_row.get("val_nrmse_scale_mean")
    try:
        if val_r2 is not None and float(val_r2) < 0.50:
            warnings_out.append(f"Validation R² is poor ({float(val_r2):.3f}); do not promote this MLP.")
    except Exception:
        warnings_out.append("Validation R² is unavailable; do not promote this MLP.")
    try:
        if test_r2 is not None and float(test_r2) < 0.50:
            warnings_out.append(f"Test R² is poor ({float(test_r2):.3f}); do not promote this MLP.")
    except Exception:
        warnings_out.append("Test R² is unavailable; do not promote this MLP.")
    try:
        if val_nrmse is not None and float(val_nrmse) > 0.30:
            warnings_out.append(f"Validation normalized RMSE is high ({float(val_nrmse):.3f}); model is not engineering-ready.")
    except Exception:
        pass
    return warnings_out

def run_live_mlp_arrays(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    target_columns: list[str],
    output_dir: Path,
    max_epochs: int = 50,
    random_seed: int = 123,
    model_params: dict[str, Any] | None = None,
    epoch_callback: EpochCallback | None = None,
    X_test: np.ndarray | None = None,
    y_test: np.ndarray | None = None,
    tracking_backends: list[str] | None = None,
    tracking_experiment_name: str = "aeris",
    tracking_run_name: str | None = None,
    wandb_mode: str = "offline",
) -> dict[str, Any]:
    """Train an sklearn MLP one epoch at a time and emit full live metric events.

    V2.1 intentionally logs both raw physical-unit metrics and normalized target-scale
    metrics. This matters in AERIS because targets can have different units/scales
    (e.g. trim deflection in degrees and Cm_delta_e per radian).
    """
    output_dir = Path(output_dir).expanduser()
    artifacts = _make_artifacts(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts.monitor_dir.mkdir(parents=True, exist_ok=True)
    artifacts.models_dir.mkdir(parents=True, exist_ok=True)
    artifacts.plots_dir.mkdir(parents=True, exist_ok=True)

    X_train = np.asarray(X_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    X_val = np.asarray(X_val, dtype=float)
    y_val = np.asarray(y_val, dtype=float)
    if y_train.ndim == 1:
        y_train = y_train.reshape(-1, 1)
    if y_val.ndim == 1:
        y_val = y_val.reshape(-1, 1)
    if X_test is not None:
        X_test = np.asarray(X_test, dtype=float)
    if y_test is not None:
        y_test = np.asarray(y_test, dtype=float)
        if y_test.ndim == 1:
            y_test = y_test.reshape(-1, 1)

    if int(max_epochs) <= 0:
        raise ValueError("max_epochs must be positive")
    if y_train.shape[1] != len(target_columns):
        raise ValueError("target_columns length does not match y_train target dimension")

    target_scales = _target_scale_summary(y_train, target_columns)
    target_offsets, target_scale_values, target_scaling_manifest = _target_scale_vectors(y_train, target_columns, target_scales)
    y_train_fit = _scale_targets(y_train, target_offsets, target_scale_values)
    model = _make_live_mlp(random_seed=random_seed, model_params=model_params)
    history_rows: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []
    tracker = build_experiment_tracker(
        output_dir=output_dir,
        backends=tracking_backends,
        experiment_name=tracking_experiment_name,
        run_name=tracking_run_name or output_dir.name,
        wandb_mode=wandb_mode,
        params={
            "model_type": "neural_mlp_live",
            "max_epochs": int(max_epochs),
            "random_seed": int(random_seed),
            "target_columns": list(target_columns),
            "model_params": dict(model_params or {}),
            "target_scaling_enabled": True,
            "target_scaling_method": "center_by_train_mean_scale_by_target_iqr_or_std",
        },
        tags={"aeris.live_training": True, "aeris.schema_version": LIVE_TRAINING_SCHEMA_VERSION},
    )

    for epoch in range(1, int(max_epochs) + 1):
        tic = time.perf_counter()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=ConvergenceWarning)
            model.fit(X_train, y_train_fit)
        epoch_time_sec = float(time.perf_counter() - tic)

        inner = model.named_steps.get("model", model)
        train_pred = _inverse_scale_targets(_predict_2d(model, X_train), target_offsets, target_scale_values)
        val_pred = _inverse_scale_targets(_predict_2d(model, X_val), target_offsets, target_scale_values)
        train_summary, train_pt = _partition_metrics(
            y_true=y_train, y_pred=train_pred, target_columns=target_columns, target_scales=target_scales
        )
        val_summary, val_pt = _partition_metrics(
            y_true=y_val, y_pred=val_pred, target_columns=target_columns, target_scales=target_scales
        )

        row: dict[str, Any] = {
            "epoch": int(epoch),
            "train_loss": _safe_float(getattr(inner, "loss_", np.nan)),
            "learning_rate": _get_learning_rate(inner),
            "epoch_time_sec": epoch_time_sec,
        }
        row.update(_flatten_partition_metrics("train", train_summary, train_pt))
        row.update(_flatten_partition_metrics("val", val_summary, val_pt))

        if X_test is not None and y_test is not None:
            test_pred = _inverse_scale_targets(_predict_2d(model, X_test), target_offsets, target_scale_values)
            test_summary, test_pt = _partition_metrics(
                y_true=y_test, y_pred=test_pred, target_columns=target_columns, target_scales=target_scales
            )
            row.update(_flatten_partition_metrics("test", test_summary, test_pt))
            long_rows.extend(_history_long_rows(epoch, "test", test_pt))

        row["val_minus_train_rmse_mean"] = (
            row["val_rmse_mean"] - row["train_rmse_mean"]
            if row.get("val_rmse_mean") is not None and row.get("train_rmse_mean") is not None
            else None
        )
        row["val_minus_train_loss_mse_mean"] = (
            row["val_loss_mse_mean"] - row["train_loss_mse_mean"]
            if row.get("val_loss_mse_mean") is not None and row.get("train_loss_mse_mean") is not None
            else None
        )
        row["test_minus_train_rmse_mean"] = (
            row["test_rmse_mean"] - row["train_rmse_mean"]
            if row.get("test_rmse_mean") is not None and row.get("train_rmse_mean") is not None
            else None
        )

        history_rows.append(row)
        long_rows.extend(_history_long_rows(epoch, "train", train_pt))
        long_rows.extend(_history_long_rows(epoch, "val", val_pt))
        history_df = _write_history(history_rows, artifacts.history_csv)
        _write_long_history(long_rows, artifacts.history_long_csv)
        diagnostics = _diagnose_history(history_df)

        partial_report = {
            "schema_version": LIVE_TRAINING_SCHEMA_VERSION,
            "status": "running" if epoch < int(max_epochs) else "completed",
            "monitor_status": "live_iterative_training_full_metrics",
            "model_type": "neural_mlp_live",
            "live_streaming_supported": True,
            "history_available": True,
            "n_history_rows": len(history_rows),
            "current_epoch": int(epoch),
            "max_epochs": int(max_epochs),
            "target_columns": list(target_columns),
            "target_normalization": target_scales,
            "target_scaling": target_scaling_manifest,
            "latest_epoch": row,
            "diagnostics": diagnostics,
            "artifacts": {
                "training_monitor_report_json": str(artifacts.report_json),
                "training_history_csv": str(artifacts.history_csv),
                "training_history_long_csv": str(artifacts.history_long_csv),
                "plots_dir": str(artifacts.plots_dir),
                "loss_curves_png": str(artifacts.loss_curve_png),
                "rmse_mean_curves_png": str(artifacts.rmse_mean_curve_png),
                "r2_mean_curves_png": str(artifacts.r2_mean_curve_png),
                "per_target_rmse_curves_png": str(artifacts.per_target_rmse_curve_png),
                "per_target_r2_curves_png": str(artifacts.per_target_r2_curve_png),
                "normalized_error_curves_png": str(artifacts.normalized_error_curve_png),
                "generalization_gap_curves_png": str(artifacts.generalization_gap_curve_png),
                "model_path": str(artifacts.model_path),
                "metrics_json": str(artifacts.metrics_json),
            },
            "explanation": "True live epoch-by-epoch neural MLP training with raw, normalized, and per-target metrics.",
        }
        _write_report(partial_report, artifacts.report_json)
        if epoch == int(max_epochs) or epoch % 5 == 0 or epoch == 1:
            _write_all_plots(history_df, artifacts)
        tracker.log_epoch(dict(row))
        if epoch_callback is not None:
            epoch_callback(dict(row))

    history_df = _write_history(history_rows, artifacts.history_csv)
    history_long_df = _write_long_history(long_rows, artifacts.history_long_csv)
    _write_all_plots(history_df, artifacts)

    final_train_pred = _inverse_scale_targets(_predict_2d(model, X_train), target_offsets, target_scale_values)
    final_val_pred = _inverse_scale_targets(_predict_2d(model, X_val), target_offsets, target_scale_values)
    residual_artifacts = _write_residual_artifacts(
        artifacts=artifacts,
        target_columns=target_columns,
        partitions={"train": (y_train, final_train_pred), "val": (y_val, final_val_pred)},
    )
    if X_test is not None and y_test is not None:
        final_test_pred = _inverse_scale_targets(_predict_2d(model, X_test), target_offsets, target_scale_values)
        residual_artifacts = _write_residual_artifacts(
            artifacts=artifacts,
            target_columns=target_columns,
            partitions={"train": (y_train, final_train_pred), "val": (y_val, final_val_pred), "test": (y_test, final_test_pred)},
        )

    with artifacts.model_path.open("wb") as f:
        pickle.dump(model, f)

    final_metrics = {
        "model": {
            "model_type": "neural_mlp_live",
            "display_name": "Live Neural MLP",
            "family_name": "neural_tabular_live",
            "explainability_artifact_type": "none",
            "wrapped_per_target": False,
        },
        "target_normalization": target_scales,
        "target_scaling": target_scaling_manifest,
        "final_epoch": history_rows[-1] if history_rows else {},
    }
    artifacts.metrics_json.write_text(json.dumps(final_metrics, indent=2, default=_json_default, allow_nan=False), encoding="utf-8")
    diagnostics = _diagnose_history(history_df)
    final_report = {
        "schema_version": LIVE_TRAINING_SCHEMA_VERSION,
        "created_at_utc": _utc_now_iso(),
        "status": "completed",
        "monitor_status": "live_iterative_training_full_metrics",
        "model_type": "neural_mlp_live",
        "target_columns": list(target_columns),
        "target_normalization": target_scales,
        "target_scaling": target_scaling_manifest,
        "live_streaming_supported": True,
        "history_available": True,
        "n_history_rows": len(history_rows),
        "n_history_long_rows": int(len(history_long_df)),
        "current_epoch": len(history_rows),
        "max_epochs": int(max_epochs),
        "latest_epoch": history_rows[-1] if history_rows else None,
        "diagnostics": diagnostics,
        "quality_warnings": _live_training_quality_warnings(history_rows[-1] if history_rows else None),
        "promotion_recommendation": "do_not_promote_if_quality_warnings_present",
        "metrics_summary": {
            "train_rmse_mean": history_rows[-1].get("train_rmse_mean") if history_rows else None,
            "val_rmse_mean": history_rows[-1].get("val_rmse_mean") if history_rows else None,
            "test_rmse_mean": history_rows[-1].get("test_rmse_mean") if history_rows else None,
            "train_r2_mean": history_rows[-1].get("train_r2_mean") if history_rows else None,
            "val_r2_mean": history_rows[-1].get("val_r2_mean") if history_rows else None,
            "test_r2_mean": history_rows[-1].get("test_r2_mean") if history_rows else None,
            "train_nrmse_scale_mean": history_rows[-1].get("train_nrmse_scale_mean") if history_rows else None,
            "val_nrmse_scale_mean": history_rows[-1].get("val_nrmse_scale_mean") if history_rows else None,
            "test_nrmse_scale_mean": history_rows[-1].get("test_nrmse_scale_mean") if history_rows else None,
        },
        "experiment_tracking": tracker.state.__dict__,
        "artifacts": {
            "experiment_tracking_manifest_json": str((output_dir / "tracking" / "experiment_tracking_manifest.json")),
            "training_monitor_report_json": str(artifacts.report_json),
            "training_history_csv": str(artifacts.history_csv),
            "training_history_long_csv": str(artifacts.history_long_csv),
            "plots_dir": str(artifacts.plots_dir),
            "loss_curves_png": str(artifacts.loss_curve_png),
            "rmse_mean_curves_png": str(artifacts.rmse_mean_curve_png),
            "r2_mean_curves_png": str(artifacts.r2_mean_curve_png),
            "per_target_rmse_curves_png": str(artifacts.per_target_rmse_curve_png),
            "per_target_r2_curves_png": str(artifacts.per_target_r2_curve_png),
            "normalized_error_curves_png": str(artifacts.normalized_error_curve_png),
            "generalization_gap_curves_png": str(artifacts.generalization_gap_curve_png),
            "model_path": str(artifacts.model_path),
            "metrics_json": str(artifacts.metrics_json),
            **residual_artifacts,
        },
        "recommended_next_diagnostic": "Use per-target normalized curves, generalization gaps, repeated grouped CV, and promotion gates before trusting the model.",
    }
    _write_report(final_report, artifacts.report_json)
    tracker.log_final_artifacts([
        artifacts.report_json,
        artifacts.history_csv,
        artifacts.history_long_csv,
        artifacts.plots_dir,
        artifacts.metrics_json,
    ])
    tracker_state = tracker.close()
    final_report["experiment_tracking"] = tracker_state.__dict__
    _write_report(final_report, artifacts.report_json)

    return {
        "model": model,
        "metrics": final_metrics,
        "history": history_rows,
        "history_long": long_rows,
        "report": final_report,
        "artifacts": artifacts,
    }


def run_live_neural_mlp_training(
    *,
    dataset_path: Path,
    feature_columns: list[str] | None = None,
    target_columns: list[str],
    feature_set_name: str | None = None,
    split_method: str = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.70,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
    allow_forced: bool = False,
    output_dir: Path,
    max_epochs: int = 50,
    model_params: dict[str, Any] | None = None,
    epoch_callback: EpochCallback | None = None,
    tracking_backends: list[str] | None = None,
    tracking_experiment_name: str = "aeris",
    tracking_run_name: str | None = None,
    wandb_mode: str = "offline",
) -> dict[str, Any]:
    dataset_path = Path(dataset_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser()

    feature_set: FeatureSet | None = None
    load_feature_columns: list[str]
    final_feature_columns: list[str]
    transforms: list[str] | None = None

    if feature_set_name:
        feature_set = get_feature_set(feature_set_name)
        load_feature_columns = list(feature_set.required_source_columns)
        final_feature_columns = list(feature_set.columns)
        transforms = list(feature_set.transforms)
    else:
        if not feature_columns:
            raise ValueError("feature_columns are required when feature_set_name is not supplied")
        load_feature_columns = list(feature_columns)
        final_feature_columns = list(feature_columns)

    training_data: TrainingData = load_training_data(
        dataset_path=dataset_path,
        feature_columns=load_feature_columns,
        target_columns=target_columns,
        allow_forced=allow_forced,
    )

    fe_manifest_path = output_dir / "feature_engineering_manifest.json"
    augmented_df, _fe_manifest = apply_feature_engineering(
        training_data.df,
        transforms=transforms,
        manifest_path=fe_manifest_path,
    )
    training_data.df = augmented_df

    if feature_set is not None:
        validation = validate_feature_set_dataframe(
            training_data.df,
            feature_set=feature_set,
            target_columns=target_columns,
            group_column=group_column,
        )
        if not validation.passed:
            messages = [f"{issue.code}: {issue.message}" for issue in validation.errors]
            raise ValueError("Feature set validation failed: " + "; ".join(messages))
        training_data.metadata["feature_set"] = feature_set.to_dict()

    split: DatasetSplit = split_dataset(
        training_data.df,
        method=split_method,  # type: ignore[arg-type]
        group_column=group_column,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        random_seed=random_seed,
    )
    if len(split.val_df) == 0:
        raise ValueError("Live training requires a non-empty validation split; increase val_fraction or use a larger dataset.")
    if len(split.train_df) == 0:
        raise ValueError("Live training requires a non-empty training split.")

    output_dir.mkdir(parents=True, exist_ok=True)
    train_rows_csv = output_dir / "train_rows.csv"
    val_rows_csv = output_dir / "val_rows.csv"
    test_rows_csv = output_dir / "test_rows.csv"
    split.train_df.to_csv(train_rows_csv, index=False)
    split.val_df.to_csv(val_rows_csv, index=False)
    split.test_df.to_csv(test_rows_csv, index=False)

    X_train = split.train_df[final_feature_columns].to_numpy(dtype=float)
    y_train = split.train_df[target_columns].to_numpy(dtype=float)
    X_val = split.val_df[final_feature_columns].to_numpy(dtype=float)
    y_val = split.val_df[target_columns].to_numpy(dtype=float)
    X_test = split.test_df[final_feature_columns].to_numpy(dtype=float)
    y_test = split.test_df[target_columns].to_numpy(dtype=float)

    result = run_live_mlp_arrays(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        target_columns=target_columns,
        output_dir=output_dir,
        max_epochs=max_epochs,
        random_seed=random_seed,
        model_params=model_params,
        epoch_callback=epoch_callback,
        tracking_backends=tracking_backends,
        tracking_experiment_name=tracking_experiment_name,
        tracking_run_name=tracking_run_name,
        wandb_mode=wandb_mode,
    )

    config = {
        "schema_version": "aeris.live_training_config.v1",
        "dataset_path": str(dataset_path),
        "feature_columns": final_feature_columns,
        "target_columns": list(target_columns),
        "feature_set_name": feature_set_name,
        "split_method": split_method,
        "group_column": group_column,
        "train_fraction": train_fraction,
        "val_fraction": val_fraction,
        "test_fraction": test_fraction,
        "random_seed": random_seed,
        "allow_forced": allow_forced,
        "max_epochs": max_epochs,
        "model_params": dict(model_params or {}),
        "artifacts": {
            "train_rows_csv": str(train_rows_csv),
            "val_rows_csv": str(val_rows_csv),
            "test_rows_csv": str(test_rows_csv),
            "feature_engineering_manifest_json": str(fe_manifest_path),
        },
    }
    (output_dir / "live_train_config.json").write_text(json.dumps(config, indent=2, default=_json_default), encoding="utf-8")

    artifacts: LiveTrainingArtifacts = result["artifacts"]
    result["artifacts"] = LiveTrainingArtifacts(
        output_dir=artifacts.output_dir,
        models_dir=artifacts.models_dir,
        model_path=artifacts.model_path,
        monitor_dir=artifacts.monitor_dir,
        report_json=artifacts.report_json,
        history_csv=artifacts.history_csv,
        history_long_csv=artifacts.history_long_csv,
        plots_dir=artifacts.plots_dir,
        loss_curve_png=artifacts.loss_curve_png,
        rmse_mean_curve_png=artifacts.rmse_mean_curve_png,
        r2_mean_curve_png=artifacts.r2_mean_curve_png,
        per_target_rmse_curve_png=artifacts.per_target_rmse_curve_png,
        per_target_r2_curve_png=artifacts.per_target_r2_curve_png,
        normalized_error_curve_png=artifacts.normalized_error_curve_png,
        generalization_gap_curve_png=artifacts.generalization_gap_curve_png,
        metrics_json=artifacts.metrics_json,
        train_rows_csv=train_rows_csv,
        val_rows_csv=val_rows_csv,
        test_rows_csv=test_rows_csv,
    )
    result["split"] = split
    result["training_data"] = training_data
    return result
