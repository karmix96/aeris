from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from aeris.dataset.promoted_dataset import require_promoted_aero_dataset
from aeris.ml.feature_engineering import FEATURE_TRANSFORMS, apply_feature_engineering
from aeris.ml.schema import SchemaIssue, SchemaValidationResult


FEATURE_SET_SCHEMA_VERSION = "aeris.ml.feature_set.v1"


class FeatureSetError(ValueError):
    """Raised when a named ML feature set cannot be resolved or validated."""


@dataclass(frozen=True)
class FeatureSet:
    """A named ML input representation.

    A feature preset is just a column bundle. A feature set is stronger: it
    records the intended domain, generator family, raw source columns, optional
    feature-engineering transforms, and the final columns expected by the ML
    layer. This gives AERIS a clean seam for comparing raw vs physics-informed
    inputs without hiding engineered columns inside training code.
    """

    name: str
    domain: str
    description: str
    raw_columns: tuple[str, ...]
    engineered_columns: tuple[str, ...] = ()
    transforms: tuple[str, ...] = ()
    generator_id: str | None = None
    status: str = "active"
    version: str = "v1"
    tags: tuple[str, ...] = ()

    @property
    def columns(self) -> tuple[str, ...]:
        """Final feature columns expected after optional transforms."""
        return self.raw_columns + self.engineered_columns

    @property
    def required_source_columns(self) -> tuple[str, ...]:
        """Columns that must exist in the promoted curated dataset."""
        return self.raw_columns

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FEATURE_SET_SCHEMA_VERSION,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "generator_id": self.generator_id,
            "status": self.status,
            "version": self.version,
            "tags": list(self.tags),
            "raw_columns": list(self.raw_columns),
            "engineered_columns": list(self.engineered_columns),
            "columns": list(self.columns),
            "required_source_columns": list(self.required_source_columns),
            "transforms": list(self.transforms),
        }


BWB_CONTROL_RAW_COLUMNS: tuple[str, ...] = (
    "c1_m",
    "b_total_m",
    "sw1_deg",
    "alpha_deg",
    "velocity_mps",
    "altitude_m",
    "control_input_deg",
)


BWB_CONTROL_SYM_ELEVON_RAW_COLUMNS: tuple[str, ...] = (
    "c1_m",
    "b_total_m",
    "sw1_deg",
    "alpha_deg",
    "velocity_mps",
    "altitude_m",
    "delta_e_sym_deg",
)


BWB_CONTROL_PHYSICS_TRANSFORMS: tuple[str, ...] = (
    "alpha_sq",
    "abs_alpha",
    "control_sq",
    "alpha_x_control",
    "dynamic_pressure_proxy",
    "aspect_ratio_proxy",
    "sweep_alpha_interaction",
    "re_number",
)


BWB_CONTROL_SYM_ELEVON_PHYSICS_TRANSFORMS: tuple[str, ...] = (
    "alpha_sq",
    "abs_alpha",
    "delta_e_sym_sq",
    "alpha_x_delta_e_sym",
    "dynamic_pressure_proxy",
    "aspect_ratio_proxy",
    "sweep_alpha_interaction",
    "re_number",
)


def _transform_output_columns(transforms: Iterable[str]) -> tuple[str, ...]:
    output_columns: list[str] = []
    for transform_key in transforms:
        try:
            transform = FEATURE_TRANSFORMS[transform_key]
        except KeyError as exc:
            supported = ", ".join(sorted(FEATURE_TRANSFORMS))
            raise FeatureSetError(
                f"Feature set references unknown transform '{transform_key}'. "
                f"Supported transforms: {supported}"
            ) from exc
        output_columns.extend(transform.output_columns)
    return tuple(output_columns)


_FEATURE_SETS: dict[str, FeatureSet] = {
    "bwb_control_raw": FeatureSet(
        name="bwb_control_raw",
        domain="bwb_scalar_aero",
        generator_id="bwb_segmented_v1",
        raw_columns=BWB_CONTROL_RAW_COLUMNS,
        engineered_columns=(),
        transforms=(),
        description=(
            "Raw current BWB control feature set. This is the production-safe "
            "alias for the existing bwb_control preset: no Reynolds, Mach, "
            "qbar, trigonometric, squared, or interaction features are added."
        ),
        tags=("bwb", "control", "raw", "tabular"),
    ),
    "bwb_control_physics_v1": FeatureSet(
        name="bwb_control_physics_v1",
        domain="bwb_scalar_aero",
        generator_id="bwb_segmented_v1",
        raw_columns=BWB_CONTROL_RAW_COLUMNS,
        engineered_columns=_transform_output_columns(BWB_CONTROL_PHYSICS_TRANSFORMS),
        transforms=BWB_CONTROL_PHYSICS_TRANSFORMS,
        description=(
            "Backward-compatible physics-informed BWB control feature set using "
            "the legacy control_input_deg column. Keep this for old datasets and "
            "existing model runs; prefer bwb_control_sym_elevon_physics_v1 for "
            "new D1b.2+ datasets."
        ),
        tags=("bwb", "control", "legacy-control", "physics", "tabular", "engineered"),
    ),
    "bwb_control_sym_elevon_raw": FeatureSet(
        name="bwb_control_sym_elevon_raw",
        domain="bwb_scalar_aero",
        generator_id="bwb_segmented_v1",
        raw_columns=BWB_CONTROL_SYM_ELEVON_RAW_COLUMNS,
        engineered_columns=(),
        transforms=(),
        description=(
            "Raw BWB control feature set using explicit symmetric-elevon naming. "
            "This is the preferred raw feature set for new D1b.2+ datasets. "
            "It uses delta_e_sym_deg instead of the legacy control_input_deg alias."
        ),
        tags=("bwb", "control", "symmetric-elevon", "raw", "tabular"),
    ),
    "bwb_control_sym_elevon_physics_v1": FeatureSet(
        name="bwb_control_sym_elevon_physics_v1",
        domain="bwb_scalar_aero",
        generator_id="bwb_segmented_v1",
        raw_columns=BWB_CONTROL_SYM_ELEVON_RAW_COLUMNS,
        engineered_columns=_transform_output_columns(BWB_CONTROL_SYM_ELEVON_PHYSICS_TRANSFORMS),
        transforms=BWB_CONTROL_SYM_ELEVON_PHYSICS_TRANSFORMS,
        description=(
            "Physics-informed BWB control feature set using explicit symmetric-"
            "elevon naming. It derives nonlinear and interaction terms from "
            "delta_e_sym_deg, not from the legacy control_input_deg alias."
        ),
        tags=("bwb", "control", "symmetric-elevon", "physics", "tabular", "engineered"),
    ),
}


def list_feature_sets(*, include_inactive: bool = False) -> list[FeatureSet]:
    """Return registered feature sets in stable name order."""
    feature_sets = sorted(_FEATURE_SETS.values(), key=lambda item: item.name)
    if include_inactive:
        return feature_sets
    return [item for item in feature_sets if item.status == "active"]


def list_feature_set_names(*, include_inactive: bool = False) -> list[str]:
    """Return registered feature-set names."""
    return [item.name for item in list_feature_sets(include_inactive=include_inactive)]


def get_feature_set(name: str) -> FeatureSet:
    """Resolve a feature set by name."""
    key = str(name).strip()
    if not key:
        raise FeatureSetError("Feature-set name must not be empty.")
    try:
        return _FEATURE_SETS[key]
    except KeyError as exc:
        supported = ", ".join(list_feature_set_names(include_inactive=True))
        raise FeatureSetError(
            f"Unknown feature set '{name}'. Supported feature sets: {supported}"
        ) from exc


def describe_feature_set(name: str) -> dict[str, Any]:
    """Return a JSON-safe description for one feature set."""
    return get_feature_set(name).to_dict()


def _clean_columns(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    out: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean:
            out.append(clean)
    return out


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _numeric_issues(df: pd.DataFrame, columns: list[str], *, label: str) -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []
    non_numeric: list[str] = []
    non_finite: list[str] = []

    for column in columns:
        if column not in df.columns:
            continue
        series = pd.to_numeric(df[column], errors="coerce")
        original_non_missing = df[column].notna().to_numpy()
        converted_missing = series.isna().to_numpy()
        if bool(np.any(original_non_missing & converted_missing)):
            non_numeric.append(column)
            continue
        values = series.to_numpy(dtype=float)
        if not bool(np.isfinite(values).all()):
            non_finite.append(column)

    if non_numeric:
        issues.append(
            SchemaIssue(
                "error",
                f"non_numeric_{label}_columns",
                f"{label.title()} columns contain non-numeric values: {non_numeric}",
                tuple(non_numeric),
            )
        )
    if non_finite:
        issues.append(
            SchemaIssue(
                "error",
                f"non_finite_{label}_columns",
                f"{label.title()} columns contain NaN/inf values: {non_finite}",
                tuple(non_finite),
            )
        )
    return issues


def validate_feature_set_dataframe(
    df: pd.DataFrame,
    *,
    feature_set: FeatureSet | str,
    target_columns: Iterable[str] | None = None,
    group_column: str | None = "geometry_id",
    require_group_column: bool = True,
) -> SchemaValidationResult:
    """Validate whether a DataFrame can support a named feature set.

    This function may apply declared transforms in memory only. It does not
    write an engineered dataset. That explicit materialization is the next slice.
    """
    fs = get_feature_set(feature_set) if isinstance(feature_set, str) else feature_set
    targets = _clean_columns(target_columns)
    group = None if group_column is None else str(group_column).strip() or None

    errors: list[SchemaIssue] = []
    warnings: list[SchemaIssue] = []

    if df.empty:
        errors.append(SchemaIssue("error", "empty_dataframe", "Dataset dataframe is empty."))

    duplicate_features = _duplicate_values(list(fs.columns))
    if duplicate_features:
        errors.append(
            SchemaIssue(
                "error",
                "duplicate_feature_set_columns",
                f"Feature set contains duplicate columns: {duplicate_features}",
                tuple(duplicate_features),
            )
        )

    duplicate_targets = _duplicate_values(targets)
    if duplicate_targets:
        errors.append(
            SchemaIssue(
                "error",
                "duplicate_target_columns",
                f"Duplicate target columns requested: {duplicate_targets}",
                tuple(duplicate_targets),
            )
        )

    overlap = sorted(set(fs.columns) & set(targets))
    if overlap:
        errors.append(
            SchemaIssue(
                "error",
                "feature_target_overlap",
                f"Columns cannot be both features and targets: {overlap}",
                tuple(overlap),
            )
        )

    missing_source = [column for column in fs.required_source_columns if column not in df.columns]
    if missing_source:
        errors.append(
            SchemaIssue(
                "error",
                "missing_feature_set_source_columns",
                f"Missing raw source columns required by feature set '{fs.name}': {missing_source}",
                tuple(missing_source),
            )
        )

    if require_group_column:
        if not group:
            errors.append(
                SchemaIssue(
                    "error",
                    "missing_group_column_name",
                    "Feature-set validation requires a non-empty group_column name.",
                )
            )
        elif group not in df.columns:
            errors.append(
                SchemaIssue(
                    "error",
                    "missing_group_column",
                    f"Missing group column: {group}",
                    (group,),
                )
            )

    missing_targets = [column for column in targets if column not in df.columns]
    if missing_targets:
        errors.append(
            SchemaIssue(
                "error",
                "missing_target_columns",
                f"Missing target columns: {missing_targets}",
                tuple(missing_targets),
            )
        )

    augmented_df = df.copy()
    transform_manifest: dict[str, Any] | None = None
    if not missing_source and fs.transforms:
        try:
            augmented_df, transform_manifest = apply_feature_engineering(
                df,
                transforms=list(fs.transforms),
            )
        except Exception as exc:
            errors.append(
                SchemaIssue(
                    "error",
                    "feature_engineering_failed",
                    f"Feature engineering failed for feature set '{fs.name}': {exc}",
                )
            )

    missing_features = [column for column in fs.columns if column not in augmented_df.columns]
    if missing_features:
        errors.append(
            SchemaIssue(
                "error",
                "missing_feature_set_columns_after_transforms",
                f"Feature set columns are missing after transforms: {missing_features}",
                tuple(missing_features),
            )
        )

    existing_features = [column for column in fs.columns if column in augmented_df.columns]
    existing_targets = [column for column in targets if column in augmented_df.columns]

    errors.extend(_numeric_issues(augmented_df, existing_features, label="feature"))
    if existing_targets:
        errors.extend(_numeric_issues(augmented_df, existing_targets, label="target"))

    constant_features: list[str] = []
    for column in existing_features:
        try:
            if pd.to_numeric(augmented_df[column], errors="coerce").nunique(dropna=True) <= 1:
                constant_features.append(column)
        except Exception:
            pass
    if constant_features:
        warnings.append(
            SchemaIssue(
                "warning",
                "constant_feature_set_columns",
                f"Feature-set columns are constant in this dataset: {constant_features}",
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

    metadata: dict[str, Any] = {
        "schema_version": FEATURE_SET_SCHEMA_VERSION,
        "feature_set": fs.to_dict(),
        "feature_set_id": fs.name,
        "domain": fs.domain,
        "generator_id": fs.generator_id,
        "n_rows": int(len(df)),
        "n_columns_before_transforms": int(len(df.columns)),
        "n_columns_after_transforms": int(len(augmented_df.columns)),
        "raw_features": list(fs.raw_columns),
        "engineered_features": list(fs.engineered_columns),
        "feature_columns": list(fs.columns),
        "target_columns": targets,
        "group_column": group,
        "n_groups": group_unique_count,
        "transforms": list(fs.transforms),
        "transform_manifest": transform_manifest,
        "available_columns_before_transforms": list(df.columns),
        "available_columns_after_transforms": list(augmented_df.columns),
    }

    return SchemaValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        metadata=metadata,
    )


def validate_promoted_dataset_feature_set(
    *,
    dataset_path: str | Path,
    feature_set_name: str,
    target_columns: Iterable[str] | None = None,
    group_column: str | None = "geometry_id",
    allow_forced: bool = False,
) -> SchemaValidationResult:
    """Validate a named feature set against a promoted dataset's curated CSV."""
    dataset_root = Path(dataset_path).expanduser().resolve()
    context = require_promoted_aero_dataset(
        dataset_root=dataset_root,
        allow_forced=allow_forced,
    )
    curated_csv = Path(context["curated_aero_dataset_csv"]).expanduser().resolve()
    df = pd.read_csv(curated_csv)

    result = validate_feature_set_dataframe(
        df,
        feature_set=feature_set_name,
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
            "promotion_forced": bool(
                context.get("promotion_manifest", {}).get("promotion_forced", False)
            ),
        }
    )

    return SchemaValidationResult(
        passed=result.passed,
        errors=result.errors,
        warnings=result.warnings,
        metadata=metadata,
    )
