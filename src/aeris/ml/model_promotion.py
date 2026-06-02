from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import build_environment_snapshot, utc_now_iso
from aeris.ml.validation import validate_promoted_dataset_schema

MODEL_PROMOTION_SCHEMA_VERSION = "aeris.model_promotion_manifest.v1"
MODEL_CARD_SCHEMA_VERSION = "aeris.model_card.v1"
TRAINING_ENVELOPE_SCHEMA_VERSION = "aeris.training_envelope.v1"


@dataclass(frozen=True)
class ModelPromotionResult:
    model_run_dir: Path
    passed: bool
    manifest_path: Path
    model_card_path: Path
    training_envelope_path: Path | None
    blockers: list[str]
    warnings: list[str]
    manifest: dict[str, Any]


def _load_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing required JSON file: {path}")
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _resolve_model_path(model_run_dir: Path) -> Path:
    candidates = [model_run_dir / "models" / "model.pkl", model_run_dir / "model.pkl"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find model artifact under: {model_run_dir}")


def _metric(metrics: dict[str, Any], dotted_path: str) -> float | None:
    node: Any = metrics
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if node is None:
        return None
    try:
        return float(node)
    except Exception:
        return None


def _artifact_hashes(model_run_dir: Path) -> dict[str, Any]:
    train_config_path = model_run_dir / "train_config.json"
    metrics_path = model_run_dir / "metrics.json"
    ml_run_manifest_path = model_run_dir / "ml_run_manifest.json"
    model_path = _resolve_model_path(model_run_dir)
    paths = {
        "train_config": train_config_path,
        "metrics": metrics_path,
        "ml_run_manifest": ml_run_manifest_path,
        "model": model_path,
    }
    hashes: dict[str, Any] = {}
    for name, path in paths.items():
        hashes[name] = {
            "path": str(path),
            "exists": path.exists(),
            "sha256": file_sha256(path) if path.exists() else None,
        }
    return hashes


def _build_training_envelope(
    *,
    model_run_dir: Path,
    feature_columns: list[str],
    target_columns: list[str],
    group_column: str | None,
) -> tuple[Path | None, list[str]]:
    warnings: list[str] = []
    train_rows_path = model_run_dir / "train_rows.csv"
    if not train_rows_path.exists():
        warnings.append("training envelope skipped because train_rows.csv is missing")
        return None, warnings

    df = pd.read_csv(train_rows_path)
    missing_features = [c for c in feature_columns if c not in df.columns]
    if missing_features:
        warnings.append(f"training envelope skipped; missing feature columns in train_rows.csv: {missing_features}")
        return None, warnings

    feature_ranges: dict[str, dict[str, Any]] = {}
    for col in feature_columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        finite = numeric.dropna()
        if finite.empty:
            feature_ranges[col] = {"min": None, "max": None, "mean": None, "std": None, "n_finite": 0}
            warnings.append(f"feature '{col}' has no finite values in train_rows.csv")
            continue
        feature_ranges[col] = {
            "min": float(finite.min()),
            "max": float(finite.max()),
            "mean": float(finite.mean()),
            "std": float(finite.std(ddof=0)),
            "n_finite": int(finite.shape[0]),
        }

    target_ranges: dict[str, dict[str, Any]] = {}
    for col in target_columns:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        finite = numeric.dropna()
        if finite.empty:
            continue
        target_ranges[col] = {
            "min": float(finite.min()),
            "max": float(finite.max()),
            "mean": float(finite.mean()),
            "std": float(finite.std(ddof=0)),
            "n_finite": int(finite.shape[0]),
        }

    group_info: dict[str, Any] | None = None
    if group_column and group_column in df.columns:
        group_info = {
            "group_column": group_column,
            "n_groups": int(df[group_column].nunique(dropna=True)),
        }

    envelope = {
        "schema_version": TRAINING_ENVELOPE_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "train_rows_csv": str(train_rows_path),
        "n_train_rows": int(len(df)),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "feature_ranges": feature_ranges,
        "target_ranges": target_ranges,
        "groups": group_info,
    }
    path = _write_json(model_run_dir / "training_envelope.json", envelope)
    return path, warnings


def promote_model_run(
    *,
    model_run_dir: str | Path,
    max_val_rmse_mean: float | None = None,
    max_test_rmse_mean: float | None = None,
    min_test_r2_mean: float | None = None,
    require_diagnostics: bool = True,
    allow_forced_dataset: bool = False,
    notes: str | None = None,
) -> ModelPromotionResult:
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")

    train_config_path = model_run_dir / "train_config.json"
    metrics_path = model_run_dir / "metrics.json"
    ml_run_manifest_path = model_run_dir / "ml_run_manifest.json"
    diagnostics_dir = model_run_dir / "diagnostics"
    model_path = _resolve_model_path(model_run_dir)

    train_config = _load_json(train_config_path)
    metrics = _load_json(metrics_path)
    ml_manifest = _load_json(ml_run_manifest_path)

    blockers: list[str] = []
    warnings: list[str] = []

    if require_diagnostics and not diagnostics_dir.exists():
        blockers.append("diagnostics directory is missing")

    promotion_context = ml_manifest.get("dataset", {}).get("promotion_context", {})
    if not promotion_context:
        blockers.append("ml_run_manifest.json does not contain dataset promotion_context")
    else:
        if promotion_context.get("promotion_ready_at_time_of_promotion") is False:
            blockers.append("source dataset was not promotion-ready at time of dataset promotion")
        if promotion_context.get("promotion_forced") and not allow_forced_dataset:
            blockers.append("source dataset was force-promoted; pass --allow-forced-dataset only for explicit override workflows")
        dataset_blockers = promotion_context.get("promotion_blockers") or []
        if dataset_blockers:
            blockers.append(f"source dataset promotion blockers were recorded: {dataset_blockers}")

    val_rmse = _metric(metrics, "val.overall.rmse_mean")
    test_rmse = _metric(metrics, "test.overall.rmse_mean")
    test_r2 = _metric(metrics, "test.overall.r2_mean")

    if max_val_rmse_mean is not None:
        if val_rmse is None:
            blockers.append("val.overall.rmse_mean metric is missing")
        elif val_rmse > max_val_rmse_mean:
            blockers.append(f"val.overall.rmse_mean={val_rmse} exceeds threshold {max_val_rmse_mean}")
    if max_test_rmse_mean is not None:
        if test_rmse is None:
            blockers.append("test.overall.rmse_mean metric is missing")
        elif test_rmse > max_test_rmse_mean:
            blockers.append(f"test.overall.rmse_mean={test_rmse} exceeds threshold {max_test_rmse_mean}")
    if min_test_r2_mean is not None:
        if test_r2 is None:
            blockers.append("test.overall.r2_mean metric is missing")
        elif test_r2 < min_test_r2_mean:
            blockers.append(f"test.overall.r2_mean={test_r2} is below threshold {min_test_r2_mean}")

    feature_columns = list(train_config.get("feature_columns", []))
    target_columns = list(train_config.get("target_columns", []))
    group_column = train_config.get("group_column")

    # CLI.2 — Validate ML schema of source promoted dataset at promotion time.
    # If the model was trained from a named feature set, validate the promoted
    # curated dataset against that feature set instead of requiring engineered
    # columns to physically exist in curated_aero_dataset.csv. Engineered columns
    # are produced by explicit/auditable transforms, not stored as raw solver data.
    feature_set_name = train_config.get("feature_set_name")
    if not feature_set_name:
        _training_data = ml_manifest.get("training_data", {})
        if isinstance(_training_data, dict):
            feature_set_name = _training_data.get("feature_set_name")
    if not feature_set_name:
        _feature_set_payload = train_config.get("feature_set")
        if isinstance(_feature_set_payload, dict):
            feature_set_name = _feature_set_payload.get("name")

    _dataset_path = train_config.get("dataset_path")
    if _dataset_path:
        try:
            if feature_set_name:
                from aeris.ml.feature_sets import validate_promoted_dataset_feature_set

                _schema_result = validate_promoted_dataset_feature_set(
                    dataset_path=_dataset_path,
                    feature_set_name=str(feature_set_name),
                    target_columns=target_columns,
                    group_column=str(group_column) if group_column else "geometry_id",
                    allow_forced=allow_forced_dataset,
                )
            else:
                _schema_result = validate_promoted_dataset_schema(
                    dataset_path=_dataset_path,
                    feature_columns=feature_columns,
                    target_columns=target_columns,
                    group_column=str(group_column) if group_column else "geometry_id",
                    allow_forced=allow_forced_dataset,
                )
            if not _schema_result.passed:
                _errs = "; ".join(i.message for i in _schema_result.errors)
                blockers.append(f"promoted dataset schema validation failed: {_errs}")
        except Exception as _exc:
            warnings.append(
                f"promoted dataset schema validation skipped — "
                f"dataset not accessible: {_exc}"
            )
    else:
        warnings.append(
            "train_config.json does not record dataset_path; schema validation skipped"
        )

    envelope_path, envelope_warnings = _build_training_envelope(
        model_run_dir=model_run_dir,
        feature_columns=feature_columns,
        target_columns=target_columns,
        group_column=None if group_column is None else str(group_column),
    )
    warnings.extend(envelope_warnings)

    artifact_hashes = _artifact_hashes(model_run_dir)
    passed = len(blockers) == 0

    manifest = {
        "schema_version": MODEL_PROMOTION_SCHEMA_VERSION,
        "status": "approved" if passed else "rejected",
        "promoted_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "promotion_ready_at_time_of_promotion": passed,
        "promotion_forced": False,
        "promotion_blockers": blockers,
        "warnings": warnings,
        "notes": notes,
        "feature_set_name": feature_set_name,
        "thresholds": {
            "max_val_rmse_mean": max_val_rmse_mean,
            "max_test_rmse_mean": max_test_rmse_mean,
            "min_test_r2_mean": min_test_r2_mean,
            "require_diagnostics": require_diagnostics,
            "allow_forced_dataset": allow_forced_dataset,
        },
        "model": {
            "model_type": train_config.get("model_type"),
            "feature_set_name": feature_set_name,
            "feature_set": train_config.get("feature_set"),
            "model_params": train_config.get("model_params", {}),
            "feature_columns": feature_columns,
            "target_columns": target_columns,
            "model_path": str(model_path),
        },
        "dataset": {
            "dataset_path": train_config.get("dataset_path"),
            "promotion_context": promotion_context,
            "fingerprints": ml_manifest.get("dataset", {}).get("fingerprints"),
        },
        "split": ml_manifest.get("split", {}),
        "metrics": {
            "val_rmse_mean": val_rmse,
            "test_rmse_mean": test_rmse,
            "test_r2_mean": test_r2,
            "full_metrics_path": str(metrics_path),
        },
        "artifacts": {
            "hashes": artifact_hashes,
            "train_config_path": str(train_config_path),
            "metrics_path": str(metrics_path),
            "ml_run_manifest_path": str(ml_run_manifest_path),
            "diagnostics_dir": str(diagnostics_dir),
            "training_envelope_path": None if envelope_path is None else str(envelope_path),
            "model_path": str(model_path),
        },
        "environment": build_environment_snapshot(),
    }
    manifest_path = _write_json(model_run_dir / "model_promotion_manifest.json", manifest)

    model_card = {
        "schema_version": MODEL_CARD_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "status": manifest["status"],
        "model_type": train_config.get("model_type"),
        "feature_set_name": feature_set_name,
        "feature_set": train_config.get("feature_set"),
        "features": feature_columns,
        "targets": target_columns,
        "source_dataset": train_config.get("dataset_path"),
        "metrics": manifest["metrics"],
        "promotion_blockers": blockers,
        "warnings": warnings,
        "intended_use": "AERIS scalar surrogate inference within the recorded training envelope only.",
        "not_intended_for": [
            "extrapolation outside recorded feature ranges without guard checks",
            "certification or safety decisions without higher-fidelity validation",
            "flight-critical control without VVUQ escalation",
        ],
        "training_envelope_path": None if envelope_path is None else str(envelope_path),
        "promotion_manifest_path": str(manifest_path),
    }
    model_card_path = _write_json(model_run_dir / "model_card.json", model_card)

    return ModelPromotionResult(
        model_run_dir=model_run_dir,
        passed=passed,
        manifest_path=manifest_path,
        model_card_path=model_card_path,
        training_envelope_path=envelope_path,
        blockers=blockers,
        warnings=warnings,
        manifest=manifest,
    )


def inspect_model_run(model_run_dir: str | Path) -> dict[str, Any]:
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    train_config = _load_json(model_run_dir / "train_config.json")
    metrics = _load_json(model_run_dir / "metrics.json")
    ml_manifest = _load_json(model_run_dir / "ml_run_manifest.json", required=False)
    promotion_manifest = _load_json(model_run_dir / "model_promotion_manifest.json", required=False)
    model_card = _load_json(model_run_dir / "model_card.json", required=False)
    return {
        "model_run_dir": str(model_run_dir),
        "model_type": train_config.get("model_type"),
        "feature_set_name": train_config.get("feature_set_name") or promotion_manifest.get("feature_set_name"),
        "feature_columns": train_config.get("feature_columns", []),
        "target_columns": train_config.get("target_columns", []),
        "dataset_path": train_config.get("dataset_path"),
        "metrics": {
            "val_rmse_mean": _metric(metrics, "val.overall.rmse_mean"),
            "test_rmse_mean": _metric(metrics, "test.overall.rmse_mean"),
            "test_r2_mean": _metric(metrics, "test.overall.r2_mean"),
        },
        "promotion": {
            "has_manifest": bool(promotion_manifest),
            "status": promotion_manifest.get("status"),
            "promotion_ready_at_time_of_promotion": promotion_manifest.get("promotion_ready_at_time_of_promotion"),
            "blockers": promotion_manifest.get("promotion_blockers", []),
            "manifest_path": str(model_run_dir / "model_promotion_manifest.json"),
        },
        "has_model_card": bool(model_card),
        "has_ml_run_manifest": bool(ml_manifest),
    }


def require_promoted_model(
    model_run_dir: str | Path,
    *,
    verify_hashes: bool = True,
    allow_rejected: bool = False,
) -> dict[str, Any]:
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    manifest_path = model_run_dir / "model_promotion_manifest.json"
    manifest = _load_json(manifest_path)
    status = manifest.get("status")
    if status != "approved" and not allow_rejected:
        raise ValueError(f"Model is not promoted/approved. status={status}, blockers={manifest.get('promotion_blockers', [])}")
    if manifest.get("promotion_ready_at_time_of_promotion") is not True and not allow_rejected:
        raise ValueError("Model promotion manifest does not mark the model as promotion-ready.")
    if verify_hashes:
        recorded_hashes = manifest.get("artifacts", {}).get("hashes", {})
        current_hashes = _artifact_hashes(model_run_dir)
        mismatches: list[str] = []
        for name, recorded in recorded_hashes.items():
            recorded_sha = recorded.get("sha256") if isinstance(recorded, dict) else None
            current_sha = current_hashes.get(name, {}).get("sha256")
            if recorded_sha != current_sha:
                mismatches.append(name)
        if mismatches:
            raise ValueError(f"Promoted model artifact hashes no longer match: {mismatches}")
    return manifest
