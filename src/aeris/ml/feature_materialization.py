from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from aeris.dataset.promoted_dataset import require_promoted_aero_dataset
from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import (
    FeatureSet,
    FeatureSetError,
    get_feature_set,
    validate_feature_set_dataframe,
)
from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso
from aeris.ml.schema import SchemaValidationResult


FEATURE_MATERIALIZATION_SCHEMA_VERSION = "aeris.ml.feature_materialization.v1"


class FeatureMaterializationError(ValueError):
    """Raised when a feature-set materialization request is invalid."""


@dataclass(frozen=True)
class FeatureMaterializationResult:
    dataset_path: Path
    curated_csv_path: Path
    output_dir: Path
    engineered_dataset_csv: Path
    feature_engineering_manifest_json: Path
    feature_schema_json: Path
    feature_materialization_report_json: Path
    feature_set: FeatureSet
    validation: SchemaValidationResult
    n_rows: int
    n_columns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FEATURE_MATERIALIZATION_SCHEMA_VERSION,
            "dataset_path": str(self.dataset_path),
            "curated_csv_path": str(self.curated_csv_path),
            "output_dir": str(self.output_dir),
            "engineered_dataset_csv": str(self.engineered_dataset_csv),
            "feature_engineering_manifest_json": str(self.feature_engineering_manifest_json),
            "feature_schema_json": str(self.feature_schema_json),
            "feature_materialization_report_json": str(self.feature_materialization_report_json),
            "feature_set": self.feature_set.to_dict(),
            "validation": self.validation.to_dict(),
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
        }


def _clean_columns(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    out: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean:
            out.append(clean)
    return out


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _validation_error_message(validation: SchemaValidationResult) -> str:
    if validation.passed:
        return "feature-set validation passed"
    messages = [f"{issue.code}: {issue.message}" for issue in validation.errors]
    return "; ".join(messages) or "feature-set validation failed"


def _select_materialized_columns(
    df: pd.DataFrame,
    *,
    feature_set: FeatureSet,
    target_columns: list[str],
    group_column: str | None,
    include_all_columns: bool,
) -> pd.DataFrame:
    if include_all_columns:
        return df.copy()

    columns: list[str] = []
    if group_column and group_column in df.columns:
        columns.append(group_column)
    columns.extend(feature_set.columns)
    columns.extend(target_columns)
    columns = _unique_preserve_order(columns)
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise FeatureMaterializationError(
            f"Cannot materialize selected columns because these columns are missing after transforms: {missing}"
        )
    return df[columns].copy()


def materialize_feature_set_dataset(
    *,
    dataset_path: str | Path,
    feature_set_name: str,
    target_columns: Iterable[str] | None = None,
    group_column: str | None = "geometry_id",
    output_dir: str | Path | None = None,
    allow_forced: bool = False,
    include_all_columns: bool = True,
    overwrite: bool = False,
) -> FeatureMaterializationResult:
    """Materialize a named feature set into explicit ML-ready artifacts.

    This function consumes a promoted aero dataset, applies the transforms
    declared by a named feature set, validates the resulting columns, and writes
    the materialized dataset plus schema/manifest/report files. It deliberately
    does not train a model. Training/compare/tune integration belongs in the next
    slice so the trust chain stays auditable.
    """
    dataset_root = Path(dataset_path).expanduser().resolve()
    feature_set = get_feature_set(feature_set_name)
    target_cols = _clean_columns(target_columns)
    group = None if group_column is None else str(group_column).strip() or None

    context = require_promoted_aero_dataset(
        dataset_root=dataset_root,
        allow_forced=allow_forced,
    )
    curated_csv_path = Path(context["curated_aero_dataset_csv"]).expanduser().resolve()
    df = pd.read_csv(curated_csv_path)

    if output_dir is None:
        out_dir = dataset_root / "features" / feature_set.name
    else:
        out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    engineered_csv_path = out_dir / "engineered_dataset.csv"
    fe_manifest_path = out_dir / "feature_engineering_manifest.json"
    feature_schema_path = out_dir / "feature_schema.json"
    report_path = out_dir / "feature_materialization_report.json"

    artifact_paths = [
        engineered_csv_path,
        fe_manifest_path,
        feature_schema_path,
        report_path,
    ]
    existing = [path for path in artifact_paths if path.exists()]
    if existing and not overwrite:
        raise FeatureMaterializationError(
            "Output artifacts already exist. Use overwrite=True or --overwrite to replace them: "
            + ", ".join(str(path) for path in existing)
        )

    augmented_df, fe_manifest = apply_feature_engineering(
        df,
        transforms=list(feature_set.transforms),
    )

    validation = validate_feature_set_dataframe(
        augmented_df,
        feature_set=feature_set,
        target_columns=target_cols,
        group_column=group,
    )
    if not validation.passed:
        raise FeatureMaterializationError(_validation_error_message(validation))

    materialized_df = _select_materialized_columns(
        augmented_df,
        feature_set=feature_set,
        target_columns=target_cols,
        group_column=group,
        include_all_columns=include_all_columns,
    )
    materialized_df.to_csv(engineered_csv_path, index=False)

    fe_manifest_payload = dict(fe_manifest)
    fe_manifest_payload.update(
        {
            "materialized_at": utc_now_iso(),
            "feature_set": feature_set.to_dict(),
            "input_curated_csv": str(curated_csv_path),
            "output_engineered_dataset_csv": str(engineered_csv_path),
        }
    )
    _write_json(fe_manifest_path, fe_manifest_payload)

    feature_schema_payload = {
        "schema_version": "aeris.ml.feature_schema.v1",
        "created_at": utc_now_iso(),
        "dataset_path": str(dataset_root),
        "curated_csv_path": str(curated_csv_path),
        "feature_set": feature_set.to_dict(),
        "raw_features": list(feature_set.raw_columns),
        "engineered_features": list(feature_set.engineered_columns),
        "final_features": list(feature_set.columns),
        "target_columns": target_cols,
        "group_column": group,
        "include_all_columns": bool(include_all_columns),
        "materialized_columns": list(materialized_df.columns),
        "validation": validation.to_dict(),
    }
    _write_json(feature_schema_path, feature_schema_payload)

    report_payload = {
        "schema_version": FEATURE_MATERIALIZATION_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "status": "completed",
        "dataset_path": str(dataset_root),
        "curated_csv_path": str(curated_csv_path),
        "feature_set_id": feature_set.name,
        "domain": feature_set.domain,
        "generator_id": feature_set.generator_id,
        "n_source_rows": int(len(df)),
        "n_source_columns": int(len(df.columns)),
        "n_materialized_rows": int(len(materialized_df)),
        "n_materialized_columns": int(len(materialized_df.columns)),
        "include_all_columns": bool(include_all_columns),
        "raw_features": list(feature_set.raw_columns),
        "engineered_features": list(feature_set.engineered_columns),
        "final_features": list(feature_set.columns),
        "target_columns": target_cols,
        "group_column": group,
        "transforms": list(feature_set.transforms),
        "validation": validation.to_dict(),
        "artifacts": {
            "engineered_dataset_csv": str(engineered_csv_path),
            "feature_engineering_manifest_json": str(fe_manifest_path),
            "feature_schema_json": str(feature_schema_path),
            "feature_materialization_report_json": str(report_path),
        },
        "hashes": {
            "curated_csv_sha256": file_sha256(curated_csv_path),
            "engineered_dataset_csv_sha256": file_sha256(engineered_csv_path),
        },
    }
    _write_json(report_path, report_payload)

    return FeatureMaterializationResult(
        dataset_path=dataset_root,
        curated_csv_path=curated_csv_path,
        output_dir=out_dir,
        engineered_dataset_csv=engineered_csv_path,
        feature_engineering_manifest_json=fe_manifest_path,
        feature_schema_json=feature_schema_path,
        feature_materialization_report_json=report_path,
        feature_set=feature_set,
        validation=validation,
        n_rows=int(len(materialized_df)),
        n_columns=int(len(materialized_df.columns)),
    )
