"""
Model registry for AERIS tabular ML baselines.

Responsibilities:
    - Centralize supported model types
    - Provide consistent model construction
    - Expose explainability policy metadata
    - Keep train/compare logic free of model-specific branching

Notes:
    - Add new model families here, not via scattered if/else blocks.
    - External libraries (xgboost/lightgbm/catboost) can be added later
      behind this same registry seam without changing train/compare flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import ElasticNet, LinearRegression, Ridge
from sklearn.multioutput import MultiOutputRegressor

ExplainabilityArtifactType = Literal["coefficients", "feature_importances", "none"]


@dataclass(frozen=True)
class ModelSpec:
    """Registry entry describing one supported model family."""

    model_type: str
    display_name: str
    family_name: str
    explainability_artifact_type: ExplainabilityArtifactType
    builder: Callable[[int, dict[str, Any] | None], object]
    wrapped_per_target: bool


def _merge_params(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(defaults)
    params.update(overrides or {})
    return params


def _build_linear_regression(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params({}, model_params)
    return LinearRegression(**params)


def _build_ridge(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params({"alpha": 1.0}, model_params)
    return Ridge(**params)


def _build_elastic_net(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    # ElasticNet is single-target in sklearn.
    params = _merge_params(
        {
            "alpha": 1.0,
            "l1_ratio": 0.5,
            "random_state": random_seed,
            "max_iter": 10000,
        },
        model_params,
    )
    return MultiOutputRegressor(ElasticNet(**params))


def _build_random_forest(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params(
        {
            "n_estimators": 300,
            "random_state": random_seed,
            "n_jobs": -1,
        },
        model_params,
    )
    return RandomForestRegressor(**params)


def _build_extra_trees(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params(
        {
            "n_estimators": 300,
            "random_state": random_seed,
            "n_jobs": -1,
        },
        model_params,
    )
    return ExtraTreesRegressor(**params)


def _build_gradient_boosting(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params(
        {
            "random_state": random_seed,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "max_depth": 3,
        },
        model_params,
    )
    return MultiOutputRegressor(GradientBoostingRegressor(**params))


def _build_hist_gradient_boosting(
    random_seed: int, model_params: dict[str, Any] | None = None
) -> object:
    params = _merge_params(
        {
            "random_state": random_seed,
            "learning_rate": 0.05,
            "max_iter": 300,
            "max_depth": None,
        },
        model_params,
    )
    return MultiOutputRegressor(HistGradientBoostingRegressor(**params))


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "linear_regression": ModelSpec(
        model_type="linear_regression",
        display_name="Linear Regression",
        family_name="linear_model",
        explainability_artifact_type="coefficients",
        builder=_build_linear_regression,
        wrapped_per_target=False,
    ),
    "ridge": ModelSpec(
        model_type="ridge",
        display_name="Ridge Regression",
        family_name="linear_regularized",
        explainability_artifact_type="coefficients",
        builder=_build_ridge,
        wrapped_per_target=False,
    ),
    "elastic_net": ModelSpec(
        model_type="elastic_net",
        display_name="Elastic Net",
        family_name="linear_regularized",
        explainability_artifact_type="coefficients",
        builder=_build_elastic_net,
        wrapped_per_target=True,
    ),
    "random_forest": ModelSpec(
        model_type="random_forest",
        display_name="Random Forest",
        family_name="tree_ensemble",
        explainability_artifact_type="feature_importances",
        builder=_build_random_forest,
        wrapped_per_target=False,
    ),
    "extra_trees": ModelSpec(
        model_type="extra_trees",
        display_name="Extra Trees",
        family_name="tree_ensemble",
        explainability_artifact_type="feature_importances",
        builder=_build_extra_trees,
        wrapped_per_target=False,
    ),
    "gradient_boosting": ModelSpec(
        model_type="gradient_boosting",
        display_name="Gradient Boosting",
        family_name="tree_boosting",
        explainability_artifact_type="feature_importances",
        builder=_build_gradient_boosting,
        wrapped_per_target=True,
    ),
    "hist_gradient_boosting": ModelSpec(
        model_type="hist_gradient_boosting",
        display_name="Hist Gradient Boosting",
        family_name="tree_boosting",
        explainability_artifact_type="none",
        builder=_build_hist_gradient_boosting,
        wrapped_per_target=True,
    ),
}


def get_model_spec(model_type: str) -> ModelSpec:
    """Return the registry spec for a supported model type."""
    try:
        return MODEL_REGISTRY[model_type]
    except KeyError as exc:
        supported = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(
            f"Unsupported model_type '{model_type}'. Supported: {supported}"
        ) from exc


def build_model(
    model_type: str,
    random_seed: int,
    model_params: dict[str, Any] | None = None,
) -> object:
    """Construct a model instance from the registry."""
    return get_model_spec(model_type).builder(random_seed, model_params)


def list_model_types() -> list[str]:
    """Return sorted supported model identifiers."""
    return sorted(MODEL_REGISTRY)