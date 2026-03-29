from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from aeris.dataset.splitting import DatasetSplit, split_dataset
from aeris.dataset.training_data import TrainingData, load_training_data


ModelType = Literal["linear_regression", "random_forest"]
SplitMethod = Literal["random", "grouped"]


@dataclass
class TrainConfig:
    dataset_path: str
    feature_columns: list[str]
    target_columns: list[str]
    model_type: ModelType
    split_method: SplitMethod
    group_column: str
    train_fraction: float
    val_fraction: float
    test_fraction: float
    random_seed: int
    allow_forced: bool
    model_params: dict[str, Any]


@dataclass
class TrainArtifacts:
    run_dir: Path
    metrics_path: Path
    config_path: Path
    models_dir: Path


def _evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_names: list[str],
) -> dict[str, Any]:
    metrics_by_target: dict[str, dict[str, float]] = {}

    for i, name in enumerate(target_names):
        yt = y_true[:, i]
        yp = y_pred[:, i]

        rmse = float(np.sqrt(mean_squared_error(yt, yp)))
        mae = float(mean_absolute_error(yt, yp))
        r2 = float(r2_score(yt, yp))

        metrics_by_target[name] = {
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
        }

    overall = {
        "rmse_mean": float(np.mean([m["rmse"] for m in metrics_by_target.values()])),
        "mae_mean": float(np.mean([m["mae"] for m in metrics_by_target.values()])),
        "r2_mean": float(np.mean([m["r2"] for m in metrics_by_target.values()])),
    }

    return {
        "per_target": metrics_by_target,
        "overall": overall,
    }


def _build_model(
    model_type: ModelType,
    *,
    random_seed: int,
    model_params: dict[str, Any] | None = None,
):
    params = dict(model_params or {})

    if model_type == "linear_regression":
        return LinearRegression(**params)

    if model_type == "random_forest":
        default_params = {
            "n_estimators": 200,
            "max_depth": None,
            "min_samples_split": 2,
            "min_samples_leaf": 1,
            "random_state": random_seed,
            "n_jobs": -1,
        }
        default_params.update(params)
        return RandomForestRegressor(**default_params)

    raise ValueError(f"Unsupported model_type: {model_type}")


def _ensure_run_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def train_baseline_model(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_type: ModelType = "linear_regression",
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

    model = _build_model(
        model_type,
        random_seed=random_seed,
        model_params=model_params,
    )
    model.fit(X_train, y_train)

    y_pred_train = model.predict(X_train)
    y_pred_val = model.predict(X_val)
    y_pred_test = model.predict(X_test)

    metrics = {
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

    config = TrainConfig(
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

    config_path = output_dir / "train_config.json"
    config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    metrics_payload = {
        "dataset_name": dataset_path.name,
        "model_type": model_type,
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "random_seed": random_seed,
        "training_data_metadata": training_data.metadata,
        "split_metadata": split.metadata,
        "metrics": metrics,
        "artifacts": {
            "model_path": str(model_path),
            "config_path": str(config_path),
        },
    }

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    artifacts = TrainArtifacts(
        run_dir=output_dir,
        metrics_path=metrics_path,
        config_path=config_path,
        models_dir=models_dir,
    )

    return {
        "model": model,
        "metrics": metrics,
        "training_data": training_data,
        "split": split,
        "artifacts": artifacts,
        "metrics_payload": metrics_payload,
    }