"""
PATCH 03 — src/aeris/ml/model_registry.py
===========================================
Adds LightGBM, XGBoost, CatBoost, and TabPFN to the model registry.

All four are guarded with try/except imports — if the library is not
installed, building that model type raises ImportError with a clear pip
install message. No other code changes: train/compare/tune/promote/predict
are unaware of the addition.

HOW TO APPLY
------------
Replace src/aeris/ml/model_registry.py entirely with this file.

INSTALL NEW DEPENDENCIES
-------------------------
pip install lightgbm xgboost catboost tabpfn

TabPFN note: requires Python >=3.9, torch >=2.0. On machines without GPU
it runs on CPU and is fast for n_train < 10,000.
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
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from aeris.ml.neural import build_neural_mlp, build_neural_mlp_ensemble

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


# ── Original sklearn builders (unchanged) ────────────────────────────────────

def _build_linear_regression(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params({}, model_params)
    return Pipeline([("scaler", StandardScaler()), ("model", LinearRegression(**params))])


def _build_ridge(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params({"alpha": 1.0}, model_params)
    return Pipeline([("scaler", StandardScaler()), ("model", Ridge(**params))])


def _build_elastic_net(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params(
        {"alpha": 1.0, "l1_ratio": 0.5, "random_state": random_seed, "max_iter": 10000},
        model_params,
    )
    return Pipeline([("scaler", StandardScaler()), ("model", MultiOutputRegressor(ElasticNet(**params)))])


def _build_random_forest(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params({"n_estimators": 300, "random_state": random_seed, "n_jobs": -1}, model_params)
    return RandomForestRegressor(**params)


def _build_extra_trees(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params({"n_estimators": 300, "random_state": random_seed, "n_jobs": -1}, model_params)
    return ExtraTreesRegressor(**params)


def _build_gradient_boosting(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params(
        {"random_state": random_seed, "n_estimators": 200, "learning_rate": 0.05, "max_depth": 3},
        model_params,
    )
    return MultiOutputRegressor(GradientBoostingRegressor(**params))


def _build_hist_gradient_boosting(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    params = _merge_params(
        {"random_state": random_seed, "learning_rate": 0.05, "max_iter": 300, "max_depth": None},
        model_params,
    )
    return MultiOutputRegressor(HistGradientBoostingRegressor(**params))


# ── NEW: LightGBM ─────────────────────────────────────────────────────────────

def _build_lightgbm(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    """
    LightGBM gradient boosting via MultiOutputRegressor.

    Defaults tuned for small-to-medium aero surrogate datasets (1k–100k rows).
    Key advantages over sklearn GBM:
    - 10–100x faster training (histogram algorithm, parallel leaf-wise growth)
    - DART boosting (drop trees, reduces overfitting on small datasets)
    - Native categorical support (set categorical_feature in model_params)
    - GPU support: add device='gpu' to model_params

    Override any param via --model-params-json:
        {"n_estimators": 1000, "boosting_type": "dart", "num_leaves": 127}
    """
    try:
        from lightgbm import LGBMRegressor
    except ImportError as exc:
        raise ImportError(
            "LightGBM is not installed. Run: pip install lightgbm"
        ) from exc

    params = _merge_params(
        {
            "n_estimators": 500,
            "learning_rate": 0.03,
            "num_leaves": 63,
            "min_child_samples": 10,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
            "random_state": random_seed,
            "n_jobs": -1,
            "verbose": -1,
        },
        model_params,
    )
    # LightGBM does not natively support multi-output regression; wrap it.
    return MultiOutputRegressor(LGBMRegressor(**params))


def _build_lightgbm_dart(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    """
    LightGBM with DART boosting — best for small datasets (<5k rows) where
    standard GBM overfits. DART randomly drops trees during training.
    Slower than standard LightGBM but more regularised.
    """
    try:
        from lightgbm import LGBMRegressor
    except ImportError as exc:
        raise ImportError(
            "LightGBM is not installed. Run: pip install lightgbm"
        ) from exc

    params = _merge_params(
        {
            "boosting_type": "dart",
            "n_estimators": 400,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 5,
            "drop_rate": 0.1,
            "random_state": random_seed,
            "n_jobs": -1,
            "verbose": -1,
        },
        model_params,
    )
    return MultiOutputRegressor(LGBMRegressor(**params))


# ── NEW: XGBoost ──────────────────────────────────────────────────────────────

def _build_xgboost(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    """
    XGBoost gradient boosting via MultiOutputRegressor.

    Key advantages over sklearn GBM:
    - Regularised (L1 + L2) objective with built-in pruning
    - GPU support: add tree_method='gpu_hist' to model_params
    - Handles missing values natively
    - Early stopping support via eval_set in fit() (not used here;
      override with model_params if needed)

    Override any param via --model-params-json:
        {"n_estimators": 1000, "max_depth": 6, "tree_method": "gpu_hist"}
    """
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise ImportError(
            "XGBoost is not installed. Run: pip install xgboost"
        ) from exc

    params = _merge_params(
        {
            "n_estimators": 500,
            "learning_rate": 0.03,
            "max_depth": 6,
            "min_child_weight": 3,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "gamma": 0.0,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
            "random_state": random_seed,
            "n_jobs": -1,
            "tree_method": "hist",      # fast histogram; switch to gpu_hist for GPU
            "verbosity": 0,
        },
        model_params,
    )
    return MultiOutputRegressor(XGBRegressor(**params))


# ── NEW: CatBoost ─────────────────────────────────────────────────────────────

def _build_catboost(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    """
    CatBoost gradient boosting.

    Key advantages:
    - Ordered boosting (reduces overfit on small datasets via target leakage prevention)
    - Native multi-output regression support (no MultiOutputRegressor wrapper needed)
    - Handles categorical columns natively (declare via cat_features in model_params)
    - GPU support: add task_type='GPU' to model_params

    CatBoost natively supports multi-output so wrapped_per_target=False.

    Override any param via --model-params-json:
        {"iterations": 1000, "depth": 8, "task_type": "GPU"}
    """
    try:
        from catboost import CatBoostRegressor
    except ImportError as exc:
        raise ImportError(
            "CatBoost is not installed. Run: pip install catboost"
        ) from exc

    params = _merge_params(
        {
            "iterations": 500,
            "learning_rate": 0.03,
            "depth": 6,
            "l2_leaf_reg": 3.0,
            "random_seed": random_seed,
            "thread_count": -1,
            "verbose": False,
            "loss_function": "MultiRMSE",  # native multi-output loss
        },
        model_params,
    )
    return CatBoostRegressor(**params)


# ── NEW: TabPFN ──────────────────────────────────────────────────────────────

def _build_tabpfn(random_seed: int, model_params: dict[str, Any] | None = None) -> object:
    """
    TabPFN — in-context learning transformer pretrained on synthetic tabular data.

    WHEN TO USE:
    - Dataset has fewer than ~10,000 training rows
    - You want a strong baseline with zero hyperparameter tuning
    - You do NOT want to wait for Optuna trials

    WHEN NOT TO USE:
    - Dataset has > 10,000 rows (TabPFN truncates or errors)
    - You need GPU training (TabPFN runs on CPU by default)
    - You need feature importance

    TabPFN wraps in MultiOutputRegressor because it is single-target.

    Override: {"device": "cpu", "N_ensemble_configurations": 16}
    """
    try:
        from tabpfn import TabPFNRegressor
    except ImportError as exc:
        raise ImportError(
            "TabPFN is not installed. Run: pip install tabpfn\n"
            "Requires Python>=3.9 and torch>=2.0."
        ) from exc

    params = _merge_params(
        {
            "device": "cpu",
            "N_ensemble_configurations": 16,  # more = better but slower
        },
        model_params,
    )
    # TabPFN ignores random_seed in its constructor; seed is set via torch.manual_seed
    # before fit() in real usage. We store it for logging only.
    _ = random_seed
    return MultiOutputRegressor(TabPFNRegressor(**params))


# ── Model registry (original entries + new entries) ───────────────────────────

MODEL_REGISTRY: dict[str, ModelSpec] = {
    # ── Original sklearn models (unchanged) ──────────────────────────────────
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
    "neural_mlp": ModelSpec(
        model_type="neural_mlp",
        display_name="Neural MLP",
        family_name="neural_tabular",
        explainability_artifact_type="none",
        builder=build_neural_mlp,
        wrapped_per_target=False,
    ),
    "neural_mlp_ensemble": ModelSpec(
        model_type="neural_mlp_ensemble",
        display_name="Neural MLP Ensemble",
        family_name="neural_tabular_ensemble",
        explainability_artifact_type="none",
        builder=build_neural_mlp_ensemble,
        wrapped_per_target=False,
    ),
    # ── NEW: gradient boosting libraries ─────────────────────────────────────
    "lightgbm": ModelSpec(
        model_type="lightgbm",
        display_name="LightGBM",
        family_name="tree_boosting_fast",
        explainability_artifact_type="feature_importances",
        builder=_build_lightgbm,
        wrapped_per_target=True,   # MultiOutputRegressor wraps single-target LGBM
    ),
    "lightgbm_dart": ModelSpec(
        model_type="lightgbm_dart",
        display_name="LightGBM DART",
        family_name="tree_boosting_fast",
        explainability_artifact_type="feature_importances",
        builder=_build_lightgbm_dart,
        wrapped_per_target=True,
    ),
    "xgboost": ModelSpec(
        model_type="xgboost",
        display_name="XGBoost",
        family_name="tree_boosting_regularized",
        explainability_artifact_type="feature_importances",
        builder=_build_xgboost,
        wrapped_per_target=True,
    ),
    "catboost": ModelSpec(
        model_type="catboost",
        display_name="CatBoost",
        family_name="tree_boosting_ordered",
        explainability_artifact_type="feature_importances",
        builder=_build_catboost,
        wrapped_per_target=False,  # native multi-output, no wrapper
    ),
    "tabpfn": ModelSpec(
        model_type="tabpfn",
        display_name="TabPFN (<=10k rows)",
        family_name="transformer_tabular",
        explainability_artifact_type="none",
        builder=_build_tabpfn,
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
