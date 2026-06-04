from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from aeris.ml.fingerprints import file_sha256
from aeris.ml.feature_set_inference import (
    prepare_dataframe_for_feature_set_inference,
    trained_feature_set_name_from_config,
)
from aeris.ml.manifest import utc_now_iso
from aeris.ml.model_promotion import require_promoted_model

ObjectiveMode = Literal["maximize", "minimize", "target"]

ACTIVE_LEARNING_REPORT_SCHEMA_VERSION = "aeris.active_learning_report.v1"


@dataclass(frozen=True)
class ActiveLearningArtifacts:
    output_dir: Path
    ranked_candidates_csv_path: Path
    report_path: Path


@dataclass(frozen=True)
class ActiveLearningResult:
    ranked_df: pd.DataFrame
    report: dict[str, Any]
    artifacts: ActiveLearningArtifacts


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


def _resolve_model_path(model_run_dir: Path) -> Path:
    candidates = [model_run_dir / "models" / "model.pkl", model_run_dir / "model.pkl"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find model.pkl under model run dir: {model_run_dir}")


def _load_model(model_path: Path) -> Any:
    with model_path.open("rb") as f:
        return pickle.load(f)


def _unwrap_pipeline(model: Any) -> Any:
    steps = getattr(model, "named_steps", None)
    if steps is not None:
        return steps.get("model", model)
    return model


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


def _load_reference_rows(model_run_dir: Path, reference_csv: Path | None) -> tuple[Path, pd.DataFrame]:
    path = reference_csv.expanduser().resolve() if reference_csv is not None else model_run_dir / "train_rows.csv"
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(
            f"Reference CSV not found: {path}. Provide --reference-csv or ensure train_rows.csv exists."
        )
    return path, pd.read_csv(path)


def _load_training_envelope(model_run_dir: Path) -> dict[str, Any] | None:
    path = model_run_dir / "training_envelope.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _feature_ranges_from_reference(reference_df: pd.DataFrame, feature_columns: list[str]) -> dict[str, dict[str, float | None]]:
    ranges: dict[str, dict[str, float | None]] = {}
    for col in feature_columns:
        numeric = pd.to_numeric(reference_df[col], errors="coerce")
        finite = numeric[np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))]
        if finite.empty:
            ranges[col] = {"min": None, "max": None}
        else:
            ranges[col] = {"min": float(finite.min()), "max": float(finite.max())}
    return ranges


def _resolve_feature_ranges(
    *,
    envelope: dict[str, Any] | None,
    reference_df: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, dict[str, float | None]]:
    if envelope is not None:
        raw = envelope.get("feature_ranges", {}) or {}
        ranges: dict[str, dict[str, float | None]] = {}
        for col in feature_columns:
            item = raw.get(col, {}) or {}
            ranges[col] = {"min": item.get("min"), "max": item.get("max")}
        return ranges
    return _feature_ranges_from_reference(reference_df, feature_columns)


def _range_arrays(feature_ranges: dict[str, dict[str, float | None]], feature_columns: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lows: list[float] = []
    highs: list[float] = []
    widths: list[float] = []
    for col in feature_columns:
        item = feature_ranges.get(col, {}) or {}
        lo_raw = item.get("min")
        hi_raw = item.get("max")
        if lo_raw is None or hi_raw is None:
            lo = 0.0
            hi = 1.0
        else:
            lo = float(lo_raw)
            hi = float(hi_raw)
        width = abs(hi - lo)
        if not np.isfinite(width) or width <= 0.0:
            width = 1.0
        lows.append(lo)
        highs.append(hi)
        widths.append(width)
    return np.asarray(lows, dtype=float), np.asarray(highs, dtype=float), np.asarray(widths, dtype=float)


def _normalize_values(values: np.ndarray, lows: np.ndarray, widths: np.ndarray) -> np.ndarray:
    return (values - lows.reshape(1, -1)) / widths.reshape(1, -1)


def _nearest_normalized_distance(
    *,
    candidate_values: np.ndarray,
    reference_values: np.ndarray,
    lows: np.ndarray,
    widths: np.ndarray,
    chunk_size: int = 2048,
) -> np.ndarray:
    if reference_values.shape[0] == 0:
        raise ValueError("Reference dataframe has zero rows; cannot compute novelty.")

    ref_norm = _normalize_values(reference_values, lows, widths)
    cand_norm = _normalize_values(candidate_values, lows, widths)
    out = np.empty(cand_norm.shape[0], dtype=float)

    for start in range(0, cand_norm.shape[0], chunk_size):
        chunk = cand_norm[start:start + chunk_size]
        diff = chunk[:, None, :] - ref_norm[None, :, :]
        dist2 = np.sum(diff * diff, axis=2)
        out[start:start + chunk.shape[0]] = np.sqrt(np.min(dist2, axis=1))
    return out


def _minmax_score(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    out = np.zeros_like(values, dtype=float)
    if not finite.any():
        return out
    v = values[finite]
    lo = float(np.min(v))
    hi = float(np.max(v))
    if np.isclose(hi, lo):
        return out
    out[finite] = (values[finite] - lo) / (hi - lo)
    return out


def _envelope_metrics(candidate_values: np.ndarray, lows: np.ndarray, highs: np.ndarray, widths: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lower_excess = np.maximum(lows.reshape(1, -1) - candidate_values, 0.0) / widths.reshape(1, -1)
    upper_excess = np.maximum(candidate_values - highs.reshape(1, -1), 0.0) / widths.reshape(1, -1)
    excess = lower_excess + upper_excess
    violation_count = np.sum(excess > 0.0, axis=1).astype(int)
    excess_sum = np.sum(excess, axis=1)
    excess_max = np.max(excess, axis=1)
    return violation_count, excess_sum, excess_max


def _predict(model: Any, X: np.ndarray, target_columns: list[str]) -> np.ndarray:
    pred = np.asarray(model.predict(X), dtype=float)
    if pred.ndim == 1:
        pred = pred.reshape(-1, 1)
    if pred.shape[1] != len(target_columns):
        raise ValueError(
            f"Model predicted {pred.shape[1]} target columns but train_config declares {len(target_columns)} targets."
        )
    return pred


def _uncertainty_from_native_ensemble(inner_model: Any, X: np.ndarray, target_columns: list[str]) -> tuple[np.ndarray, dict[str, Any]] | None:
    estimators = getattr(inner_model, "estimators_", None)
    if not estimators:
        return None

    try:
        preds = []
        for estimator in estimators:
            arr = np.asarray(estimator.predict(X), dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1)
            preds.append(arr)
        stacked = np.stack(preds, axis=0)
    except Exception:
        return None

    if stacked.ndim != 3 or stacked.shape[1] != X.shape[0]:
        return None
    if stacked.shape[2] != len(target_columns):
        return None

    return np.std(stacked, axis=0), {
        "method": "native_estimator_prediction_spread",
        "supported": True,
        "n_estimators": int(stacked.shape[0]),
        "note": "Uses prediction spread across native ensemble estimators. Useful as a heuristic, not calibrated uncertainty.",
    }


def _uncertainty_from_wrapped_ensemble(inner_model: Any, X: np.ndarray, target_columns: list[str]) -> tuple[np.ndarray, dict[str, Any]] | None:
    estimators = getattr(inner_model, "estimators_", None)
    if not estimators or len(estimators) != len(target_columns):
        return None

    cols: list[np.ndarray] = []
    supported_targets: list[str] = []
    for target, estimator in zip(target_columns, estimators):
        sub_estimators = getattr(estimator, "estimators_", None)
        if sub_estimators is None:
            cols.append(np.full(X.shape[0], np.nan, dtype=float))
            continue
        try:
            # sklearn GradientBoostingRegressor stores estimators_ as (n_estimators, 1).
            flat_estimators = np.asarray(sub_estimators, dtype=object).reshape(-1)
            preds = np.stack(
                [np.asarray(sub.predict(X), dtype=float).reshape(-1) for sub in flat_estimators],
                axis=0,
            )
            cols.append(np.std(preds, axis=0))
            supported_targets.append(target)
        except Exception:
            cols.append(np.full(X.shape[0], np.nan, dtype=float))

    if not supported_targets:
        return None

    return np.column_stack(cols), {
        "method": "wrapped_target_estimator_spread",
        "supported": True,
        "supported_targets": supported_targets,
        "unsupported_targets": [t for t in target_columns if t not in supported_targets],
        "note": "Uses per-target estimator spread where available. This is a heuristic, not calibrated uncertainty.",
    }


def _estimate_uncertainty(model: Any, X: np.ndarray, target_columns: list[str]) -> tuple[np.ndarray, dict[str, Any]]:
    inner = _unwrap_pipeline(model)

    native = _uncertainty_from_native_ensemble(inner, X, target_columns)
    if native is not None:
        return native

    wrapped = _uncertainty_from_wrapped_ensemble(inner, X, target_columns)
    if wrapped is not None:
        return wrapped

    return np.full((X.shape[0], len(target_columns)), np.nan, dtype=float), {
        "method": "unsupported",
        "supported": False,
        "note": "Model does not expose an estimator ensemble usable for prediction-spread scoring. Uncertainty contribution is set to zero.",
    }


def _objective_score(
    *,
    ranked_df: pd.DataFrame,
    objective_column: str | None,
    objective_mode: ObjectiveMode,
    objective_target_value: float | None,
) -> tuple[np.ndarray, dict[str, Any]]:
    if objective_column is None:
        return np.zeros(len(ranked_df), dtype=float), {"enabled": False}

    if objective_column not in ranked_df.columns:
        raise ValueError(
            f"objective_column '{objective_column}' is missing. Available columns: {list(ranked_df.columns)}"
        )
    values = pd.to_numeric(ranked_df[objective_column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)

    if objective_mode == "maximize":
        raw = values
    elif objective_mode == "minimize":
        raw = -values
    elif objective_mode == "target":
        if objective_target_value is None:
            raise ValueError("objective_mode='target' requires objective_target_value")
        raw = -np.abs(values - float(objective_target_value))
    else:
        raise ValueError(f"Unsupported objective_mode: {objective_mode}")

    return _minmax_score(raw), {
        "enabled": True,
        "objective_column": objective_column,
        "objective_mode": objective_mode,
        "objective_target_value": objective_target_value,
    }


def suggest_samples(
    *,
    model_run_dir: str | Path,
    candidate_csv: str | Path,
    output_dir: str | Path | None = None,
    reference_csv: str | Path | None = None,
    top_n: int = 25,
    candidate_id_column: str | None = None,
    require_promoted_model_gate: bool = True,
    objective_column: str | None = None,
    objective_mode: ObjectiveMode = "maximize",
    objective_target_value: float | None = None,
    uncertainty_weight: float = 1.0,
    novelty_weight: float = 0.5,
    objective_weight: float = 0.25,
    envelope_penalty_weight: float = 2.0,
    exclude_outside_envelope: bool = False,
    feature_set_name: str | None = None,
    allow_feature_set_mismatch: bool = False,
) -> ActiveLearningResult:
    """Rank candidate samples for the next simulation batch.

    This is the first active-learning foundation layer. It does not run solvers
    and it does not mutate datasets. It scores a candidate pool using the saved
    model, the model training envelope, and the existing training rows.
    """
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    candidate_csv = Path(candidate_csv).expanduser().resolve()
    reference_path_arg = Path(reference_csv).expanduser().resolve() if reference_csv is not None else None

    if top_n <= 0:
        raise ValueError(f"top_n must be positive. Got {top_n}.")
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    if not candidate_csv.exists() or not candidate_csv.is_file():
        raise FileNotFoundError(f"Candidate CSV does not exist: {candidate_csv}")

    promotion_manifest: dict[str, Any] | None = None
    if require_promoted_model_gate:
        promotion_manifest = require_promoted_model(model_run_dir)

    train_config = _load_json(model_run_dir / "train_config.json")
    model_path = _resolve_model_path(model_run_dir)
    model = _load_model(model_path)

    feature_columns = list(train_config.get("feature_columns", []))
    target_columns = list(train_config.get("target_columns", []))
    if not feature_columns:
        raise ValueError("train_config.json does not define feature_columns")
    if not target_columns:
        raise ValueError("train_config.json does not define target_columns")

    candidate_df_raw = pd.read_csv(candidate_csv)
    if candidate_df_raw.empty:
        raise ValueError(f"Candidate CSV is empty: {candidate_csv}")
    if candidate_id_column is not None and candidate_id_column not in candidate_df_raw.columns:
        raise ValueError(f"candidate_id_column '{candidate_id_column}' is missing from candidate CSV")

    reference_path, reference_df_raw = _load_reference_rows(model_run_dir, reference_path_arg)

    resolved_feature_set_name = feature_set_name or trained_feature_set_name_from_config(train_config)

    candidate_prepared = prepare_dataframe_for_feature_set_inference(
        candidate_df_raw,
        train_config=train_config,
        feature_set_name=resolved_feature_set_name,
        allow_feature_set_mismatch=allow_feature_set_mismatch,
    )
    reference_prepared = prepare_dataframe_for_feature_set_inference(
        reference_df_raw,
        train_config=train_config,
        feature_set_name=resolved_feature_set_name,
        allow_feature_set_mismatch=allow_feature_set_mismatch,
    )

    candidate_df_prepared = candidate_prepared.dataframe
    reference_df_prepared = reference_prepared.dataframe

    _require_columns(candidate_df_prepared, feature_columns, label="Candidate CSV")
    _require_columns(reference_df_prepared, feature_columns, label="Reference CSV")

    candidate_df = _numeric_frame(candidate_df_prepared, feature_columns, label="Candidate CSV")
    reference_df = _numeric_frame(reference_df_prepared, feature_columns, label="Reference CSV")

    X_candidate = candidate_df[feature_columns].to_numpy(dtype=float)
    X_reference = reference_df[feature_columns].to_numpy(dtype=float)

    envelope = _load_training_envelope(model_run_dir)
    feature_ranges = _resolve_feature_ranges(
        envelope=envelope,
        reference_df=reference_df,
        feature_columns=feature_columns,
    )
    lows, highs, widths = _range_arrays(feature_ranges, feature_columns)

    predictions = _predict(model, X_candidate, target_columns)
    uncertainty, uncertainty_report = _estimate_uncertainty(model, X_candidate, target_columns)
    uncertainty_finite = np.where(np.isfinite(uncertainty), uncertainty, 0.0)
    uncertainty_mean = np.mean(uncertainty_finite, axis=1)

    nearest_distance = _nearest_normalized_distance(
        candidate_values=X_candidate,
        reference_values=X_reference,
        lows=lows,
        widths=widths,
    )
    novelty_score = _minmax_score(nearest_distance)

    envelope_violation_count, envelope_excess_sum, envelope_excess_max = _envelope_metrics(X_candidate, lows, highs, widths)
    envelope_penalty_score = _minmax_score(envelope_excess_sum)

    ranked_df = candidate_df_prepared.copy()
    if candidate_id_column is None:
        ranked_df.insert(0, "candidate_id", [f"cand_{i:05d}" for i in range(len(ranked_df))])
        resolved_candidate_id_column = "candidate_id"
    else:
        resolved_candidate_id_column = candidate_id_column

    for idx, target in enumerate(target_columns):
        ranked_df[f"pred__{target}"] = predictions[:, idx]
        ranked_df[f"uncertainty__{target}"] = uncertainty[:, idx]

    ranked_df["uncertainty_mean"] = uncertainty_mean
    ranked_df["uncertainty_score"] = _minmax_score(uncertainty_mean)
    ranked_df["nearest_training_distance_normalized"] = nearest_distance
    ranked_df["novelty_score"] = novelty_score
    ranked_df["envelope_violation_count"] = envelope_violation_count
    ranked_df["envelope_excess_sum"] = envelope_excess_sum
    ranked_df["envelope_excess_max"] = envelope_excess_max
    ranked_df["envelope_status"] = np.where(envelope_violation_count > 0, "outside", "inside")

    objective_score, objective_report = _objective_score(
        ranked_df=ranked_df,
        objective_column=objective_column,
        objective_mode=objective_mode,
        objective_target_value=objective_target_value,
    )
    ranked_df["objective_score"] = objective_score

    score = (
        float(uncertainty_weight) * ranked_df["uncertainty_score"].to_numpy(dtype=float)
        + float(novelty_weight) * ranked_df["novelty_score"].to_numpy(dtype=float)
        + float(objective_weight) * ranked_df["objective_score"].to_numpy(dtype=float)
        - float(envelope_penalty_weight) * envelope_penalty_score
    )
    if exclude_outside_envelope:
        score = np.where(envelope_violation_count > 0, -np.inf, score)
    ranked_df["active_learning_score"] = score

    ranked_df = ranked_df.sort_values(
        by=["active_learning_score", "novelty_score", "uncertainty_score"],
        ascending=[False, False, False],
        kind="mergesort",
    ).reset_index(drop=True)
    ranked_df["active_learning_rank"] = np.arange(1, len(ranked_df) + 1)
    ranked_df["recommended"] = ranked_df["active_learning_rank"] <= int(top_n)

    if output_dir is None:
        output_dir_resolved = model_run_dir / "active_learning" / candidate_csv.stem
    else:
        output_dir_resolved = Path(output_dir).expanduser().resolve()
    output_dir_resolved = _ensure_dir(output_dir_resolved)

    materialized_candidate_csv_path: Path | None = None
    materialized_reference_csv_path: Path | None = None
    feature_engineering_manifest_path: Path | None = None

    if candidate_prepared.feature_set_applied:
        materialized_candidate_csv_path = output_dir_resolved / "materialized_candidate_pool.csv"
        materialized_reference_csv_path = output_dir_resolved / "materialized_reference_rows.csv"
        feature_engineering_manifest_path = output_dir_resolved / "active_learning_feature_engineering_manifest.json"

        candidate_df_prepared.to_csv(materialized_candidate_csv_path, index=False)
        reference_df_prepared.to_csv(materialized_reference_csv_path, index=False)
        feature_engineering_manifest_path.write_text(
            json.dumps(
                {
                    "candidate": candidate_prepared.to_summary(),
                    "reference": reference_prepared.to_summary(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    ranked_path = output_dir_resolved / "ranked_candidate_samples.csv"
    report_path = output_dir_resolved / "active_learning_report.json"
    ranked_df.to_csv(ranked_path, index=False)

    n_outside = int((ranked_df["envelope_status"] == "outside").sum())
    n_recommended = int(ranked_df["recommended"].sum())
    report: dict[str, Any] = {
        "schema_version": ACTIVE_LEARNING_REPORT_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "status": "success",
        "purpose": "rank candidate samples for next simulation; no solver execution performed",
        "model_run_dir": str(model_run_dir),
        "model_path": str(model_path),
        "candidate_csv": str(candidate_csv),
        "reference_csv": str(reference_path),
        "output_dir": str(output_dir_resolved),
        "ranked_candidates_csv": str(ranked_path),
        "require_promoted_model_gate": bool(require_promoted_model_gate),
        "promotion_manifest_status": None if promotion_manifest is None else promotion_manifest.get("status"),
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "candidate_id_column": resolved_candidate_id_column,
        "feature_set_name": candidate_prepared.requested_feature_set_name,
        "trained_feature_set_name": candidate_prepared.trained_feature_set_name,
        "feature_set_applied": candidate_prepared.feature_set_applied,
        "allow_feature_set_mismatch": bool(allow_feature_set_mismatch),
        "feature_engineering": {
            "candidate": candidate_prepared.to_summary(),
            "reference": reference_prepared.to_summary(),
        },
        "n_candidates": int(len(ranked_df)),
        "top_n_requested": int(top_n),
        "n_recommended": n_recommended,
        "n_outside_envelope": n_outside,
        "exclude_outside_envelope": bool(exclude_outside_envelope),
        "weights": {
            "uncertainty_weight": float(uncertainty_weight),
            "novelty_weight": float(novelty_weight),
            "objective_weight": float(objective_weight),
            "envelope_penalty_weight": float(envelope_penalty_weight),
        },
        "objective": objective_report,
        "uncertainty": uncertainty_report,
        "envelope_source": "training_envelope.json" if envelope is not None else "reference_csv_ranges",
        "artifacts": {
            "ranked_candidates_csv": str(ranked_path),
            "report_json": str(report_path),
            "materialized_candidate_pool_csv": None if materialized_candidate_csv_path is None else str(materialized_candidate_csv_path),
            "materialized_reference_rows_csv": None if materialized_reference_csv_path is None else str(materialized_reference_csv_path),
            "feature_engineering_manifest_json": None if feature_engineering_manifest_path is None else str(feature_engineering_manifest_path),
            "candidate_csv_sha256": file_sha256(candidate_csv),
            "reference_csv_sha256": file_sha256(reference_path),
            "materialized_candidate_pool_sha256": None if materialized_candidate_csv_path is None else file_sha256(materialized_candidate_csv_path),
            "materialized_reference_rows_sha256": None if materialized_reference_csv_path is None else file_sha256(materialized_reference_csv_path),
            "model_sha256": file_sha256(model_path),
        },
        "top_recommendations": ranked_df.head(int(top_n))[
            [resolved_candidate_id_column, "active_learning_rank", "active_learning_score", "envelope_status"]
        ].to_dict(orient="records"),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    artifacts = ActiveLearningArtifacts(
        output_dir=output_dir_resolved,
        ranked_candidates_csv_path=ranked_path,
        report_path=report_path,
    )
    return ActiveLearningResult(ranked_df=ranked_df, report=report, artifacts=artifacts)

