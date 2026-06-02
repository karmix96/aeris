from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.feature_set_inference import prepare_dataframe_for_feature_set_inference
from aeris.ml.manifest import utc_now_iso
from aeris.ml.model_promotion import require_promoted_model

INFERENCE_GUARD_SCHEMA_VERSION = "aeris.inference_guard_report.v1"


@dataclass(frozen=True)
class InferenceGuardResult:
    model_run_dir: Path
    input_csv: Path
    passed: bool
    report_path: Path
    errors: list[str]
    warnings: list[str]
    report: dict[str, Any]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_output_dir(model_run_dir: Path, input_csv: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return _ensure_output_dir(output_dir)
    return _ensure_output_dir(model_run_dir / "inference" / input_csv.stem)


def check_inference_inputs(
    *,
    model_run_dir: str | Path,
    input_csv: str | Path,
    output_dir: str | Path | None = None,
    require_promoted_model_gate: bool = True,
    fail_on_violations: bool = False,
    tolerance: float = 0.0,
    feature_set_name: str | None = None,
    allow_feature_set_mismatch: bool = False,
) -> InferenceGuardResult:
    """Validate whether an inference CSV stays within the promoted model training envelope.

    If ``feature_set_name`` is provided, declared transforms are applied before
    checking required feature columns and training-envelope ranges.
    """
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    input_csv = Path(input_csv).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    if not input_csv.exists() or not input_csv.is_file():
        raise FileNotFoundError(f"Input CSV does not exist: {input_csv}")

    if require_promoted_model_gate:
        require_promoted_model(model_run_dir)

    train_config = _load_json(model_run_dir / "train_config.json")
    envelope = _load_json(model_run_dir / "training_envelope.json")

    feature_columns = list(train_config.get("feature_columns", []))
    feature_ranges = envelope.get("feature_ranges", {}) or {}

    raw_df = pd.read_csv(input_csv)
    prepared = prepare_dataframe_for_feature_set_inference(
        raw_df,
        train_config=train_config,
        feature_set_name=feature_set_name,
        allow_feature_set_mismatch=allow_feature_set_mismatch,
    )
    df = prepared.dataframe

    errors: list[str] = []
    warnings: list[str] = []
    feature_reports: dict[str, Any] = {}

    missing_features = [c for c in feature_columns if c not in df.columns]
    if missing_features:
        errors.append(f"input CSV is missing required feature columns: {missing_features}")

    for col in feature_columns:
        if col not in df.columns:
            continue

        numeric = pd.to_numeric(df[col], errors="coerce")
        finite_mask = np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))
        finite_mask_series = pd.Series(finite_mask, index=df.index)
        n_non_numeric = int(numeric.isna().sum() - df[col].isna().sum())
        n_non_finite = int((~numeric.isna() & ~finite_mask_series).sum())
        finite = numeric[finite_mask_series]

        report = {
            "present": True,
            "n_rows": int(len(df)),
            "n_non_numeric": max(n_non_numeric, 0),
            "n_non_finite": max(n_non_finite, 0),
            "observed_min": None,
            "observed_max": None,
            "train_min": None,
            "train_max": None,
            "within_envelope": None,
        }

        if n_non_numeric > 0:
            errors.append(f"feature column '{col}' contains non-numeric values ({n_non_numeric} rows)")
        if n_non_finite > 0:
            errors.append(f"feature column '{col}' contains non-finite numeric values ({n_non_finite} rows)")
        if finite.empty:
            errors.append(f"feature column '{col}' has no finite numeric values")
            feature_reports[col] = report
            continue

        observed_min = float(finite.min())
        observed_max = float(finite.max())
        report["observed_min"] = observed_min
        report["observed_max"] = observed_max

        env = feature_ranges.get(col, {}) or {}
        train_min = env.get("min")
        train_max = env.get("max")
        report["train_min"] = train_min
        report["train_max"] = train_max

        if train_min is None or train_max is None:
            warnings.append(f"training envelope is missing range information for feature '{col}'")
            report["within_envelope"] = None
        else:
            lower = float(train_min) - float(tolerance)
            upper = float(train_max) + float(tolerance)
            in_range = observed_min >= lower and observed_max <= upper
            report["within_envelope"] = bool(in_range)
            if not in_range:
                errors.append(
                    f"feature '{col}' is outside training envelope: observed range [{observed_min}, {observed_max}] vs train range [{train_min}, {train_max}] with tolerance {tolerance}"
                )

        feature_reports[col] = report

    passed = len(errors) == 0
    feature_summary = prepared.to_summary()
    report = {
        "schema_version": INFERENCE_GUARD_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "input_csv": str(input_csv),
        "passed": passed,
        "fail_on_violations": bool(fail_on_violations),
        "require_promoted_model_gate": bool(require_promoted_model_gate),
        "tolerance": float(tolerance),
        "feature_columns": feature_columns,
        "n_rows": int(len(df)),
        "errors": errors,
        "warnings": warnings,
        "feature_reports": feature_reports,
        **feature_summary,
    }

    out_dir = _resolve_output_dir(
        model_run_dir,
        input_csv,
        Path(output_dir).expanduser().resolve() if output_dir is not None else None,
    )
    if prepared.feature_set_applied:
        materialized_path = out_dir / "materialized_inference_input.csv"
        fe_manifest_path = out_dir / "inference_feature_engineering_manifest.json"
        df.to_csv(materialized_path, index=False)
        fe_manifest_path.write_text(
            json.dumps(prepared.transform_manifest or {}, indent=2),
            encoding="utf-8",
        )
        report["materialized_input_csv_path"] = str(materialized_path)
        report["feature_engineering_manifest_path"] = str(fe_manifest_path)

    report_path = out_dir / "inference_guard_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    result = InferenceGuardResult(
        model_run_dir=model_run_dir,
        input_csv=input_csv,
        passed=passed,
        report_path=report_path,
        errors=errors,
        warnings=warnings,
        report=report,
    )
    if fail_on_violations and not passed:
        raise ValueError("Inference guard failed; see inference_guard_report.json for details")
    return result
