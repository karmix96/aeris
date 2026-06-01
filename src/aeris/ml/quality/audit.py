from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso

MODEL_QUALITY_REPORT_SCHEMA_VERSION = "aeris.model_quality_report.v1"


@dataclass(frozen=True)
class ModelQualityArtifacts:
    output_dir: Path
    report_path: Path
    residual_audit_csv_path: Path


@dataclass(frozen=True)
class ModelQualityResult:
    passed: bool
    status: str
    report: dict[str, Any]
    artifacts: ModelQualityArtifacts


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing required JSON file: {path}")
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _partition_metric_summary(metrics: dict[str, Any], partition: str) -> dict[str, Any]:
    part = metrics.get(partition, {}) or {}
    overall = part.get("overall", {}) or {}
    per_target = part.get("per_target", {}) or {}
    error_p95_values = []
    max_abs_values = []
    bias_values = []
    for item in per_target.values():
        if isinstance(item, dict):
            if item.get("error_p95") is not None:
                error_p95_values.append(float(item["error_p95"]))
            if item.get("max_abs_error") is not None:
                max_abs_values.append(float(item["max_abs_error"]))
            if item.get("bias_mean") is not None:
                bias_values.append(abs(float(item["bias_mean"])))
    return {
        "overall": overall,
        "per_target": per_target,
        "derived": {
            "error_p95_mean": None if not error_p95_values else float(np.mean(error_p95_values)),
            "max_abs_error_mean": None if not max_abs_values else float(np.mean(max_abs_values)),
            "abs_bias_mean": None if not bias_values else float(np.mean(bias_values)),
        },
    }


def _collect_worst_residual_rows(
    *,
    diagnostics_dir: Path,
    target_columns: list[str],
    top_k_per_target: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    id_like_cols = [
        "geometry_id",
        "airfoil_id",
        "case_id",
        "alpha_deg",
        "beta_deg",
        "reynolds",
        "mach",
        "velocity_mps",
        "altitude_m",
        "control_input_deg",
        "solver_id",
        "fidelity_level",
    ]
    for partition in ["train", "val", "test"]:
        path = diagnostics_dir / f"{partition}_residuals.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        for target in target_columns:
            abs_col = f"abs_error__{target}"
            err_col = f"error__{target}"
            true_col = f"true__{target}"
            pred_col = f"pred__{target}"
            if abs_col not in df.columns:
                continue
            work = df.copy()
            work[abs_col] = pd.to_numeric(work[abs_col], errors="coerce")
            work = work[np.isfinite(work[abs_col].to_numpy(dtype=float, na_value=np.nan))]
            if work.empty:
                continue
            top = work.sort_values(abs_col, ascending=False).head(int(top_k_per_target))
            for row_index, row in top.iterrows():
                out: dict[str, Any] = {
                    "partition": partition,
                    "target": target,
                    "source_row_index": int(row_index),
                    "abs_error": float(row[abs_col]),
                    "error": None if err_col not in row or pd.isna(row.get(err_col)) else float(row[err_col]),
                    "true": None if true_col not in row or pd.isna(row.get(true_col)) else float(row[true_col]),
                    "pred": None if pred_col not in row or pd.isna(row.get(pred_col)) else float(row[pred_col]),
                }
                for col in id_like_cols:
                    if col in row.index:
                        value = row[col]
                        out[col] = None if pd.isna(value) else value
                rows.append(out)
    if not rows:
        return pd.DataFrame(columns=["partition", "target", "source_row_index", "abs_error", "error", "true", "pred"])
    return pd.DataFrame(rows).sort_values(["partition", "target", "abs_error"], ascending=[True, True, False])


def _quality_gates(
    *,
    metrics: dict[str, Any],
    max_test_rmse_mean: float | None,
    min_test_r2_mean: float | None,
    max_test_error_p95_mean: float | None,
    max_test_abs_bias_mean: float | None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    test_summary = _partition_metric_summary(metrics, "test")
    overall = test_summary.get("overall", {}) or {}
    derived = test_summary.get("derived", {}) or {}

    observed = {
        "test_rmse_mean": overall.get("rmse_mean"),
        "test_r2_mean": overall.get("r2_mean"),
        "test_error_p95_mean": derived.get("error_p95_mean"),
        "test_abs_bias_mean": derived.get("abs_bias_mean"),
    }
    thresholds = {
        "max_test_rmse_mean": max_test_rmse_mean,
        "min_test_r2_mean": min_test_r2_mean,
        "max_test_error_p95_mean": max_test_error_p95_mean,
        "max_test_abs_bias_mean": max_test_abs_bias_mean,
    }

    if max_test_rmse_mean is not None:
        value = observed["test_rmse_mean"]
        if value is None:
            errors.append("test rmse_mean is missing; cannot apply max_test_rmse_mean gate")
        elif float(value) > float(max_test_rmse_mean):
            errors.append(f"test rmse_mean {value} exceeds max_test_rmse_mean {max_test_rmse_mean}")
    if min_test_r2_mean is not None:
        value = observed["test_r2_mean"]
        if value is None:
            errors.append("test r2_mean is missing; cannot apply min_test_r2_mean gate")
        elif float(value) < float(min_test_r2_mean):
            errors.append(f"test r2_mean {value} is below min_test_r2_mean {min_test_r2_mean}")
    if max_test_error_p95_mean is not None:
        value = observed["test_error_p95_mean"]
        if value is None:
            errors.append("test error_p95_mean is missing; cannot apply max_test_error_p95_mean gate")
        elif float(value) > float(max_test_error_p95_mean):
            errors.append(f"test error_p95_mean {value} exceeds max_test_error_p95_mean {max_test_error_p95_mean}")
    if max_test_abs_bias_mean is not None:
        value = observed["test_abs_bias_mean"]
        if value is None:
            errors.append("test abs_bias_mean is missing; cannot apply max_test_abs_bias_mean gate")
        elif float(value) > float(max_test_abs_bias_mean):
            errors.append(f"test abs_bias_mean {value} exceeds max_test_abs_bias_mean {max_test_abs_bias_mean}")

    if not thresholds or all(v is None for v in thresholds.values()):
        warnings.append("no explicit model-quality thresholds were provided; report is informational")

    return errors, warnings, {"observed": observed, "thresholds": thresholds}


def audit_model(
    *,
    model_run_dir: str | Path,
    output_dir: str | Path | None = None,
    max_test_rmse_mean: float | None = None,
    min_test_r2_mean: float | None = None,
    max_test_error_p95_mean: float | None = None,
    max_test_abs_bias_mean: float | None = None,
    top_k_worst_rows_per_target: int = 20,
    fail_on_quality_gate: bool = False,
) -> ModelQualityResult:
    """Build a quality report for a saved AERIS ML model run.

    The audit consumes existing training artifacts. It does not retrain, mutate the
    model, or run solvers. It is deliberately report-first so model quality can be
    inspected before downstream optimization or active learning trusts the run.
    """
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")

    metrics_path = model_run_dir / "metrics.json"
    train_config_path = model_run_dir / "train_config.json"
    metrics = _load_json(metrics_path)
    train_config = _load_json(train_config_path)
    ml_manifest = _load_json(model_run_dir / "ml_run_manifest.json", required=False)
    promotion_manifest = _load_json(model_run_dir / "model_promotion_manifest.json", required=False)

    target_columns = list(train_config.get("target_columns", []))
    if not target_columns:
        raise ValueError("train_config.json does not define target_columns")

    if output_dir is None:
        output_dir_resolved = model_run_dir / "quality" / "model_audit"
    else:
        output_dir_resolved = Path(output_dir).expanduser().resolve()
    output_dir_resolved = _ensure_dir(output_dir_resolved)

    residual_audit_csv_path = output_dir_resolved / "residual_audit.csv"
    worst_df = _collect_worst_residual_rows(
        diagnostics_dir=model_run_dir / "diagnostics",
        target_columns=target_columns,
        top_k_per_target=top_k_worst_rows_per_target,
    )
    worst_df.to_csv(residual_audit_csv_path, index=False)

    errors, warnings, gate_report = _quality_gates(
        metrics=metrics,
        max_test_rmse_mean=max_test_rmse_mean,
        min_test_r2_mean=min_test_r2_mean,
        max_test_error_p95_mean=max_test_error_p95_mean,
        max_test_abs_bias_mean=max_test_abs_bias_mean,
    )

    partition_summaries = {
        partition: _partition_metric_summary(metrics, partition)
        for partition in ["train", "val", "test"]
        if partition in metrics
    }
    passed = len(errors) == 0
    status = "passed" if passed else "failed"
    report_path = output_dir_resolved / "model_quality_report.json"
    report: dict[str, Any] = {
        "schema_version": MODEL_QUALITY_REPORT_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "status": status,
        "passed": passed,
        "purpose": "audit saved ML run quality; no retraining or solver execution performed",
        "model_run_dir": str(model_run_dir),
        "output_dir": str(output_dir_resolved),
        "target_columns": target_columns,
        "feature_columns": list(train_config.get("feature_columns", [])),
        "model_type": train_config.get("model_type"),
        "dataset_path": train_config.get("dataset_path"),
        "quality_gate": gate_report,
        "partition_summaries": partition_summaries,
        "promotion": {
            "has_promotion_manifest": bool(promotion_manifest),
            "status": promotion_manifest.get("status") if promotion_manifest else None,
            "promotion_ready_at_time_of_promotion": promotion_manifest.get("promotion_ready_at_time_of_promotion") if promotion_manifest else None,
        },
        "manifest": {
            "has_ml_run_manifest": bool(ml_manifest),
            "status": ml_manifest.get("status") if ml_manifest else None,
        },
        "artifacts": {
            "model_quality_report_json": str(report_path),
            "residual_audit_csv": str(residual_audit_csv_path),
            "metrics_json": str(metrics_path),
            "metrics_json_sha256": file_sha256(metrics_path),
            "train_config_json": str(train_config_path),
            "train_config_json_sha256": file_sha256(train_config_path),
        },
        "worst_residual_rows_preview": worst_df.head(20).to_dict(orient="records"),
        "errors": errors,
        "warnings": warnings,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    artifacts = ModelQualityArtifacts(
        output_dir=output_dir_resolved,
        report_path=report_path,
        residual_audit_csv_path=residual_audit_csv_path,
    )
    result = ModelQualityResult(passed=passed, status=status, report=report, artifacts=artifacts)
    if fail_on_quality_gate and not passed:
        raise ValueError("Model quality audit failed; see model_quality_report.json for details")
    return result
