from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from aeris.dataset.promoted_dataset import require_promoted_aero_dataset
from aeris.ml.schema import SchemaValidationResult, validate_tabular_ml_schema


def validate_promoted_dataset_schema(
    *,
    dataset_path: str | Path,
    feature_columns: Iterable[str],
    target_columns: Iterable[str],
    group_column: str = "geometry_id",
    allow_forced: bool = False,
) -> SchemaValidationResult:
    """Validate ML schema against a promoted dataset's curated CSV."""
    dataset_root = Path(dataset_path).expanduser().resolve()
    context = require_promoted_aero_dataset(
        dataset_root=dataset_root,
        allow_forced=allow_forced,
    )
    curated_csv = Path(context["curated_aero_dataset_csv"]).expanduser().resolve()
    df = pd.read_csv(curated_csv)

    result = validate_tabular_ml_schema(
        df,
        feature_columns=feature_columns,
        target_columns=target_columns,
        group_column=group_column,
        require_group_column=bool(group_column),
    )

    metadata = dict(result.metadata)
    metadata.update(
        {
            "dataset_path": str(dataset_root),
            "curated_csv_path": str(curated_csv),
            "promotion_manifest_path": context.get("promotion_manifest_path"),
            "promotion_forced": bool(context.get("promotion_manifest", {}).get("promotion_forced", False)),
        }
    )

    return SchemaValidationResult(
        passed=result.passed,
        errors=result.errors,
        warnings=result.warnings,
        metadata=metadata,
    )


def require_valid_promoted_dataset_schema(
    *,
    dataset_path: str | Path,
    feature_columns: Iterable[str],
    target_columns: Iterable[str],
    group_column: str = "geometry_id",
    allow_forced: bool = False,
) -> SchemaValidationResult:
    """Validate schema and raise a compact error if it fails."""
    result = validate_promoted_dataset_schema(
        dataset_path=dataset_path,
        feature_columns=feature_columns,
        target_columns=target_columns,
        group_column=group_column,
        allow_forced=allow_forced,
    )
    if not result.passed:
        messages = "; ".join(issue.message for issue in result.errors)
        raise ValueError(f"ML dataset schema validation failed: {messages}")
    return result
