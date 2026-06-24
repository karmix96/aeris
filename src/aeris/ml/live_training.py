from __future__ import annotations

import json
import pickle
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

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
from aeris.ml.metrics import evaluate_regression_metrics

LIVE_TRAINING_SCHEMA_VERSION = "aeris.live_training_monitor.v2"

EpochCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class LiveTrainingArtifacts:
    output_dir: Path
    models_dir: Path
    model_path: Path
    monitor_dir: Path
    report_json: Path
    history_csv: Path
    plots_dir: Path
    loss_curve_png: Path
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
    return str(value)


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

    # Live streaming needs one optimizer step per loop. We force max_iter=1 and
    # warm_start=True, while preserving useful operator-controlled hyperparams.
    params.pop("max_iter", None)
    params.pop("warm_start", None)
    params.pop("early_stopping", None)

    mlp_params = {
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
    # Carry through harmless sklearn MLP params if the user supplied them.
    for key in ("beta_1", "beta_2", "epsilon", "nesterovs_momentum", "momentum", "power_t"):
        if key in params:
            mlp_params[key] = params.pop(key)
    if params:
        unknown = ", ".join(sorted(params))
        raise ValueError(f"Unsupported live neural_mlp parameter(s): {unknown}")

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("model", MLPRegressor(**mlp_params)),
        ]
    )


def _predict_2d(model: Any, X: np.ndarray) -> np.ndarray:
    pred = np.asarray(model.predict(X), dtype=float)
    if pred.ndim == 1:
        pred = pred.reshape(-1, 1)
    return pred


def _compact_metric_summary(y_true: np.ndarray, y_pred: np.ndarray, target_columns: list[str]) -> dict[str, float]:
    metrics = evaluate_regression_metrics(y_true, y_pred, target_columns)
    return {
        "rmse_mean": float(metrics.get("rmse_mean", np.nan)),
        "mae_mean": float(metrics.get("mae_mean", np.nan)),
        "r2_mean": float(metrics.get("r2_mean", np.nan)),
    }


def _write_live_plot(history_df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    fig = plt.figure(figsize=(8, 4.5))
    ax = fig.add_subplot(111)
    if "train_loss" in history_df.columns:
        ax.plot(history_df["epoch"], history_df["train_loss"], label="train_loss")
    if "val_rmse_mean" in history_df.columns:
        ax.plot(history_df["epoch"], history_df["val_rmse_mean"], label="val_rmse_mean")
    ax.set_xlabel("epoch")
    ax.set_ylabel("metric")
    ax.set_title("AERIS live neural MLP training")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _write_history(history_rows: list[dict[str, Any]], history_csv: Path) -> pd.DataFrame:
    history_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(history_rows)
    df.to_csv(history_csv, index=False)
    return df


def _write_report(report: dict[str, Any], report_json: Path) -> None:
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")


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
) -> dict[str, Any]:
    """Train an sklearn MLP one epoch at a time and emit live epoch events.

    This is intentionally narrow: it exists to give the GUI true live curves for
    neural/tabular MLP training. Tree/linear models remain non-iterative and are
    better assessed with AERIS learning-curves and repeated grouped CV.
    """
    output_dir = Path(output_dir).expanduser()
    monitor_dir = output_dir / "training_monitor"
    models_dir = output_dir / "models"
    plots_dir = monitor_dir / "plots"
    model_path = models_dir / "model.pkl"
    history_csv = monitor_dir / "training_history.csv"
    report_json = monitor_dir / "training_monitor_report.json"
    metrics_json = output_dir / "metrics.json"
    loss_curve_png = plots_dir / "live_training_loss_curve.png"

    output_dir.mkdir(parents=True, exist_ok=True)
    monitor_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

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

    model = _make_live_mlp(random_seed=random_seed, model_params=model_params)
    history_rows: list[dict[str, Any]] = []

    for epoch in range(1, int(max_epochs) + 1):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=ConvergenceWarning)
            model.fit(X_train, y_train)

        train_pred = _predict_2d(model, X_train)
        val_pred = _predict_2d(model, X_val)
        train_summary = _compact_metric_summary(y_train, train_pred, target_columns)
        val_summary = _compact_metric_summary(y_val, val_pred, target_columns)
        inner = model.named_steps.get("model", model)
        row = {
            "epoch": int(epoch),
            "train_loss": float(getattr(inner, "loss_", np.nan)),
            "train_rmse_mean": train_summary["rmse_mean"],
            "train_r2_mean": train_summary["r2_mean"],
            "val_rmse_mean": val_summary["rmse_mean"],
            "val_r2_mean": val_summary["r2_mean"],
        }
        history_rows.append(row)

        # Persist after every epoch so a GUI or external watcher can read it.
        history_df = _write_history(history_rows, history_csv)
        partial_report = {
            "schema_version": LIVE_TRAINING_SCHEMA_VERSION,
            "status": "running" if epoch < int(max_epochs) else "completed",
            "monitor_status": "live_iterative_training",
            "model_type": "neural_mlp_live",
            "live_streaming_supported": True,
            "history_available": True,
            "n_history_rows": len(history_rows),
            "current_epoch": int(epoch),
            "max_epochs": int(max_epochs),
            "target_columns": list(target_columns),
            "latest_epoch": row,
            "artifacts": {
                "training_monitor_report_json": str(report_json),
                "training_history_csv": str(history_csv),
                "plots_dir": str(plots_dir),
                "training_loss_curve_png": str(loss_curve_png),
                "model_path": str(model_path),
                "metrics_json": str(metrics_json),
            },
            "explanation": "True live epoch-by-epoch neural MLP training. The GUI can update charts from each emitted epoch event.",
        }
        _write_report(partial_report, report_json)
        if epoch == int(max_epochs) or epoch % 5 == 0 or epoch == 1:
            _write_live_plot(history_df, loss_curve_png)
        if epoch_callback is not None:
            epoch_callback(dict(row))

    train_pred = _predict_2d(model, X_train)
    val_pred = _predict_2d(model, X_val)
    metrics: dict[str, Any] = {
        "model": {
            "model_type": "neural_mlp_live",
            "display_name": "Live Neural MLP",
            "family_name": "neural_tabular_live",
            "explainability_artifact_type": "none",
            "wrapped_per_target": False,
        },
        "train": evaluate_regression_metrics(y_train, train_pred, target_columns),
        "val": evaluate_regression_metrics(y_val, val_pred, target_columns),
    }
    if X_test is not None and y_test is not None:
        test_pred = _predict_2d(model, X_test)
        metrics["test"] = evaluate_regression_metrics(y_test, test_pred, target_columns)

    metrics_json.write_text(json.dumps(metrics, indent=2, default=_json_default), encoding="utf-8")
    with model_path.open("wb") as f:
        pickle.dump(model, f)
    history_df = _write_history(history_rows, history_csv)
    _write_live_plot(history_df, loss_curve_png)

    final_report = {
        "schema_version": LIVE_TRAINING_SCHEMA_VERSION,
        "created_at_utc": _utc_now_iso(),
        "status": "completed",
        "monitor_status": "live_iterative_training",
        "model_type": "neural_mlp_live",
        "target_columns": list(target_columns),
        "live_streaming_supported": True,
        "history_available": True,
        "n_history_rows": len(history_rows),
        "current_epoch": len(history_rows),
        "max_epochs": int(max_epochs),
        "latest_epoch": history_rows[-1] if history_rows else None,
        "metrics_summary": {
            "train": _compact_metric_summary(y_train, train_pred, target_columns),
            "val": _compact_metric_summary(y_val, val_pred, target_columns),
            **({"test": _compact_metric_summary(y_test, _predict_2d(model, X_test), target_columns)} if X_test is not None and y_test is not None else {}),
        },
        "artifacts": {
            "training_monitor_report_json": str(report_json),
            "training_history_csv": str(history_csv),
            "plots_dir": str(plots_dir),
            "training_loss_curve_png": str(loss_curve_png),
            "model_path": str(model_path),
            "metrics_json": str(metrics_json),
        },
        "recommended_next_diagnostic": "Inspect live training curves for overfitting/plateau, then run repeated grouped CV before promotion.",
    }
    _write_report(final_report, report_json)

    artifacts = LiveTrainingArtifacts(
        output_dir=output_dir,
        models_dir=models_dir,
        model_path=model_path,
        monitor_dir=monitor_dir,
        report_json=report_json,
        history_csv=history_csv,
        plots_dir=plots_dir,
        loss_curve_png=loss_curve_png,
        metrics_json=metrics_json,
    )
    return {
        "model": model,
        "metrics": metrics,
        "history": history_rows,
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

    # Add split/config paths to the returned artifact dataclass by replacing the
    # immutable object with an augmented one.
    artifacts = result["artifacts"]
    result["artifacts"] = LiveTrainingArtifacts(
        output_dir=artifacts.output_dir,
        models_dir=artifacts.models_dir,
        model_path=artifacts.model_path,
        monitor_dir=artifacts.monitor_dir,
        report_json=artifacts.report_json,
        history_csv=artifacts.history_csv,
        plots_dir=artifacts.plots_dir,
        loss_curve_png=artifacts.loss_curve_png,
        metrics_json=artifacts.metrics_json,
        train_rows_csv=train_rows_csv,
        val_rows_csv=val_rows_csv,
        test_rows_csv=test_rows_csv,
    )
    result["split"] = split
    result["training_data"] = training_data
    return result
