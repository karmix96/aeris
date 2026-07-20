from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso
from aeris.ml.metrics import evaluate_regression_metrics
from aeris.ml.model_promotion import require_promoted_model

PREDICTION_CONFIDENCE_SCHEMA_VERSION = "aeris.prediction_confidence_report.v1"

# ML-H3: estimator-spread is a valid epistemic-uncertainty heuristic ONLY for
# bagging-style ensembles whose members each predict the full target vector.
# MultiOutputRegressor exposes per-target sub-models through estimators_
# (NOT ensemble members: a single-target wrapper yields spread == 0), and
# boosting stage trees are residual increments (their spread reflects the
# learning trajectory, not predictive uncertainty). Anything outside this
# whitelist reports supported=False and honest NaN uncertainty.
_AERIS_BAGGING_ENSEMBLE_TYPES = {
    "RandomForestRegressor",
    "ExtraTreesRegressor",
    "NeuralMLPEnsembleRegressor",
}


@dataclass(frozen=True)
class PredictionConfidenceArtifacts:
    output_dir: Path
    prediction_confidence_csv_path: Path
    report_path: Path


@dataclass(frozen=True)
class PredictionConfidenceResult:
    output_df: pd.DataFrame
    report: dict[str, Any]
    artifacts: PredictionConfidenceArtifacts


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
            raise ValueError(
                f"{label} column '{col}' contains {int(bad.sum())} non-finite/non-numeric values"
            )
        out[col] = numeric.astype(float)
    return out


def _load_training_envelope(model_run_dir: Path) -> dict[str, Any] | None:
    path = model_run_dir / "training_envelope.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _feature_ranges_from_rows(rows_csv: Path, feature_columns: list[str]) -> dict[str, dict[str, float | None]]:
    if not rows_csv.exists():
        return {col: {"min": None, "max": None} for col in feature_columns}
    df = pd.read_csv(rows_csv)
    _require_columns(df, feature_columns, label=str(rows_csv))
    ranges: dict[str, dict[str, float | None]] = {}
    for col in feature_columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        finite = numeric[np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))]
        if finite.empty:
            ranges[col] = {"min": None, "max": None}
        else:
            ranges[col] = {"min": float(finite.min()), "max": float(finite.max())}
    return ranges


def _resolve_feature_ranges(model_run_dir: Path, feature_columns: list[str]) -> tuple[dict[str, dict[str, float | None]], str]:
    envelope = _load_training_envelope(model_run_dir)
    if envelope is not None:
        raw = envelope.get("feature_ranges", {}) or {}
        ranges: dict[str, dict[str, float | None]] = {}
        for col in feature_columns:
            item = raw.get(col, {}) or {}
            ranges[col] = {"min": item.get("min"), "max": item.get("max")}
        return ranges, "training_envelope.json"
    return _feature_ranges_from_rows(model_run_dir / "train_rows.csv", feature_columns), "train_rows.csv"


def _range_arrays(feature_ranges: dict[str, dict[str, float | None]], feature_columns: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], np.ndarray]:
    # ML-H2: features WITHOUT a recorded training range must be excluded from
    # envelope arithmetic entirely (valid_mask False), never scored against a
    # fabricated [0, 1] placeholder range. The placeholder lo/hi/width values
    # below only keep array shapes aligned; the mask guarantees they can never
    # contribute to a violation. Mirrors aeris.ml.envelope_metrics.
    lows: list[float] = []
    highs: list[float] = []
    widths: list[float] = []
    missing: list[str] = []
    valid: list[bool] = []
    for col in feature_columns:
        item = feature_ranges.get(col, {}) or {}
        lo_raw = item.get("min")
        hi_raw = item.get("max")
        if lo_raw is None or hi_raw is None:
            lo = 0.0
            hi = 1.0
            missing.append(col)
            valid.append(False)
        else:
            lo = float(lo_raw)
            hi = float(hi_raw)
            valid.append(True)
        width = abs(hi - lo)
        if not np.isfinite(width) or width <= 0.0:
            width = 1.0
        lows.append(lo)
        highs.append(hi)
        widths.append(width)
    return (
        np.asarray(lows, dtype=float),
        np.asarray(highs, dtype=float),
        np.asarray(widths, dtype=float),
        missing,
        np.asarray(valid, dtype=bool),
    )


def _envelope_metrics(candidate_values: np.ndarray, lows: np.ndarray, highs: np.ndarray, widths: np.ndarray, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lower_excess = np.maximum(lows.reshape(1, -1) - candidate_values, 0.0) / widths.reshape(1, -1)
    upper_excess = np.maximum(candidate_values - highs.reshape(1, -1), 0.0) / widths.reshape(1, -1)
    excess = lower_excess + upper_excess
    # ML-H2: zero out columns with no recorded training range so they can
    # never be counted as envelope violations.
    if excess.size:
        excess[:, ~np.asarray(valid_mask, dtype=bool)] = 0.0
    violation_count = np.sum(excess > 0.0, axis=1).astype(int)
    excess_sum = np.sum(excess, axis=1)
    excess_max = np.max(excess, axis=1) if excess.size else np.zeros(candidate_values.shape[0])
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
    # ML-H3: only genuine bagging ensembles qualify; a MultiOutputRegressor
    # also exposes estimators_ but those are per-target sub-models.
    if type(inner_model).__name__ not in _AERIS_BAGGING_ENSEMBLE_TYPES:
        return None
    if len(estimators) < 2:
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
    if stacked.ndim != 3 or stacked.shape[1] != X.shape[0] or stacked.shape[2] != len(target_columns):
        return None
    return np.std(stacked, axis=0), {
        "method": "native_estimator_prediction_spread",
        "supported": True,
        "n_estimators": int(stacked.shape[0]),
        "note": "Heuristic estimator-spread uncertainty; not calibrated probability.",
    }


def _uncertainty_from_wrapped_ensemble(inner_model: Any, X: np.ndarray, target_columns: list[str]) -> tuple[np.ndarray, dict[str, Any]] | None:
    estimators = getattr(inner_model, "estimators_", None)
    if not estimators or len(estimators) != len(target_columns):
        return None
    cols: list[np.ndarray] = []
    supported_targets: list[str] = []
    for target, estimator in zip(target_columns, estimators):
        sub_estimators = getattr(estimator, "estimators_", None)
        # ML-H3: per-target spread is meaningful only when the per-target
        # model is itself a bagging ensemble with >= 2 members. Boosting
        # stage trees (e.g. GradientBoostingRegressor.estimators_) are
        # residual increments and must not be treated as members.
        if (
            type(estimator).__name__ not in _AERIS_BAGGING_ENSEMBLE_TYPES
            or sub_estimators is None
            or len(sub_estimators) < 2
        ):
            cols.append(np.full(X.shape[0], np.nan, dtype=float))
            continue
        try:
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
        "note": "Heuristic per-target estimator-spread uncertainty; not calibrated probability.",
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
        "note": "Model does not expose estimator ensembles. Uncertainty columns are NaN and confidence cannot be calibrated.",
    }


def _safe_mean_uncertainty(uncertainty: np.ndarray) -> np.ndarray:
    finite = np.where(np.isfinite(uncertainty), uncertainty, np.nan)
    with np.errstate(all="ignore"):
        mean = np.nanmean(finite, axis=1)
    return np.where(np.isfinite(mean), mean, np.nan)


def _confidence_status(*, uncertainty_mean: np.ndarray, envelope_violation_count: np.ndarray, uncertainty_supported: bool) -> list[str]:
    if not uncertainty_supported:
        return ["outside_envelope" if int(v) > 0 else "unknown_uncertainty" for v in envelope_violation_count]
    finite = uncertainty_mean[np.isfinite(uncertainty_mean)]
    if finite.size == 0:
        return ["outside_envelope" if int(v) > 0 else "unknown_uncertainty" for v in envelope_violation_count]
    p50 = float(np.percentile(finite, 50))
    p90 = float(np.percentile(finite, 90))
    statuses: list[str] = []
    for unc, violations in zip(uncertainty_mean, envelope_violation_count):
        if int(violations) > 0:
            statuses.append("outside_envelope")
        elif not np.isfinite(unc):
            statuses.append("unknown_uncertainty")
        elif float(unc) <= p50:
            statuses.append("high_confidence")
        elif float(unc) <= p90:
            statuses.append("medium_confidence")
        else:
            statuses.append("low_confidence")
    return statuses


def _to_jsonable_metrics(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if metrics is None:
        return None
    # json.dumps allows NaN by default, but explicit conversion keeps reports cleaner.
    text = json.dumps(metrics, allow_nan=True)
    return json.loads(text)


def predict_with_confidence(
    *,
    model_run_dir: str | Path,
    input_csv: str | Path,
    output_dir: str | Path | None = None,
    require_promoted_model_gate: bool = True,
    include_truth_if_available: bool = True,
    uq_method: str = "heuristic",
    feature_set_name: str | None = None,
    allow_feature_set_mismatch: bool = False,
) -> PredictionConfidenceResult:
    """Predict with a saved AERIS model and attach engineering-quality confidence diagnostics.

    This function intentionally produces heuristic confidence information, not certified
    probability intervals. It combines estimator-spread uncertainty where available with
    training-envelope checks so downstream active learning and optimization can avoid
    blind trust in extrapolated predictions.
    """
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    input_csv = Path(input_csv).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    if not input_csv.exists() or not input_csv.is_file():
        raise FileNotFoundError(f"Input CSV does not exist: {input_csv}")

    promotion_manifest: dict[str, Any] | None = None
    if require_promoted_model_gate:
        promotion_manifest = require_promoted_model(model_run_dir)

    train_config = _load_json(model_run_dir / "train_config.json")
    feature_columns = list(train_config.get("feature_columns", []))
    target_columns = list(train_config.get("target_columns", []))
    if not feature_columns:
        raise ValueError("train_config.json does not define feature_columns")
    if not target_columns:
        raise ValueError("train_config.json does not define target_columns")

    model_path = _resolve_model_path(model_run_dir)
    model = _load_model(model_path)

    input_df_raw = pd.read_csv(input_csv)
    if input_df_raw.empty:
        raise ValueError(f"Input CSV is empty: {input_csv}")
    # ML-BUG-04 / ML-REF-03: shared feature-set materialization path.
    from aeris.ml.feature_set_inference import (
        prepare_dataframe_for_feature_set_inference,
    )
    _prepared = prepare_dataframe_for_feature_set_inference(
        input_df_raw,
        train_config=train_config,
        feature_set_name=feature_set_name,
        allow_feature_set_mismatch=allow_feature_set_mismatch,
    )
    _feature_set_summary = _prepared.to_summary()
    input_df_prepared = _prepared.dataframe
    _require_columns(input_df_prepared, feature_columns, label="Input CSV")
    input_df = _numeric_frame(input_df_prepared, feature_columns, label="Input CSV")
    X = input_df[feature_columns].to_numpy(dtype=float)

    if uq_method not in {"heuristic", "conformal"}:
        raise ValueError(
            "Unsupported uq_method '" + str(uq_method) + "'. Use 'heuristic' or 'conformal'."
        )

    predictions = _predict(model, X, target_columns)
    conformal_lower: np.ndarray | None = None
    conformal_upper: np.ndarray | None = None

    if uq_method == "conformal":
        # ML-C2 / CONF.1: calibrated split-conformal intervals.
        from aeris.ml.conformal import load_conformal_calibration

        calibration_path = model_run_dir / "conformal_calibration.json"
        calibration = load_conformal_calibration(calibration_path)
        if list(calibration.target_columns) != list(target_columns):
            raise ValueError(
                "Conformal calibration target mismatch. Model targets: "
                + str(list(target_columns))
                + ", calibration targets: "
                + str(list(calibration.target_columns))
                + ". Re-run: aeris ml calibrate-conformal --model-run-dir ..."
            )
        current_model_sha = file_sha256(model_path)
        if (
            calibration.model_sha256 is not None
            and calibration.model_sha256 != current_model_sha
        ):
            raise ValueError(
                "Conformal calibration was fitted on a DIFFERENT model artifact "
                "(model.pkl sha256 mismatch). The coverage guarantee does not "
                "transfer. Re-run: aeris ml calibrate-conformal --model-run-dir ..."
            )
        q_arr = np.array(
            [float(calibration.q_hat[t]) for t in target_columns], dtype=float
        )
        uncertainty = np.tile(q_arr.reshape(1, -1), (X.shape[0], 1))
        conformal_lower = predictions - q_arr.reshape(1, -1)
        conformal_upper = predictions + q_arr.reshape(1, -1)
        uncertainty_report = {
            "method": "split_conformal_v1",
            "supported": True,
            "alpha": float(calibration.alpha),
            "coverage_theoretical": float(calibration.coverage_theoretical),
            "n_calibration": int(calibration.n_calibration),
            "q_hat": {k: float(v) for k, v in calibration.q_hat.items()},
            "calibration_path": str(calibration_path),
            "calibration_model_sha256": calibration.model_sha256,
            "note": (
                "Symmetric split-conformal intervals: per-target marginal "
                "coverage >= 1 - alpha under exchangeability of calibration "
                "and test rows. Interval half-width per target = q_hat."
            ),
        }
    else:
        uncertainty, uncertainty_report = _estimate_uncertainty(model, X, target_columns)

    uncertainty_mean = _safe_mean_uncertainty(uncertainty)

    feature_ranges, envelope_source = _resolve_feature_ranges(model_run_dir, feature_columns)
    lows, highs, widths, missing_envelope_features, envelope_valid_mask = _range_arrays(feature_ranges, feature_columns)
    envelope_violation_count, envelope_excess_sum, envelope_excess_max = _envelope_metrics(X, lows, highs, widths, envelope_valid_mask)

    output_df = input_df_raw.copy()
    for idx, target in enumerate(target_columns):
        output_df[f"pred__{target}"] = predictions[:, idx]
        output_df[f"uncertainty__{target}"] = uncertainty[:, idx]
    if conformal_lower is not None and conformal_upper is not None:
        for idx, target in enumerate(target_columns):
            output_df[f"lower__{target}"] = conformal_lower[:, idx]
            output_df[f"upper__{target}"] = conformal_upper[:, idx]
    output_df["uncertainty_mean"] = uncertainty_mean
    output_df["envelope_violation_count"] = envelope_violation_count
    output_df["envelope_excess_sum"] = envelope_excess_sum
    output_df["envelope_excess_max"] = envelope_excess_max
    output_df["envelope_status"] = np.where(envelope_violation_count > 0, "outside", "inside")
    if uq_method == "conformal":
        # Calibrated intervals carry their own guarantee; the only remaining
        # per-row qualifier is the training envelope. Batch-relative
        # percentile labels would be meaningless on constant q_hat widths.
        output_df["confidence_status"] = np.where(
            envelope_violation_count > 0, "outside_envelope", "calibrated"
        )
    else:
        output_df["confidence_status"] = _confidence_status(
            uncertainty_mean=uncertainty_mean,
            envelope_violation_count=envelope_violation_count,
            uncertainty_supported=bool(uncertainty_report.get("supported")),
        )

    evaluation: dict[str, Any] | None = None
    truth_available = all(col in input_df_raw.columns for col in target_columns)
    if include_truth_if_available and truth_available:
        y_true = input_df_raw[target_columns].to_numpy(dtype=float)
        evaluation = evaluate_regression_metrics(y_true, predictions, target_columns)
        for idx, target in enumerate(target_columns):
            output_df[f"error__{target}"] = predictions[:, idx] - y_true[:, idx]
            output_df[f"abs_error__{target}"] = np.abs(predictions[:, idx] - y_true[:, idx])

    if output_dir is None:
        output_dir_resolved = model_run_dir / "quality" / f"confidence__{input_csv.stem}"
    else:
        output_dir_resolved = Path(output_dir).expanduser().resolve()
    output_dir_resolved = _ensure_dir(output_dir_resolved)

    prediction_confidence_csv_path = output_dir_resolved / "prediction_confidence.csv"
    report_path = output_dir_resolved / "prediction_confidence_report.json"
    output_df.to_csv(prediction_confidence_csv_path, index=False)

    status_counts = output_df["confidence_status"].value_counts(dropna=False).to_dict()
    envelope_counts = output_df["envelope_status"].value_counts(dropna=False).to_dict()
    report: dict[str, Any] = {
        "schema_version": PREDICTION_CONFIDENCE_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "status": "success",
        "purpose": "prediction with confidence diagnostics; no solver execution performed",
        "model_run_dir": str(model_run_dir),
        "model_path": str(model_path),
        "input_csv": str(input_csv),
        "output_dir": str(output_dir_resolved),
        "prediction_confidence_csv": str(prediction_confidence_csv_path),
        "require_promoted_model_gate": bool(require_promoted_model_gate),
        "promotion_manifest_status": None if promotion_manifest is None else promotion_manifest.get("status"),
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "n_rows": int(len(output_df)),
        "truth_available": bool(truth_available),
        "uq_method": uq_method,
        "feature_set_name": _feature_set_summary.get("feature_set_name"),
        "trained_feature_set_name": _feature_set_summary.get("trained_feature_set_name"),
        "feature_set_applied": _feature_set_summary.get("feature_set_applied"),
        "feature_engineering_manifest": _feature_set_summary.get("feature_engineering_manifest"),
        "evaluation": _to_jsonable_metrics(evaluation),
        "uncertainty": uncertainty_report,
        "envelope_source": envelope_source,
        "missing_envelope_features": missing_envelope_features,
        "n_outside_envelope": int((output_df["envelope_status"] == "outside").sum()),
        "confidence_status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "envelope_status_counts": {str(k): int(v) for k, v in envelope_counts.items()},
        "artifacts": {
            "prediction_confidence_csv": str(prediction_confidence_csv_path),
            "report_json": str(report_path),
            "input_csv_sha256": file_sha256(input_csv),
            "model_sha256": file_sha256(model_path),
        },
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    artifacts = PredictionConfidenceArtifacts(
        output_dir=output_dir_resolved,
        prediction_confidence_csv_path=prediction_confidence_csv_path,
        report_path=report_path,
    )
    return PredictionConfidenceResult(output_df=output_df, report=report, artifacts=artifacts)
