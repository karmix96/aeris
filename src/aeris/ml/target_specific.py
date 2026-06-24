"""Target-specific ML training orchestration for AERIS.

This module intentionally reuses ``train_baseline_model`` instead of
reimplementing training. Each target gets a normal AERIS ML run directory, so
existing metrics, diagnostics, manifests, model artifacts, and later promotion
logic stay compatible.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from aeris.ml.manifest import utc_now_iso
from aeris.ml.train import SplitMethod, train_baseline_model

SCHEMA_VERSION = "aeris.target_specific_training.v1"


def _safe_target_dir_name(target: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(target).strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "target"


def _json_safe_number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _metric(metrics: dict[str, Any], partition: str, target: str, name: str) -> float | int | None:
    partition_metrics = metrics.get(partition, {}) or {}
    per_target = partition_metrics.get("per_target", {}) or {}
    target_metrics = per_target.get(target, {}) or {}
    value = target_metrics.get(name)
    if value is None:
        # For one-target runs the aggregate value is equivalent and useful as a fallback.
        overall_name = {
            "rmse": "rmse_mean",
            "mae": "mae_mean",
            "r2": "r2_mean",
            "max_abs_error": "max_abs_error_mean",
        }.get(name)
        if overall_name is not None:
            value = (partition_metrics.get("overall", {}) or {}).get(overall_name)
    return _json_safe_number(value)


def _quality_hint(test_r2: float | int | None) -> str:
    """Give a conservative operator hint, not a promotion decision."""
    if test_r2 is None:
        return "review_missing_test_r2"
    if float(test_r2) < 0.0:
        return "weak_target_negative_r2"
    if float(test_r2) < 0.5:
        return "weak_target_low_r2"
    return "review_candidate"


def _split_identity_sha256(df: Any, *, feature_columns: list[str], group_column: str) -> str:
    """Hash row identity without target columns, so target-specific splits can be compared."""
    columns: list[str] = []
    if group_column in getattr(df, "columns", []):
        columns.append(group_column)
    columns.extend([col for col in feature_columns if col in getattr(df, "columns", [])])

    if not columns:
        # Last resort: row count/order only. This should be rare because features are validated upstream.
        payload = "\n".join(str(i) for i in range(len(df)))
    else:
        payload = df[columns].to_csv(index=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "target",
        "status",
        "model_type",
        "run_dir",
        "train_rows",
        "val_rows",
        "test_rows",
        "train_rmse",
        "train_mae",
        "train_r2",
        "val_rmse",
        "val_mae",
        "val_r2",
        "test_rmse",
        "test_mae",
        "test_r2",
        "test_nrmse_by_std",
        "test_nrmse_by_range",
        "quality_hint",
        "metrics_path",
        "model_path",
        "ml_run_manifest_path",
        "error_type",
        "error_message",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def train_target_specific_models(
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
    feature_set_name: str | None = None,
    feature_preset_name: str | None = None,
) -> dict[str, Any]:
    """Train one normal AERIS model run per target column.

    This is an orchestration wrapper. It does not alter model fitting semantics.
    """
    dataset_path = Path(dataset_path).expanduser().resolve()
    target_columns = [str(target).strip() for target in target_columns if str(target).strip()]
    if not target_columns:
        raise ValueError("target_columns must contain at least one target.")
    if len(set(target_columns)) != len(target_columns):
        raise ValueError(f"target_columns contains duplicates: {target_columns}")

    if output_dir is None:
        output_dir = (
            Path("data")
            / "processed"
            / "ml_runs"
            / f"target_specific__{model_type}__{dataset_path.name}__seed{random_seed}"
        )
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    targets_root = output_dir / "targets"
    targets_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    target_results: dict[str, dict[str, Any]] = {}
    split_identities: dict[str, dict[str, str]] = {}
    used_dir_names: set[str] = set()

    for index, target in enumerate(target_columns):
        base_dir_name = _safe_target_dir_name(target)
        dir_name = base_dir_name
        if dir_name in used_dir_names:
            dir_name = f"{base_dir_name}_{index:02d}"
        used_dir_names.add(dir_name)

        run_dir = targets_root / dir_name
        row: dict[str, Any] = {
            "target": target,
            "status": "failed",
            "model_type": model_type,
            "run_dir": str(run_dir),
            "error_type": None,
            "error_message": None,
        }

        try:
            result = train_baseline_model(
                dataset_path=dataset_path,
                feature_columns=list(feature_columns),
                target_columns=[target],
                model_type=model_type,
                split_method=split_method,
                group_column=group_column,
                train_fraction=train_fraction,
                val_fraction=val_fraction,
                test_fraction=test_fraction,
                random_seed=random_seed,
                allow_forced=allow_forced,
                model_params=dict(model_params or {}),
                output_dir=run_dir,
                feature_set_name=feature_set_name,
                feature_preset_name=feature_preset_name,
            )

            split = result["split"]
            metrics = result["metrics"]
            artifacts = result["artifacts"]

            train_id = _split_identity_sha256(
                split.train_df,
                feature_columns=list(feature_columns),
                group_column=group_column,
            )
            val_id = _split_identity_sha256(
                split.val_df,
                feature_columns=list(feature_columns),
                group_column=group_column,
            )
            test_id = _split_identity_sha256(
                split.test_df,
                feature_columns=list(feature_columns),
                group_column=group_column,
            )
            split_identities[target] = {
                "train": train_id,
                "val": val_id,
                "test": test_id,
            }

            test_r2 = _metric(metrics, "test", target, "r2")
            row.update(
                {
                    "status": "success",
                    "train_rows": int(len(split.train_df)),
                    "val_rows": int(len(split.val_df)),
                    "test_rows": int(len(split.test_df)),
                    "train_rmse": _metric(metrics, "train", target, "rmse"),
                    "train_mae": _metric(metrics, "train", target, "mae"),
                    "train_r2": _metric(metrics, "train", target, "r2"),
                    "val_rmse": _metric(metrics, "val", target, "rmse"),
                    "val_mae": _metric(metrics, "val", target, "mae"),
                    "val_r2": _metric(metrics, "val", target, "r2"),
                    "test_rmse": _metric(metrics, "test", target, "rmse"),
                    "test_mae": _metric(metrics, "test", target, "mae"),
                    "test_r2": test_r2,
                    "test_nrmse_by_std": _metric(metrics, "test", target, "nrmse_by_std"),
                    "test_nrmse_by_range": _metric(metrics, "test", target, "nrmse_by_range"),
                    "quality_hint": _quality_hint(test_r2),
                    "metrics_path": str(artifacts.metrics_path),
                    "model_path": str(artifacts.model_path),
                    "ml_run_manifest_path": (
                        None
                        if artifacts.ml_run_manifest_path is None
                        else str(artifacts.ml_run_manifest_path)
                    ),
                }
            )
            target_results[target] = {
                "status": "success",
                "run_dir": str(artifacts.run_dir),
                "metrics_path": str(artifacts.metrics_path),
                "model_path": str(artifacts.model_path),
                "ml_run_manifest_path": (
                    None
                    if artifacts.ml_run_manifest_path is None
                    else str(artifacts.ml_run_manifest_path)
                ),
                "split_identity": split_identities[target],
            }
        except Exception as exc:  # noqa: BLE001 - per-target report must capture failures.
            row.update(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            target_results[target] = {
                "status": "failed",
                "run_dir": str(run_dir),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }

        rows.append(row)

    successful_targets = [row["target"] for row in rows if row["status"] == "success"]
    failed_targets = [row["target"] for row in rows if row["status"] != "success"]

    successful_split_identities = {
        target: identities
        for target, identities in split_identities.items()
        if target in successful_targets
    }
    split_identity_consistent = True
    if successful_split_identities:
        first = next(iter(successful_split_identities.values()))
        split_identity_consistent = all(ids == first for ids in successful_split_identities.values())

    summary_csv_path = output_dir / "target_specific_training_summary.csv"
    report_path = output_dir / "target_specific_training_report.json"
    model_index_path = output_dir / "target_model_index.json"

    _write_csv(summary_csv_path, rows)

    model_index = {
        "schema_version": "aeris.target_model_index.v1",
        "created_at_utc": utc_now_iso(),
        "output_dir": str(output_dir),
        "targets": target_results,
    }
    model_index_path.write_text(json.dumps(model_index, indent=2), encoding="utf-8")

    status = "success"
    if failed_targets and successful_targets:
        status = "partial_failure"
    elif failed_targets and not successful_targets:
        status = "failed"

    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "status": status,
        "dataset_path": str(dataset_path),
        "output_dir": str(output_dir),
        "model_type": model_type,
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "feature_set_name": feature_set_name,
        "feature_preset_name": feature_preset_name,
        "split_config": {
            "split_method": split_method,
            "group_column": group_column,
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "random_seed": random_seed,
        },
        "target_count": len(target_columns),
        "successful_target_count": len(successful_targets),
        "failed_target_count": len(failed_targets),
        "successful_targets": successful_targets,
        "failed_targets": failed_targets,
        "split_identity": {
            "consistent_across_successful_targets": split_identity_consistent,
            "by_target": successful_split_identities,
        },
        "targets": rows,
        "artifacts": {
            "summary_csv": str(summary_csv_path),
            "model_index_json": str(model_index_path),
            "report_json": str(report_path),
            "targets_root": str(targets_root),
        },
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return {
        "output_dir": output_dir,
        "report": report,
        "report_path": report_path,
        "summary_csv_path": summary_csv_path,
        "model_index_path": model_index_path,
        "target_results": target_results,
        "successful_targets": successful_targets,
        "failed_targets": failed_targets,
    }
