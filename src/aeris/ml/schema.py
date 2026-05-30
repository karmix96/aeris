from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SchemaIssue:
    level: str
    code: str
    message: str
    columns: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "columns": list(self.columns),
        }


@dataclass(frozen=True)
class SchemaValidationResult:
    passed: bool
    errors: tuple[SchemaIssue, ...]
    warnings: tuple[SchemaIssue, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "metadata": self.metadata,
        }


def _as_clean_list(values: Iterable[str], *, field_name: str) -> list[str]:
    out: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean:
            out.append(clean)
    if not out:
        raise ValueError(f"{field_name} must not be empty.")
    return out


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _non_numeric_or_non_finite_columns(df: pd.DataFrame, columns: list[str]) -> tuple[list[str], list[str]]:
    non_numeric: list[str] = []
    non_finite: list[str] = []

    for column in columns:
        series = pd.to_numeric(df[column], errors="coerce")
        original_non_missing = df[column].notna().to_numpy()
        converted_missing = series.isna().to_numpy()

        # A non-missing value that becomes NaN after numeric conversion means
        # the feature/target is not safely numeric.
        if bool(np.any(original_non_missing & converted_missing)):
            non_numeric.append(column)
            continue

        values = series.to_numpy(dtype=float)
        if not bool(np.isfinite(values).all()):
            non_finite.append(column)

    return non_numeric, non_finite


def validate_tabular_ml_schema(
    df: pd.DataFrame,
    *,
    feature_columns: Iterable[str],
    target_columns: Iterable[str],
    group_column: str | None = None,
    require_group_column: bool = True,
    require_numeric_features: bool = True,
    require_numeric_targets: bool = True,
    warn_constant_features: bool = True,
) -> SchemaValidationResult:
    """Validate a tabular ML dataset before training/tuning.

    This is intentionally generic. It does not assume BWB, airfoil, XFOIL, CFD,
    GNN, or any solver-specific schema. It only enforces ML safety basics:
    required columns, numeric finite feature/target values, grouping-column
    availability, and basic metadata useful for run manifests.
    """
    features = _as_clean_list(feature_columns, field_name="feature_columns")
    targets = _as_clean_list(target_columns, field_name="target_columns")
    group = None if group_column is None else str(group_column).strip() or None

    errors: list[SchemaIssue] = []
    warnings: list[SchemaIssue] = []

    if df.empty:
        errors.append(SchemaIssue("error", "empty_dataframe", "Dataset dataframe is empty."))

    for label, columns in [("feature", features), ("target", targets)]:
        duplicates = _duplicate_values(columns)
        if duplicates:
            errors.append(
                SchemaIssue(
                    "error",
                    f"duplicate_{label}_columns",
                    f"Duplicate {label} columns requested: {duplicates}",
                    tuple(duplicates),
                )
            )

    overlap = sorted(set(features) & set(targets))
    if overlap:
        errors.append(
            SchemaIssue(
                "error",
                "feature_target_overlap",
                f"Columns cannot be both features and targets: {overlap}",
                tuple(overlap),
            )
        )

    required = features + targets
    if require_group_column and group is not None:
        required.append(group)
    missing = [column for column in required if column not in df.columns]
    if missing:
        errors.append(
            SchemaIssue(
                "error",
                "missing_columns",
                f"Missing required columns: {missing}",
                tuple(missing),
            )
        )

    if require_group_column and not group:
        errors.append(
            SchemaIssue(
                "error",
                "missing_group_column_name",
                "Grouped ML validation requires a non-empty group_column name.",
            )
        )

    # Only run type/finite checks when the required columns exist, otherwise the
    # missing-column error is already the useful failure.
    existing_features = [column for column in features if column in df.columns]
    existing_targets = [column for column in targets if column in df.columns]

    if require_numeric_features and existing_features:
        non_numeric, non_finite = _non_numeric_or_non_finite_columns(df, existing_features)
        if non_numeric:
            errors.append(
                SchemaIssue(
                    "error",
                    "non_numeric_feature_columns",
                    f"Feature columns contain non-numeric values: {non_numeric}",
                    tuple(non_numeric),
                )
            )
        if non_finite:
            errors.append(
                SchemaIssue(
                    "error",
                    "non_finite_feature_columns",
                    f"Feature columns contain NaN/inf values: {non_finite}",
                    tuple(non_finite),
                )
            )

    if require_numeric_targets and existing_targets:
        non_numeric, non_finite = _non_numeric_or_non_finite_columns(df, existing_targets)
        if non_numeric:
            errors.append(
                SchemaIssue(
                    "error",
                    "non_numeric_target_columns",
                    f"Target columns contain non-numeric values: {non_numeric}",
                    tuple(non_numeric),
                )
            )
        if non_finite:
            errors.append(
                SchemaIssue(
                    "error",
                    "non_finite_target_columns",
                    f"Target columns contain NaN/inf values: {non_finite}",
                    tuple(non_finite),
                )
            )

    if warn_constant_features and existing_features:
        constant_features: list[str] = []
        for column in existing_features:
            try:
                if pd.to_numeric(df[column], errors="coerce").nunique(dropna=True) <= 1:
                    constant_features.append(column)
            except Exception:
                pass
        if constant_features:
            warnings.append(
                SchemaIssue(
                    "warning",
                    "constant_feature_columns",
                    f"Feature columns are constant in this dataset: {constant_features}",
                    tuple(constant_features),
                )
            )

    group_unique_count = None
    if group and group in df.columns:
        group_unique_count = int(df[group].nunique(dropna=True))
        if group_unique_count < 2:
            warnings.append(
                SchemaIssue(
                    "warning",
                    "low_group_count",
                    f"Group column '{group}' has fewer than 2 unique groups.",
                    (group,),
                )
            )

    metadata = {
        "n_rows": int(len(df)),
        "n_columns": int(len(df.columns)),
        "feature_columns": features,
        "target_columns": targets,
        "group_column": group,
        "n_features": int(len(features)),
        "n_targets": int(len(targets)),
        "n_groups": group_unique_count,
        "available_columns": list(df.columns),
    }

    return SchemaValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        metadata=metadata,
    )
