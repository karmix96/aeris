from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from aeris.ml.feature_engineering import apply_feature_engineering
from aeris.ml.feature_sets import FeatureSet, get_feature_set


class FeatureSetInferenceError(ValueError):
    """Raised when inference-time feature-set preparation is invalid."""


@dataclass(frozen=True)
class FeatureSetInferenceResult:
    dataframe: pd.DataFrame
    requested_feature_set_name: str | None
    trained_feature_set_name: str | None
    feature_set: FeatureSet | None
    feature_set_applied: bool
    allow_feature_set_mismatch: bool
    transform_manifest: dict[str, Any] | None

    def to_summary(self) -> dict[str, Any]:
        return {
            "feature_set_name": self.requested_feature_set_name,
            "trained_feature_set_name": self.trained_feature_set_name,
            "feature_set_applied": self.feature_set_applied,
            "allow_feature_set_mismatch": self.allow_feature_set_mismatch,
            "feature_set": None if self.feature_set is None else self.feature_set.to_dict(),
            "feature_engineering_manifest": self.transform_manifest,
        }


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def trained_feature_set_name_from_config(train_config: dict[str, Any]) -> str | None:
    """Extract feature-set provenance from train_config-style dictionaries."""
    top_level = _clean_optional(train_config.get("feature_set_name"))
    if top_level:
        return top_level

    training_data = train_config.get("training_data")
    if isinstance(training_data, dict):
        nested = _clean_optional(training_data.get("feature_set_name"))
        if nested:
            return nested

    feature_set = train_config.get("feature_set")
    if isinstance(feature_set, dict):
        nested = _clean_optional(feature_set.get("name"))
        if nested:
            return nested

    return None


def prepare_dataframe_for_feature_set_inference(
    df: pd.DataFrame,
    *,
    train_config: dict[str, Any],
    feature_set_name: str | None = None,
    allow_feature_set_mismatch: bool = False,
) -> FeatureSetInferenceResult:
    """Prepare an inference DataFrame according to an optional feature set.

    Existing behavior is preserved when ``feature_set_name`` is omitted: the input
    DataFrame is returned unchanged and downstream code validates the trained
    feature columns exactly as before.

    When a feature set is provided, AERIS verifies that it matches the model's
    recorded training feature set unless ``allow_feature_set_mismatch`` is true,
    applies the declared transforms, and returns the augmented DataFrame.
    """
    requested = _clean_optional(feature_set_name)
    trained = trained_feature_set_name_from_config(train_config)

    if requested is None:
        return FeatureSetInferenceResult(
            dataframe=df.copy(),
            requested_feature_set_name=None,
            trained_feature_set_name=trained,
            feature_set=None,
            feature_set_applied=False,
            allow_feature_set_mismatch=allow_feature_set_mismatch,
            transform_manifest=None,
        )

    feature_set = get_feature_set(requested)

    if trained and requested != trained and not allow_feature_set_mismatch:
        raise FeatureSetInferenceError(
            f"Feature-set mismatch: model was trained with feature set '{trained}', "
            f"but inference requested '{requested}'. Use --allow-feature-set-mismatch "
            "only for deliberate debugging or compatibility migration."
        )

    missing_source = [col for col in feature_set.required_source_columns if col not in df.columns]
    if missing_source:
        raise FeatureSetInferenceError(
            f"Input CSV is missing raw source columns required by feature set "
            f"'{feature_set.name}': {missing_source}"
        )

    augmented_df, transform_manifest = apply_feature_engineering(
        df,
        transforms=list(feature_set.transforms),
    )

    missing_final = [col for col in feature_set.columns if col not in augmented_df.columns]
    if missing_final:
        raise FeatureSetInferenceError(
            f"Input CSV is missing feature-set columns after transforms for "
            f"'{feature_set.name}': {missing_final}"
        )

    return FeatureSetInferenceResult(
        dataframe=augmented_df,
        requested_feature_set_name=feature_set.name,
        trained_feature_set_name=trained,
        feature_set=feature_set,
        feature_set_applied=True,
        allow_feature_set_mismatch=allow_feature_set_mismatch,
        transform_manifest=transform_manifest,
    )
