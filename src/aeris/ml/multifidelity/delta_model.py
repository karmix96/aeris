from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from aeris.dataset.splitting import DatasetSplit, split_dataset
from aeris.ml.diagnostics import write_regression_diagnostics
from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import FeatureSetError, get_feature_set
from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import build_environment_snapshot, utc_now_iso, write_ml_run_manifest
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.model_registry import build_model, get_model_spec

SplitMethod = Literal["grouped", "random"]
DELTA_MODEL_MANIFEST_SCHEMA_VERSION = "aeris.multifidelity_delta_model_run.v1"
DELTA_PREDICTION_SCHEMA_VERSION = "aeris.multifidelity_delta_prediction.v1"


@dataclass(frozen=True)
class DeltaTrainArtifacts:
    run_dir: Path
    models_dir: Path
    model_path: Path
    metrics_path: Path
    train_config_path: Path
    manifest_path: Path
    train_rows_path: Path
    val_rows_path: Path
    test_rows_path: Path
    diagnostics_dir: Path
    feature_importances_path: Path | None = None
    coefficients_path: Path | None = None


@dataclass(frozen=True)
class DeltaPredictArtifacts:
    output_dir: Path
    predictions_csv: Path
    prediction_summary_json: Path


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_delta_dataset_csv(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    if p.is_dir():
        p = p / "delta_dataset.csv"
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Delta dataset CSV does not exist: {p}")
    return p


def _load_delta_dataset(path: str | Path) -> tuple[Path, pd.DataFrame]:
    csv_path = _resolve_delta_dataset_csv(path)
    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError(f"Delta dataset is empty: {csv_path}")
    return csv_path, df


def _require_columns(df: pd.DataFrame, columns: list[str], *, label: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def _validate_numeric_columns(df: pd.DataFrame, columns: list[str], *, label: str) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        numeric = pd.to_numeric(out[col], errors="coerce")
        arr = numeric.to_numpy(dtype=float, na_value=np.nan)
        bad = ~np.isfinite(arr)
        if bad.any():
            raise ValueError(f"{label} column '{col}' contains {int(bad.sum())} non-finite/non-numeric values")
        out[col] = numeric.astype(float)
    return out




def _prepare_delta_feature_frame(
    df: pd.DataFrame,
    *,
    feature_columns: list[str] | None,
    feature_set_name: str | None,
    base_targets: list[str],
    lf_prefix: str,
) -> tuple[pd.DataFrame, list[str], dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve explicit or named feature-set inputs for a delta-model DataFrame.

    Delta learning needs both the geometry/condition representation and the LF
    target columns. With a feature set, AERIS applies declared transforms to raw
    geometry/condition columns, then appends lf__<target> columns as mandatory
    correction inputs. This keeps multifidelity learning aligned with the normal
    scalar ML feature-set trust chain.
    """
    explicit = list(feature_columns or [])
    clean_feature_set = None if feature_set_name is None else str(feature_set_name).strip() or None

    if explicit and clean_feature_set:
        raise ValueError("Use only one of feature_columns or feature_set_name for delta-model training/prediction.")
    if not explicit and not clean_feature_set:
        raise ValueError("feature_columns or feature_set_name must be provided for delta-model training/prediction.")

    lf_columns = [f"{lf_prefix}{target}" for target in base_targets]

    if not clean_feature_set:
        return df.copy(), explicit, None, None

    try:
        feature_set = get_feature_set(clean_feature_set)
    except FeatureSetError as exc:
        raise ValueError(str(exc)) from exc

    missing_sources = [column for column in feature_set.required_source_columns if column not in df.columns]
    if missing_sources:
        raise ValueError(
            f"missing_feature_set_source_columns: Delta dataset/input is missing raw source columns "
            f"required by feature set '{feature_set.name}': {missing_sources}"
        )

    augmented_df, feature_engineering_manifest = apply_feature_engineering(
        df,
        transforms=list(feature_set.transforms),
    )
    missing_final = [column for column in feature_set.columns if column not in augmented_df.columns]
    if missing_final:
        raise ValueError(
            f"missing_feature_set_columns_after_transforms: Feature set '{feature_set.name}' did not produce "
            f"required columns: {missing_final}"
        )

    final_features = list(feature_set.columns) + lf_columns
    return augmented_df, final_features, feature_set.to_dict(), feature_engineering_manifest


def _check_delta_feature_set_mismatch(
    *,
    trained_feature_set_name: str | None,
    requested_feature_set_name: str | None,
    allow_feature_set_mismatch: bool,
) -> None:
    trained = None if trained_feature_set_name is None else str(trained_feature_set_name).strip() or None
    requested = None if requested_feature_set_name is None else str(requested_feature_set_name).strip() or None
    if requested is None:
        return
    if trained is None and not allow_feature_set_mismatch:
        raise ValueError(
            f"Feature-set mismatch: delta model was trained without a feature set, but inference requested "
            f"'{requested}'. Use --allow-feature-set-mismatch only for deliberate debugging or migration."
        )
    if trained is not None and requested != trained and not allow_feature_set_mismatch:
        raise ValueError(
            f"Feature-set mismatch: delta model was trained with feature set '{trained}', but inference requested "
            f"'{requested}'. Use --allow-feature-set-mismatch only for deliberate debugging or migration."
        )

def _target_columns(base_targets: list[str], *, delta_prefix: str, lf_prefix: str, hf_prefix: str) -> tuple[list[str], list[str], list[str]]:
    delta_cols = [f"{delta_prefix}{t}" for t in base_targets]
    lf_cols = [f"{lf_prefix}{t}" for t in base_targets]
    hf_cols = [f"{hf_prefix}{t}" for t in base_targets]
    return delta_cols, lf_cols, hf_cols


def _arrays(df: pd.DataFrame, *, feature_columns: list[str], delta_columns: list[str]) -> tuple[np.ndarray, np.ndarray]:
    return df[feature_columns].to_numpy(dtype=float), df[delta_columns].to_numpy(dtype=float)


def _write_split_rows(split: DatasetSplit, output_dir: Path) -> tuple[Path, Path, Path]:
    train_rows_path = output_dir / "train_rows.csv"
    val_rows_path = output_dir / "val_rows.csv"
    test_rows_path = output_dir / "test_rows.csv"
    split.train_df.to_csv(train_rows_path, index=False)
    split.val_df.to_csv(val_rows_path, index=False)
    split.test_df.to_csv(test_rows_path, index=False)
    return train_rows_path, val_rows_path, test_rows_path


def _evaluate_partition(
    *,
    model: Any,
    df: pd.DataFrame,
    feature_columns: list[str],
    base_targets: list[str],
    delta_columns: list[str],
    lf_columns: list[str],
    hf_columns: list[str],
) -> dict[str, Any]:
    X = df[feature_columns].to_numpy(dtype=float)
    y_delta = df[delta_columns].to_numpy(dtype=float)
    pred_delta = np.asarray(model.predict(X), dtype=float)
    if pred_delta.ndim == 1:
        pred_delta = pred_delta.reshape(-1, 1)

    lf = df[lf_columns].to_numpy(dtype=float)
    hf = df[hf_columns].to_numpy(dtype=float)
    corrected = lf + pred_delta

    return {
        "delta": evaluate_regression_metrics(y_delta, pred_delta, delta_columns),
        "corrected": evaluate_regression_metrics(hf, corrected, base_targets),
    }


def _write_corrected_predictions(
    *,
    partition_name: str,
    model: Any,
    df: pd.DataFrame,
    feature_columns: list[str],
    base_targets: list[str],
    delta_columns: list[str],
    lf_columns: list[str],
    hf_columns: list[str],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    X = df[feature_columns].to_numpy(dtype=float)
    pred_delta = np.asarray(model.predict(X), dtype=float)
    if pred_delta.ndim == 1:
        pred_delta = pred_delta.reshape(-1, 1)

    out = df.reset_index(drop=True).copy()
    for idx, target in enumerate(base_targets):
        lf_col = lf_columns[idx]
        hf_col = hf_columns[idx]
        delta_col = delta_columns[idx]
        pred_delta_col = f"pred__{delta_col}"
        pred_corrected_col = f"pred_corrected__{target}"
        error_corrected_col = f"error_corrected__{target}"
        out[pred_delta_col] = pred_delta[:, idx]
        out[pred_corrected_col] = out[lf_col].astype(float) + out[pred_delta_col]
        out[error_corrected_col] = out[pred_corrected_col] - out[hf_col].astype(float)

    path = output_dir / f"{partition_name}_corrected_predictions.csv"
    out.to_csv(path, index=False)
    return path


def _write_explainability(
    *,
    model: Any,
    model_type: str,
    feature_columns: list[str],
    target_columns: list[str],
    output_dir: Path,
) -> tuple[Path | None, Path | None]:
    spec = get_model_spec(model_type)
    if spec.explainability_artifact_type == "feature_importances":
        payload: dict[str, Any] = {"targets": {}}
        if spec.wrapped_per_target:
            estimators = getattr(model, "estimators_", None)
            if estimators is None:
                return None, None
            for target, estimator in zip(target_columns, estimators):
                importances = getattr(estimator, "feature_importances_", None)
                if importances is None:
                    continue
                arr = np.asarray(importances, dtype=float)
                payload["targets"][target] = {
                    "feature_importances": {feature: float(arr[i]) for i, feature in enumerate(feature_columns)}
                }
        else:
            importances = getattr(model, "feature_importances_", None)
            if importances is None:
                return None, None
            arr = np.asarray(importances, dtype=float)
            shared = {feature: float(arr[i]) for i, feature in enumerate(feature_columns)}
            for target in target_columns:
                payload["targets"][target] = {"feature_importances": dict(shared)}
        path = output_dir / "feature_importances.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return None, path

    if spec.explainability_artifact_type == "coefficients":
        coef = getattr(model, "coef_", None)
        intercept = getattr(model, "intercept_", None)
        if coef is None or intercept is None:
            return None, None
        coef_arr = np.asarray(coef, dtype=float)
        if coef_arr.ndim == 1:
            coef_arr = coef_arr.reshape(1, -1)
        int_arr = np.asarray(intercept, dtype=float).reshape(-1)
        payload = {"targets": {}}
        for idx, target in enumerate(target_columns):
            payload["targets"][target] = {
                "intercept": float(int_arr[idx]),
                "coefficients": {feature: float(coef_arr[idx, i]) for i, feature in enumerate(feature_columns)},
            }
        path = output_dir / "coefficients.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path, None

    return None, None


def train_delta_model(
    *,
    delta_dataset: str | Path,
    feature_columns: list[str] | None = None,
    base_targets: list[str],
    feature_set_name: str | None = None,
    model_type: str = "extra_trees",
    split_method: SplitMethod = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
    model_params: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
    delta_prefix: str = "delta__",
    lf_prefix: str = "lf__",
    hf_prefix: str = "hf__",
) -> dict[str, Any]:
    if not base_targets:
        raise ValueError("base_targets must not be empty")
    if feature_columns and feature_set_name:
        raise ValueError("Use only one of feature_columns or feature_set_name for delta-model training.")
    if not feature_columns and not feature_set_name:
        raise ValueError("feature_columns or feature_set_name must be provided for delta-model training.")

    delta_csv, df_raw = _load_delta_dataset(delta_dataset)
    delta_columns, lf_columns, hf_columns = _target_columns(
        base_targets,
        delta_prefix=delta_prefix,
        lf_prefix=lf_prefix,
        hf_prefix=hf_prefix,
    )
    df_featured, resolved_feature_columns, feature_set_metadata, feature_engineering_manifest = _prepare_delta_feature_frame(
        df_raw,
        feature_columns=feature_columns,
        feature_set_name=feature_set_name,
        base_targets=base_targets,
        lf_prefix=lf_prefix,
    )
    required = list(resolved_feature_columns) + list(delta_columns) + list(lf_columns) + list(hf_columns)
    if split_method == "grouped":
        required.append(group_column)
    _require_columns(df_featured, required, label="Delta dataset")
    df = _validate_numeric_columns(df_featured, list(resolved_feature_columns) + list(delta_columns) + list(lf_columns) + list(hf_columns), label="Delta dataset")
    feature_columns = resolved_feature_columns

    split = split_dataset(
        df,
        method=split_method,
        group_column=group_column,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        random_seed=random_seed,
    )

    if output_dir is None:
        output_dir = Path("data") / "processed" / "ml_runs" / f"delta_{model_type}"
    run_dir = _ensure_dir(Path(output_dir).expanduser().resolve())
    models_dir = _ensure_dir(run_dir / "models")
    diagnostics_dir = _ensure_dir(run_dir / "diagnostics")

    X_train, y_train = _arrays(split.train_df, feature_columns=feature_columns, delta_columns=delta_columns)
    model_params_eff = dict(model_params or {})
    model = build_model(model_type=model_type, random_seed=random_seed, model_params=model_params_eff)
    model.fit(X_train, y_train)

    model_path = models_dir / "model.pkl"
    with model_path.open("wb") as f:
        pickle.dump(model, f)

    metrics = {
        "model": {
            "model_type": model_type,
            "model_params": model_params_eff,
            "task": "multifidelity_delta_learning",
        },
        "delta_target_columns": delta_columns,
        "base_targets": base_targets,
        "train": _evaluate_partition(model=model, df=split.train_df, feature_columns=feature_columns, base_targets=base_targets, delta_columns=delta_columns, lf_columns=lf_columns, hf_columns=hf_columns),
        "val": _evaluate_partition(model=model, df=split.val_df, feature_columns=feature_columns, base_targets=base_targets, delta_columns=delta_columns, lf_columns=lf_columns, hf_columns=hf_columns),
        "test": _evaluate_partition(model=model, df=split.test_df, feature_columns=feature_columns, base_targets=base_targets, delta_columns=delta_columns, lf_columns=lf_columns, hf_columns=hf_columns),
    }
    metrics_path = run_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    train_rows_path, val_rows_path, test_rows_path = _write_split_rows(split, run_dir)

    diagnostics: dict[str, Any] = {}
    corrected_paths: dict[str, str] = {}
    for name, part in [("train", split.train_df), ("val", split.val_df), ("test", split.test_df)]:
        X_part = part[feature_columns].to_numpy(dtype=float)
        y_part = part[delta_columns].to_numpy(dtype=float)
        pred_delta = np.asarray(model.predict(X_part), dtype=float)
        if pred_delta.ndim == 1:
            pred_delta = pred_delta.reshape(-1, 1)
        diagnostics[name] = write_regression_diagnostics(
            partition_name=f"{name}_delta",
            df=part,
            target_columns=delta_columns,
            y_true=y_part,
            y_pred=pred_delta,
            output_dir=diagnostics_dir,
        )
        corrected_path = _write_corrected_predictions(
            partition_name=name,
            model=model,
            df=part,
            feature_columns=feature_columns,
            base_targets=base_targets,
            delta_columns=delta_columns,
            lf_columns=lf_columns,
            hf_columns=hf_columns,
            output_dir=diagnostics_dir,
        )
        corrected_paths[name] = str(corrected_path)

    coefficients_path, feature_importances_path = _write_explainability(
        model=model,
        model_type=model_type,
        feature_columns=feature_columns,
        target_columns=delta_columns,
        output_dir=run_dir,
    )

    train_config = {
        "task": "multifidelity_delta_learning",
        "delta_dataset_csv": str(delta_csv),
        "feature_set_name": feature_set_name,
        "feature_set": feature_set_metadata,
        "feature_engineering_manifest": feature_engineering_manifest,
        "feature_columns": list(feature_columns),
        "final_features": list(feature_columns),
        "target_columns": delta_columns,
        "delta_feature_columns": list(feature_columns),
        "base_targets": list(base_targets),
        "delta_target_columns": delta_columns,
        "lf_target_columns": lf_columns,
        "hf_target_columns": hf_columns,
        "model_type": model_type,
        "model_params": model_params_eff,
        "split_method": split_method,
        "group_column": group_column,
        "train_fraction": train_fraction,
        "val_fraction": val_fraction,
        "test_fraction": test_fraction,
        "random_seed": random_seed,
        "prefixes": {"delta_prefix": delta_prefix, "lf_prefix": lf_prefix, "hf_prefix": hf_prefix},
    }
    train_config_path = run_dir / "delta_train_config.json"
    train_config_path.write_text(json.dumps(train_config, indent=2), encoding="utf-8")

    # Standard alias for operator tooling that already knows normal ML run folders.
    # The canonical delta-specific config remains delta_train_config.json.
    train_config_alias_path = run_dir / "train_config.json"
    train_config_alias_path.write_text(json.dumps(train_config, indent=2), encoding="utf-8")

    feature_engineering_manifest_path: Path | None = None
    if feature_engineering_manifest is not None:
        feature_engineering_manifest_path = run_dir / "feature_engineering_manifest.json"
        feature_engineering_manifest_path.write_text(
            json.dumps(feature_engineering_manifest, indent=2),
            encoding="utf-8",
        )

    manifest = {
        "schema_version": DELTA_MODEL_MANIFEST_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "run_dir": str(run_dir),
        "task": "multifidelity_delta_learning",
        "environment": build_environment_snapshot(),
        "delta_dataset": {
            "csv": str(delta_csv),
            "sha256": file_sha256(delta_csv),
        },
        "model": {
            "model_type": model_type,
            "model_params": model_params_eff,
            "model_path": str(model_path),
            "model_sha256": file_sha256(model_path),
        },
        "feature_set_name": feature_set_name,
        "feature_set": feature_set_metadata,
        "feature_engineering": feature_engineering_manifest,
        "features": list(feature_columns),
        "feature_columns": list(feature_columns),
        "final_features": list(feature_columns),
        "target_columns": delta_columns,
        "lf_target_columns": lf_columns,
        "hf_target_columns": hf_columns,
        "base_targets": list(base_targets),
        "delta_target_columns": delta_columns,
        "split": {
            "method": split.method,
            "random_seed": split.random_seed,
            "metadata": split.metadata,
        },
        "artifacts": {
            "metrics_json": str(metrics_path),
            "train_config_json": str(train_config_path),
            "standard_train_config_json": str(train_config_alias_path),
            "feature_engineering_manifest_json": None if feature_engineering_manifest_path is None else str(feature_engineering_manifest_path),
            "train_rows_csv": str(train_rows_path),
            "val_rows_csv": str(val_rows_path),
            "test_rows_csv": str(test_rows_path),
            "diagnostics_dir": str(diagnostics_dir),
            "corrected_prediction_csvs": corrected_paths,
            "feature_importances_json": None if feature_importances_path is None else str(feature_importances_path),
            "coefficients_json": None if coefficients_path is None else str(coefficients_path),
        },
    }
    manifest_path = write_ml_run_manifest(run_dir / "delta_model_manifest.json", manifest)

    artifacts = DeltaTrainArtifacts(
        run_dir=run_dir,
        models_dir=models_dir,
        model_path=model_path,
        metrics_path=metrics_path,
        train_config_path=train_config_path,
        manifest_path=manifest_path,
        train_rows_path=train_rows_path,
        val_rows_path=val_rows_path,
        test_rows_path=test_rows_path,
        diagnostics_dir=diagnostics_dir,
        feature_importances_path=feature_importances_path,
        coefficients_path=coefficients_path,
    )
    return {
        "model": model,
        "metrics": metrics,
        "split": split,
        "artifacts": artifacts,
        "manifest": manifest,
        "diagnostics": diagnostics,
    }


def _load_delta_train_config(model_run_dir: Path) -> dict[str, Any]:
    path = model_run_dir / "delta_train_config.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing delta_train_config.json in delta model run dir: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"delta_train_config.json must contain an object: {path}")
    return data


def _resolve_model_path(model_run_dir: Path) -> Path:
    candidates = [model_run_dir / "models" / "model.pkl", model_run_dir / "model.pkl"]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    raise FileNotFoundError(f"Could not find model.pkl under delta model run dir: {model_run_dir}")


def predict_with_delta_model(
    *,
    model_run_dir: str | Path,
    input_csv: str | Path,
    output_dir: str | Path | None = None,
    include_truth_if_available: bool = True,
    feature_set_name: str | None = None,
    allow_feature_set_mismatch: bool = False,
) -> dict[str, Any]:
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    input_csv = Path(input_csv).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Delta model run directory does not exist: {model_run_dir}")
    if not input_csv.exists() or not input_csv.is_file():
        raise FileNotFoundError(f"Input CSV does not exist: {input_csv}")

    cfg = _load_delta_train_config(model_run_dir)
    model_path = _resolve_model_path(model_run_dir)
    with model_path.open("rb") as f:
        model = pickle.load(f)

    feature_columns = list(cfg["feature_columns"])
    base_targets = list(cfg["base_targets"])
    delta_columns = list(cfg["delta_target_columns"])
    lf_columns = list(cfg["lf_target_columns"])
    hf_columns = list(cfg.get("hf_target_columns", [f"hf__{t}" for t in base_targets]))
    trained_feature_set_name = cfg.get("feature_set_name")
    requested_feature_set_name = None if feature_set_name is None else str(feature_set_name).strip() or None
    _check_delta_feature_set_mismatch(
        trained_feature_set_name=trained_feature_set_name,
        requested_feature_set_name=requested_feature_set_name,
        allow_feature_set_mismatch=allow_feature_set_mismatch,
    )

    df_raw = pd.read_csv(input_csv)
    feature_set_metadata: dict[str, Any] | None = None
    feature_engineering_manifest: dict[str, Any] | None = None
    feature_set_applied = requested_feature_set_name is not None
    if requested_feature_set_name:
        df_prepared, _resolved_from_feature_set, feature_set_metadata, feature_engineering_manifest = _prepare_delta_feature_frame(
            df_raw,
            feature_columns=None,
            feature_set_name=requested_feature_set_name,
            base_targets=base_targets,
            lf_prefix=cfg.get("prefixes", {}).get("lf_prefix", "lf__"),
        )
    else:
        df_prepared = df_raw.copy()

    _require_columns(df_prepared, list(feature_columns) + list(lf_columns), label="Delta prediction input")
    df = _validate_numeric_columns(df_prepared, list(feature_columns) + list(lf_columns), label="Delta prediction input")

    X = df[feature_columns].to_numpy(dtype=float)
    pred_delta = np.asarray(model.predict(X), dtype=float)
    if pred_delta.ndim == 1:
        pred_delta = pred_delta.reshape(-1, 1)

    out = df.copy()
    for idx, target in enumerate(base_targets):
        out[f"pred__{delta_columns[idx]}"] = pred_delta[:, idx]
        out[f"pred_corrected__{target}"] = out[lf_columns[idx]].astype(float) + pred_delta[:, idx]

    evaluation: dict[str, Any] | None = None
    truth_available = all(col in out.columns for col in hf_columns)
    if include_truth_if_available and truth_available:
        y_true_hf = out[hf_columns].to_numpy(dtype=float)
        y_pred_corrected = out[[f"pred_corrected__{t}" for t in base_targets]].to_numpy(dtype=float)
        evaluation = evaluate_regression_metrics(y_true_hf, y_pred_corrected, base_targets)
        for idx, target in enumerate(base_targets):
            out[f"error_corrected__{target}"] = out[f"pred_corrected__{target}"] - out[hf_columns[idx]].astype(float)

    if output_dir is None:
        output_dir = model_run_dir / "delta_inference" / input_csv.stem
    out_dir = _ensure_dir(Path(output_dir).expanduser().resolve())
    predictions_csv = out_dir / "delta_predictions.csv"
    summary_json = out_dir / "delta_prediction_summary.json"
    materialized_input_csv: Path | None = None
    feature_engineering_manifest_json: Path | None = None
    if feature_set_applied:
        materialized_input_csv = out_dir / "materialized_delta_inference_input.csv"
        df.to_csv(materialized_input_csv, index=False)
        feature_engineering_manifest_json = out_dir / "delta_inference_feature_engineering_manifest.json"
        feature_engineering_manifest_json.write_text(
            json.dumps(feature_engineering_manifest or {}, indent=2),
            encoding="utf-8",
        )
    out.to_csv(predictions_csv, index=False)

    summary = {
        "schema_version": DELTA_PREDICTION_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "model_path": str(model_path),
        "input_csv": str(input_csv),
        "predictions_csv": str(predictions_csv),
        "materialized_delta_inference_input_csv": None if materialized_input_csv is None else str(materialized_input_csv),
        "feature_engineering_manifest_json": None if feature_engineering_manifest_json is None else str(feature_engineering_manifest_json),
        "n_rows": int(len(out)),
        "trained_feature_set_name": trained_feature_set_name,
        "feature_set_name": requested_feature_set_name,
        "feature_set_applied": feature_set_applied,
        "feature_set": feature_set_metadata,
        "feature_engineering_manifest": feature_engineering_manifest,
        "feature_columns": feature_columns,
        "base_targets": base_targets,
        "delta_target_columns": delta_columns,
        "lf_target_columns": lf_columns,
        "truth_available": bool(truth_available),
        "evaluation": evaluation,
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    artifacts = DeltaPredictArtifacts(
        output_dir=out_dir,
        predictions_csv=predictions_csv,
        prediction_summary_json=summary_json,
    )
    return {"summary": summary, "artifacts": artifacts, "predictions_df": out}
