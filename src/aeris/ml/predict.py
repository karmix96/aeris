from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


@dataclass(frozen=True)
class PredictArtifacts:
    run_dir: Path
    model_path: Path
    train_config_path: Path
    input_csv_path: Path
    predictions_csv_path: Path
    prediction_summary_path: Path


def _ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_train_config(model_run_dir: Path) -> dict[str, Any]:
    path = model_run_dir / "train_config.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing train_config.json in model run dir: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_model_path(model_run_dir: Path) -> Path:
    candidates = [
        model_run_dir / "models" / "model.pkl",
        model_run_dir / "model.pkl",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Could not find model.pkl under model run dir: {model_run_dir}"
    )


def _load_model(model_path: Path) -> Any:
    with model_path.open("rb") as f:
        return pickle.load(f)


def _validate_input_columns(
    df: pd.DataFrame,
    required_feature_columns: list[str],
) -> None:
    missing = [col for col in required_feature_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"Input CSV is missing required feature columns: {missing}"
        )


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


def predict_with_trained_model(
    *,
    model_run_dir: Path,
    input_csv: Path,
    output_dir: Path | None = None,
    include_truth_if_available: bool = True,
) -> dict[str, Any]:
    """
    Load a saved AERIS ML model run and produce predictions on a new CSV.

    Workflow:
    1. Load saved train_config.json
    2. Load fitted model.pkl
    3. Load input CSV
    4. Validate required feature columns
    5. Predict target columns
    6. Save predictions.csv
    7. Save prediction_summary.json
    8. If true target columns are present, also compute metrics
    """
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    input_csv = Path(input_csv).expanduser().resolve()

    if not model_run_dir.exists():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV does not exist: {input_csv}")

    train_config = _load_train_config(model_run_dir)
    model_path = _resolve_model_path(model_run_dir)
    model = _load_model(model_path)

    feature_columns = list(train_config["feature_columns"])
    target_columns = list(train_config["target_columns"])
    model_type = str(train_config["model_type"])

    df = pd.read_csv(input_csv)
    _validate_input_columns(df, feature_columns)

    X = df[feature_columns].to_numpy(dtype=float)
    y_pred = np.asarray(model.predict(X), dtype=float)
    if y_pred.ndim == 1:
        y_pred = y_pred.reshape(-1, 1)

    output_df = df.copy()
    for idx, target in enumerate(target_columns):
        output_df[f"pred__{target}"] = y_pred[:, idx]

    evaluation: dict[str, Any] | None = None
    truth_available = all(col in df.columns for col in target_columns)

    if include_truth_if_available and truth_available:
        y_true = df[target_columns].to_numpy(dtype=float)
        evaluation = _evaluate_predictions(y_true, y_pred, target_columns)

        for idx, target in enumerate(target_columns):
            output_df[f"error__{target}"] = output_df[f"pred__{target}"] - output_df[target]

    if output_dir is None:
        output_dir = model_run_dir / "inference" / input_csv.stem
    output_dir = _ensure_output_dir(output_dir)

    predictions_csv_path = output_dir / "predictions.csv"
    prediction_summary_path = output_dir / "prediction_summary.json"

    output_df.to_csv(predictions_csv_path, index=False)

    summary = {
        "model_run_dir": str(model_run_dir),
        "model_path": str(model_path),
        "train_config_path": str(model_run_dir / "train_config.json"),
        "input_csv_path": str(input_csv),
        "predictions_csv_path": str(predictions_csv_path),
        "model_type": model_type,
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "n_rows": int(len(df)),
        "truth_available": bool(truth_available),
        "evaluation": evaluation,
    }

    prediction_summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    artifacts = PredictArtifacts(
        run_dir=output_dir,
        model_path=model_path,
        train_config_path=model_run_dir / "train_config.json",
        input_csv_path=input_csv,
        predictions_csv_path=predictions_csv_path,
        prediction_summary_path=prediction_summary_path,
    )

    return {
        "summary": summary,
        "artifacts": artifacts,
        "predictions_df": output_df,
    }