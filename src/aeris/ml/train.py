from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from aeris.dataset.splitting import DatasetSplit, split_dataset
from aeris.dataset.training_data import TrainingData, load_training_data
from aeris.ml.model_registry import build_model, get_model_spec

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


def _ensure_run_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_columns: list[str],
) -> dict[str, Any]:
    if y_true.ndim == 1:
        y_true = y_true.reshape(-1, 1)
    if y_pred.ndim == 1:
        y_pred = y_pred.reshape(-1, 1)

    per_target: dict[str, dict[str, float]] = {}
    rmse_values: list[float] = []
    mae_values: list[float] = []
    r2_values: list[float] = []

    for idx, target in enumerate(target_columns):
        y_true_col = y_true[:, idx]
        y_pred_col = y_pred[:, idx]

        rmse = float(np.sqrt(mean_squared_error(y_true_col, y_pred_col)))
        mae = float(mean_absolute_error(y_true_col, y_pred_col))
        r2 = float(r2_score(y_true_col, y_pred_col))

        per_target[target] = {
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
        }

        rmse_values.append(rmse)
        mae_values.append(mae)
        r2_values.append(r2)

    return {
        "per_target": per_target,
        "overall": {
            "rmse_mean": float(np.mean(rmse_values)),
            "mae_mean": float(np.mean(mae_values)),
            "r2_mean": float(np.mean(r2_values)),
        },
    }


def _write_split_rows(split: DatasetSplit, output_dir: Path) -> tuple[Path, Path, Path]:
    train_rows_path = output_dir / "train_rows.csv"
    val_rows_path = output_dir / "val_rows.csv"
    test_rows_path = output_dir / "test_rows.csv"

    split.train_df.to_csv(train_rows_path, index=False)
    split.val_df.to_csv(val_rows_path, index=False)
    split.test_df.to_csv(test_rows_path, index=False)

    return train_rows_path, val_rows_path, test_rows_path


def _extract_coefficients_payload(
    *,
    model: Any,
    feature_columns: list[str],
    target_columns: list[str],
) -> dict[str, Any]:
    coef = getattr(model, "coef_", None)
    intercept = getattr(model, "intercept_", None)
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
    estimators = getattr(model, "estimators_", None)
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

    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        raise ValueError("Model does not expose feature_importances_.")

    arr = np.asarray(importances, dtype=float)
    shared = {
        feature: float(arr[feat_idx])
        for feat_idx, feature in enumerate(feature_columns)
    }
    for target in target_columns:
        payload["targets"][target] = {"feature_importances": dict(shared)}
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
) -> dict[str, Any]:
    dataset_path = Path(dataset_path).expanduser().resolve()

    training_data: TrainingData = load_training_data(
        dataset_path=dataset_path,
        feature_columns=feature_columns,
        target_columns=target_columns,
        allow_forced=allow_forced,
    )

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
    model.fit(X_train, y_train)

    y_pred_train = np.asarray(model.predict(X_train), dtype=float)
    y_pred_val = np.asarray(model.predict(X_val), dtype=float)
    y_pred_test = np.asarray(model.predict(X_test), dtype=float)

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

    if output_dir is None:
        output_dir = (
            Path("data")
            / "processed"
            / "ml_runs"
            / f"{model_type}__{dataset_path.name}__seed{random_seed}"
        )
    output_dir = _ensure_run_dir(output_dir)

    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    model_path = models_dir / "model.pkl"
    with model_path.open("wb") as f:
        pickle.dump(model, f)

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

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
    )

    return {
        "model": model,
        "training_data": training_data,
        "split": split,
        "metrics": metrics,
        "artifacts": artifacts,
    }