from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from aeris.dataset.splitting import DatasetSplit, split_dataset
from aeris.dataset.training_data import TrainingData, load_training_data
from aeris.ml.config import load_ml_experiment_config
from aeris.ml.diagnostics import write_regression_diagnostics
from aeris.ml.fingerprints import build_dataset_fingerprints, file_sha256
from aeris.ml.manifest import build_environment_snapshot, utc_now_iso, write_ml_run_manifest
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.training_monitor import write_training_monitor
from aeris.ml.model_registry import build_model, get_model_spec
from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import FeatureSet, get_feature_set, validate_feature_set_dataframe

SplitMethod = Literal["grouped", "random"]


@dataclass(frozen=True)
class TrainConfig:
    dataset_path: str
    feature_columns: list[str]
    target_columns: list[str]
    model_type: str
    split_method: str
    group_column: str
    train_fraction: float
    val_fraction: float
    test_fraction: float
    random_seed: int
    allow_forced: bool
    model_params: dict[str, Any]
    source_config_path: str | None = None
    source_config_sha256: str | None = None
    feature_set_name: str | None = None
    feature_set: dict[str, Any] | None = None
    # AERIS_PATCH_CST_POLISH_V1
    feature_preset_name: str | None = None


@dataclass(frozen=True)
class TrainArtifacts:
    run_dir: Path
    models_dir: Path
    model_path: Path
    metrics_path: Path
    train_config_path: Path
    train_rows_path: Path
    val_rows_path: Path
    test_rows_path: Path
    coefficients_path: Path | None = None
    feature_importances_path: Path | None = None
    diagnostics_dir: Path | None = None
    feature_engineering_manifest_path: Path | None = None
    train_prediction_vs_truth_path: Path | None = None
    val_prediction_vs_truth_path: Path | None = None
    test_prediction_vs_truth_path: Path | None = None
    train_residuals_path: Path | None = None
    val_residuals_path: Path | None = None
    test_residuals_path: Path | None = None
    training_monitor_dir: Path | None = None
    training_monitor_report_path: Path | None = None
    training_history_path: Path | None = None
    training_monitor_plots_dir: Path | None = None
    ml_run_manifest_path: Path | None = None


def _ensure_run_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_columns: list[str],
) -> dict[str, Any]:
    return evaluate_regression_metrics(y_true, y_pred, target_columns)


def _fit_target_array(y: np.ndarray, target_columns: list[str]) -> np.ndarray:
    """Return y in the shape expected by sklearn estimators during fitting.

    Single-output sklearn regressors expect a 1D target array. AERIS keeps
    internal y arrays as 2D for metric/diagnostic consistency, so only squeeze
    the fit input for the one-target case. Multi-target training stays 2D.
    """
    arr = np.asarray(y, dtype=float)
    if len(target_columns) == 1 and arr.ndim == 2 and arr.shape[1] == 1:
        return arr.ravel()
    return arr


def _prediction_array_for_metrics(y_pred: Any, target_columns: list[str]) -> np.ndarray:
    """Return predictions as 2D arrays for AERIS metrics/diagnostics."""
    arr = np.asarray(y_pred, dtype=float)
    if len(target_columns) == 1 and arr.ndim == 1:
        return arr.reshape(-1, 1)
    return arr


def _write_split_rows(split: DatasetSplit, output_dir: Path) -> tuple[Path, Path, Path]:
    train_rows_path = output_dir / "train_rows.csv"
    val_rows_path = output_dir / "val_rows.csv"
    test_rows_path = output_dir / "test_rows.csv"

    split.train_df.to_csv(train_rows_path, index=False)
    split.val_df.to_csv(val_rows_path, index=False)
    split.test_df.to_csv(test_rows_path, index=False)

    return train_rows_path, val_rows_path, test_rows_path


def _unwrap_pipeline(model: Any) -> Any:
    """If model is a sklearn Pipeline, return the final estimator step."""
    steps = getattr(model, "named_steps", None)
    if steps is not None:
        return steps.get("model", model)
    return model


def _extract_coefficients_payload(
    *,
    model: Any,
    feature_columns: list[str],
    target_columns: list[str],
) -> dict[str, Any]:
    inner = _unwrap_pipeline(model)
    coef = getattr(inner, "coef_", None)
    intercept = getattr(inner, "intercept_", None)
    if coef is None or intercept is None:
        raise ValueError("Model does not expose linear coefficients.")

    coef = np.asarray(coef, dtype=float)
    intercept = np.asarray(intercept, dtype=float)

    if coef.ndim == 1:
        coef = coef.reshape(1, -1)
    if intercept.ndim == 0:
        intercept = intercept.reshape(1)

    payload: dict[str, Any] = {"targets": {}}
    for idx, target in enumerate(target_columns):
        payload["targets"][target] = {
            "intercept": float(intercept[idx]),
            "coefficients": {
                feature: float(coef[idx, feat_idx])
                for feat_idx, feature in enumerate(feature_columns)
            },
        }
    return payload


def _extract_wrapped_coefficients_payload(
    *,
    model: Any,
    feature_columns: list[str],
    target_columns: list[str],
) -> dict[str, Any]:
    inner = _unwrap_pipeline(model)
    estimators = getattr(inner, "estimators_", None)
    if estimators is None or len(estimators) != len(target_columns):
        raise ValueError("Wrapped model does not expose per-target estimators correctly.")

    payload: dict[str, Any] = {"targets": {}}
    for target, estimator in zip(target_columns, estimators):
        coef = np.asarray(estimator.coef_, dtype=float)
        intercept = float(np.asarray(estimator.intercept_, dtype=float).reshape(-1)[0])
        payload["targets"][target] = {
            "intercept": intercept,
            "coefficients": {
                feature: float(coef[feat_idx])
                for feat_idx, feature in enumerate(feature_columns)
            },
        }
    return payload


def _extract_feature_importances_payload(
    *,
    model: Any,
    feature_columns: list[str],
    target_columns: list[str],
    wrapped_per_target: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"targets": {}}

    if wrapped_per_target:
        estimators = getattr(model, "estimators_", None)
        if estimators is None or len(estimators) != len(target_columns):
            raise ValueError("Wrapped model does not expose per-target estimators correctly.")

        for target, estimator in zip(target_columns, estimators):
            importances = getattr(estimator, "feature_importances_", None)
            if importances is None:
                raise ValueError(
                    f"Estimator for target '{target}' does not expose feature_importances_."
                )
            arr = np.asarray(importances, dtype=float)
            payload["targets"][target] = {
                "feature_importances": {
                    feature: float(arr[feat_idx])
                    for feat_idx, feature in enumerate(feature_columns)
                }
            }
        return payload

    # Native multi-output models (RandomForest, ExtraTrees) have one shared
    # feature_importances_ array — not one per target. Store it once under
    # "shared" to avoid fabricating fake per-target explanations.
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        raise ValueError("Model does not expose feature_importances_.")

    arr = np.asarray(importances, dtype=float)
    payload["shared"] = {
        feature: float(arr[feat_idx])
        for feat_idx, feature in enumerate(feature_columns)
    }
    # Keep targets dict present but empty — consumers must use payload["shared"]
    payload["targets"] = {}
    return payload


def _write_explainability_artifacts(
    *,
    model: Any,
    model_type: str,
    feature_columns: list[str],
    target_columns: list[str],
    output_dir: Path,
) -> tuple[Path | None, Path | None]:
    spec = get_model_spec(model_type)

    if spec.explainability_artifact_type == "coefficients":
        if spec.wrapped_per_target:
            payload = _extract_wrapped_coefficients_payload(
                model=model,
                feature_columns=feature_columns,
                target_columns=target_columns,
            )
        else:
            payload = _extract_coefficients_payload(
                model=model,
                feature_columns=feature_columns,
                target_columns=target_columns,
            )

        path = output_dir / "coefficients.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path, None

    if spec.explainability_artifact_type == "feature_importances":
        payload = _extract_feature_importances_payload(
            model=model,
            feature_columns=feature_columns,
            target_columns=target_columns,
            wrapped_per_target=spec.wrapped_per_target,
        )
        path = output_dir / "feature_importances.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return None, path

    return None, None


def train_baseline_model(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: str = "linear_regression",
    split_method: SplitMethod = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
    allow_forced: bool = False,
    model_params: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    source_config_path: Path | None = None,
    feature_set_name: str | None = None,
    feature_preset_name: str | None = None,
) -> dict[str, Any]:
    dataset_path = Path(dataset_path).expanduser().resolve()

    feature_set: FeatureSet | None = None
    feature_set_metadata: dict[str, Any] | None = None
    load_feature_columns = list(feature_columns)
    final_feature_columns = list(feature_columns)
    feature_engineering_transforms: list[str] | None = None

    if feature_set_name is not None:
        feature_set = get_feature_set(feature_set_name)
        feature_set_metadata = feature_set.to_dict()
        load_feature_columns = list(feature_set.required_source_columns)
        final_feature_columns = list(feature_set.columns)
        feature_engineering_transforms = list(feature_set.transforms)

        if list(feature_columns) and list(feature_columns) != final_feature_columns:
            raise ValueError(
                f"feature_columns must match feature set '{feature_set.name}' final columns when feature_set_name is used. "
                f"Expected {final_feature_columns}; got {list(feature_columns)}"
            )

    training_data: TrainingData = load_training_data(
        dataset_path=dataset_path,
        feature_columns=load_feature_columns,
        target_columns=target_columns,
        allow_forced=allow_forced,
    )

    # SCI.3 — Resolve output_dir early so fe manifest path is valid.
    if output_dir is None:
        output_dir = (
            Path("data")
            / "processed"
            / "ml_runs"
            / f"{model_type}__{dataset_path.name}__seed{random_seed}"
        )
    output_dir = _ensure_run_dir(output_dir)

    # Apply feature engineering before split.
    # If a named feature set is used, only its declared transforms are applied.
    # Otherwise the legacy/default transform behavior is preserved.
    _fe_manifest_path = output_dir / "feature_engineering_manifest.json"
    _augmented_df, _fe_manifest = apply_feature_engineering(
        training_data.df,
        transforms=feature_engineering_transforms,
        manifest_path=_fe_manifest_path,
    )

    if feature_set is not None:
        validation = validate_feature_set_dataframe(
            _augmented_df,
            feature_set=feature_set,
            target_columns=target_columns,
            group_column=group_column,
        )
        if not validation.passed:
            messages = [f"{issue.code}: {issue.message}" for issue in validation.errors]
            raise ValueError("Feature-set validation failed before training: " + "; ".join(messages))

    # Update df/X on the existing TrainingData instance.
    # TrainingData is a non-frozen dataclass — direct assignment is safe.
    training_data.df = _augmented_df
    training_data.feature_columns = list(final_feature_columns)
    training_data.X = training_data.df[final_feature_columns].copy()
    training_data.metadata["feature_columns"] = list(final_feature_columns)
    training_data.metadata["n_features"] = int(len(final_feature_columns))
    training_data.metadata["feature_set_name"] = None if feature_set is None else feature_set.name
    training_data.metadata["feature_set"] = feature_set_metadata

    feature_columns = list(final_feature_columns)

    split: DatasetSplit = split_dataset(
        training_data.df,
        method=split_method,
        group_column=group_column,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        random_seed=random_seed,
    )

    X_train = split.train_df[feature_columns].to_numpy(dtype=float)
    y_train = split.train_df[target_columns].to_numpy(dtype=float)

    X_val = split.val_df[feature_columns].to_numpy(dtype=float)
    y_val = split.val_df[target_columns].to_numpy(dtype=float)

    X_test = split.test_df[feature_columns].to_numpy(dtype=float)
    y_test = split.test_df[target_columns].to_numpy(dtype=float)

    spec = get_model_spec(model_type)
    model = build_model(
        model_type=model_type,
        random_seed=random_seed,
        model_params=model_params,
    )
    fit_y_train = _fit_target_array(y_train, target_columns)
    model.fit(X_train, fit_y_train)

    y_pred_train = _prediction_array_for_metrics(model.predict(X_train), target_columns)
    y_pred_val = _prediction_array_for_metrics(model.predict(X_val), target_columns)
    y_pred_test = _prediction_array_for_metrics(model.predict(X_test), target_columns)

    metrics = {
        "model": {
            "model_type": spec.model_type,
            "display_name": spec.display_name,
            "family_name": spec.family_name,
            "explainability_artifact_type": spec.explainability_artifact_type,
            "wrapped_per_target": spec.wrapped_per_target,
        },
        "train": _evaluate_predictions(y_train, y_pred_train, target_columns),
        "val": _evaluate_predictions(y_val, y_pred_val, target_columns),
        "test": _evaluate_predictions(y_test, y_pred_test, target_columns),
    }

    source_config_path_resolved: Path | None = None
    source_config_sha256: str | None = None
    if source_config_path is not None:
        source_config_path_resolved = Path(source_config_path).expanduser().resolve()
        source_config_sha256 = file_sha256(source_config_path_resolved)

    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    model_path = models_dir / "model.pkl"
    with model_path.open("wb") as f:
        pickle.dump(model, f)

    diagnostics_dir = output_dir / "diagnostics"
    train_diag = write_regression_diagnostics(
        partition_name="train",
        df=split.train_df,
        target_columns=target_columns,
        y_true=y_train,
        y_pred=y_pred_train,
        output_dir=diagnostics_dir,
    )
    val_diag = write_regression_diagnostics(
        partition_name="val",
        df=split.val_df,
        target_columns=target_columns,
        y_true=y_val,
        y_pred=y_pred_val,
        output_dir=diagnostics_dir,
    )
    test_diag = write_regression_diagnostics(
        partition_name="test",
        df=split.test_df,
        target_columns=target_columns,
        y_true=y_test,
        y_pred=y_pred_test,
        output_dir=diagnostics_dir,
    )
    metrics["diagnostics"] = {
        "train": train_diag,
        "val": val_diag,
        "test": test_diag,
    }

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    training_monitor = write_training_monitor(
        model=model,
        model_type=model_type,
        metrics=metrics,
        output_dir=output_dir / "training_monitor",
        target_columns=target_columns,
    )

    train_config = TrainConfig(
        dataset_path=str(dataset_path),
        feature_columns=list(feature_columns),
        target_columns=list(target_columns),
        model_type=model_type,
        split_method=split_method,
        group_column=group_column,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        random_seed=random_seed,
        allow_forced=allow_forced,
        model_params=dict(model_params or {}),
        source_config_path=None if source_config_path_resolved is None else str(source_config_path_resolved),
        source_config_sha256=source_config_sha256,
        feature_set_name=feature_set.name if feature_set is not None else None,
        feature_set=feature_set_metadata,
        feature_preset_name=feature_preset_name,
    )
    train_config_path = output_dir / "train_config.json"
    train_config_path.write_text(
        json.dumps(asdict(train_config), indent=2),
        encoding="utf-8",
    )

    train_rows_path, val_rows_path, test_rows_path = _write_split_rows(split, output_dir)

    coefficients_path, feature_importances_path = _write_explainability_artifacts(
        model=model,
        model_type=model_type,
        feature_columns=feature_columns,
        target_columns=target_columns,
        output_dir=output_dir,
    )

    curated_csv_path = training_data.metadata.get("curated_csv_path")
    dataset_fingerprints = build_dataset_fingerprints(
        dataset_path=dataset_path,
        curated_csv_path=curated_csv_path,
    )
    split_fingerprints = {
        "train_rows_csv": {"path": str(train_rows_path), "sha256": file_sha256(train_rows_path)},
        "val_rows_csv": {"path": str(val_rows_path), "sha256": file_sha256(val_rows_path)},
        "test_rows_csv": {"path": str(test_rows_path), "sha256": file_sha256(test_rows_path)},
    }

    ml_run_manifest = {
        "schema_version": "aeris.ml_run_manifest.v1",
        "status": "success",
        "created_at_utc": utc_now_iso(),
        "run_dir": str(output_dir),
        # AERIS_PATCH_CST_POLISH_V1: top-level quick-inspection aliases.
        "feature_preset": feature_preset_name,
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "group_column": group_column,
        "model_type": model_type,
        "split_method": split.method,
        "source_config": {
            "path": None if source_config_path_resolved is None else str(source_config_path_resolved),
            "sha256": source_config_sha256,
        },
        "environment": build_environment_snapshot(),
        "dataset": {
            "dataset_path": str(dataset_path),
            "curated_csv_path": str(curated_csv_path),
            "fingerprints": dataset_fingerprints,
            "promotion_context": training_data.metadata.get("promotion_context"),
        },
        "training_data": {
            "n_samples": training_data.metadata.get("n_samples"),
            "n_features": training_data.metadata.get("n_features"),
            "n_targets": training_data.metadata.get("n_targets"),
            "feature_columns": list(feature_columns),
            "target_columns": list(target_columns),
            "feature_preset_name": feature_preset_name,
            "feature_set_name": training_data.metadata.get("feature_set_name"),
            "feature_set": training_data.metadata.get("feature_set"),
            "dropped_non_finite_rows": training_data.metadata.get("dropped_non_finite_rows"),
        },
        "split": {
            "method": split.method,
            "metadata": getattr(split, "metadata", {}),
            "train_rows": int(len(split.train_df)),
            "val_rows": int(len(split.val_df)),
            "test_rows": int(len(split.test_df)),
            "fingerprints": split_fingerprints,
        },
        "model": metrics["model"],
        "metrics": metrics,
        "artifacts": {
            "model_path": str(model_path),
            "metrics_path": str(metrics_path),
            "train_config_path": str(train_config_path),
            "diagnostics_dir": str(diagnostics_dir),
            "training_monitor_report_path": str(training_monitor.report_path),
            "training_history_path": None if training_monitor.history_path is None else str(training_monitor.history_path),
            "training_monitor_plots_dir": None if training_monitor.plots_dir is None else str(training_monitor.plots_dir),
            "coefficients_path": None if coefficients_path is None else str(coefficients_path),
            "feature_importances_path": None if feature_importances_path is None else str(feature_importances_path),
        },
    }
    ml_run_manifest_path = write_ml_run_manifest(
        output_dir / "ml_run_manifest.json",
        ml_run_manifest,
    )

    artifacts = TrainArtifacts(
        run_dir=output_dir,
        models_dir=models_dir,
        model_path=model_path,
        metrics_path=metrics_path,
        train_config_path=train_config_path,
        train_rows_path=train_rows_path,
        val_rows_path=val_rows_path,
        test_rows_path=test_rows_path,
        coefficients_path=coefficients_path,
        feature_importances_path=feature_importances_path,
        diagnostics_dir=diagnostics_dir,
        training_monitor_dir=training_monitor.monitor_dir,
        training_monitor_report_path=training_monitor.report_path,
        training_history_path=training_monitor.history_path,
        training_monitor_plots_dir=training_monitor.plots_dir,
        feature_engineering_manifest_path=_fe_manifest_path,
        train_prediction_vs_truth_path=Path(train_diag["prediction_vs_truth_csv"]),
        val_prediction_vs_truth_path=Path(val_diag["prediction_vs_truth_csv"]),
        test_prediction_vs_truth_path=Path(test_diag["prediction_vs_truth_csv"]),
        train_residuals_path=Path(train_diag["residuals_csv"]),
        val_residuals_path=Path(val_diag["residuals_csv"]),
        test_residuals_path=Path(test_diag["residuals_csv"]),
        ml_run_manifest_path=ml_run_manifest_path,
    )

    return {
        "model": model,
        "training_data": training_data,
        "split": split,
        "metrics": metrics,
        "artifacts": artifacts,
    }


def train_baseline_model_from_config(
    config_path: str | Path,
    *,
    output_dir: Path | None = None,
    model_params_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Train a baseline model from a YAML ML experiment config.

    `output_dir` and `model_params_override` are explicit CLI/programmatic overrides.
    Config values remain the default source of truth.
    """
    config_path = Path(config_path).expanduser().resolve()
    cfg = load_ml_experiment_config(config_path)

    model_params = dict(cfg.model_params)
    if model_params_override:
        model_params.update(model_params_override)

    return train_baseline_model(
        dataset_path=cfg.dataset_path,
        feature_columns=cfg.feature_columns,
        target_columns=cfg.target_columns,
        model_type=cfg.model_type,
        split_method=cfg.split_method,
        group_column=cfg.group_column,
        train_fraction=cfg.train_fraction,
        val_fraction=cfg.val_fraction,
        test_fraction=cfg.test_fraction,
        random_seed=cfg.random_seed,
        allow_forced=cfg.allow_forced,
        model_params=model_params,
        output_dir=output_dir if output_dir is not None else cfg.output_dir,
        source_config_path=config_path,
        feature_set_name=None,
    )