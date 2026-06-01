from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


_DEFAULT_MLP_PARAMS: dict[str, Any] = {
    "hidden_layer_sizes": (64, 64),
    "activation": "relu",
    "solver": "adam",
    "alpha": 1.0e-4,
    "batch_size": "auto",
    "learning_rate": "adaptive",
    "learning_rate_init": 1.0e-3,
    "max_iter": 500,
    "early_stopping": True,
    "validation_fraction": 0.15,
    "n_iter_no_change": 20,
    "tol": 1.0e-4,
}


def _normalize_hidden_layer_sizes(value: Any) -> tuple[int, ...]:
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("hidden_layer_sizes must contain positive integers")
        return (int(value),)
    if isinstance(value, (list, tuple)):
        out = tuple(int(v) for v in value)
        if not out or any(v <= 0 for v in out):
            raise ValueError("hidden_layer_sizes must contain positive integers")
        return out
    raise ValueError(
        "hidden_layer_sizes must be an int or a list/tuple of positive integers"
    )


def _merge_mlp_params(
    *,
    random_seed: int,
    model_params: dict[str, Any] | None,
) -> dict[str, Any]:
    params = dict(_DEFAULT_MLP_PARAMS)
    params.update(model_params or {})
    params["hidden_layer_sizes"] = _normalize_hidden_layer_sizes(
        params.get("hidden_layer_sizes", _DEFAULT_MLP_PARAMS["hidden_layer_sizes"])
    )
    params["random_state"] = int(params.get("random_state", random_seed))
    return params


def _build_pipeline(params: dict[str, Any]) -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("model", MLPRegressor(**params)),
        ]
    )


def build_neural_mlp(
    random_seed: int,
    model_params: dict[str, Any] | None = None,
) -> Pipeline:
    """Build a scaled sklearn MLPRegressor for scalar/tabular AERIS targets.

    This is intentionally a conservative neural baseline. It supports the same
    train/compare/tune/predict/promotion path as the existing sklearn models.
    It is not a field surrogate and it does not bypass any AERIS trust gate.
    """
    params = _merge_mlp_params(random_seed=random_seed, model_params=model_params)
    return _build_pipeline(params)


@dataclass(frozen=True)
class EnsembleFitDiagnostics:
    n_members: int
    member_random_states: list[int]


class NeuralMLPEnsembleRegressor(BaseEstimator, RegressorMixin):
    """Mean-prediction ensemble of scaled MLP regressors.

    The class follows the sklearn estimator interface and is deliberately small:
    - fit() trains independent MLP members with different random seeds,
    - predict() returns the ensemble mean,
    - predict_members() returns member predictions for uncertainty diagnostics,
    - estimators_ is exposed so AERIS confidence tooling can compute spread.

    This is heuristic epistemic uncertainty, not calibrated UQ. That blunt truth
    belongs in the report, not buried under neural-network confetti.
    """

    def __init__(
        self,
        n_members: int = 5,
        hidden_layer_sizes: tuple[int, ...] | list[int] | int = (64, 64),
        activation: str = "relu",
        solver: str = "adam",
        alpha: float = 1.0e-4,
        batch_size: str | int = "auto",
        learning_rate: str = "adaptive",
        learning_rate_init: float = 1.0e-3,
        max_iter: int = 500,
        early_stopping: bool = True,
        validation_fraction: float = 0.15,
        n_iter_no_change: int = 20,
        tol: float = 1.0e-4,
        random_state: int | None = None,
        suppress_convergence_warnings: bool = True,
    ) -> None:
        self.n_members = n_members
        self.hidden_layer_sizes = hidden_layer_sizes
        self.activation = activation
        self.solver = solver
        self.alpha = alpha
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.learning_rate_init = learning_rate_init
        self.max_iter = max_iter
        self.early_stopping = early_stopping
        self.validation_fraction = validation_fraction
        self.n_iter_no_change = n_iter_no_change
        self.tol = tol
        self.random_state = random_state
        self.suppress_convergence_warnings = suppress_convergence_warnings

    def _member_params(self, member_index: int) -> dict[str, Any]:
        if int(self.n_members) <= 0:
            raise ValueError("n_members must be a positive integer")

        base_seed = 0 if self.random_state is None else int(self.random_state)
        # Prime-ish stride to keep adjacent members separated while deterministic.
        member_seed = base_seed + 7919 * int(member_index)
        return {
            "hidden_layer_sizes": _normalize_hidden_layer_sizes(self.hidden_layer_sizes),
            "activation": self.activation,
            "solver": self.solver,
            "alpha": float(self.alpha),
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "learning_rate_init": float(self.learning_rate_init),
            "max_iter": int(self.max_iter),
            "early_stopping": bool(self.early_stopping),
            "validation_fraction": float(self.validation_fraction),
            "n_iter_no_change": int(self.n_iter_no_change),
            "tol": float(self.tol),
            "random_state": member_seed,
        }

    def fit(self, X: Any, y: Any) -> "NeuralMLPEnsembleRegressor":
        X_arr = np.asarray(X, dtype=float)
        y_arr = np.asarray(y, dtype=float)
        if y_arr.ndim == 1:
            y_arr = y_arr.reshape(-1, 1)

        self.estimators_: list[Pipeline] = []
        self.member_random_states_: list[int] = []

        warning_context = warnings.catch_warnings()
        with warning_context:
            if self.suppress_convergence_warnings:
                warnings.filterwarnings("ignore", category=ConvergenceWarning)
            for member_index in range(int(self.n_members)):
                params = self._member_params(member_index)
                self.member_random_states_.append(int(params["random_state"]))
                estimator = _build_pipeline(params)
                estimator.fit(X_arr, y_arr)
                self.estimators_.append(estimator)

        self.n_features_in_ = int(X_arr.shape[1])
        self.n_outputs_ = int(y_arr.shape[1])
        self.fit_diagnostics_ = EnsembleFitDiagnostics(
            n_members=int(self.n_members),
            member_random_states=list(self.member_random_states_),
        )
        return self

    def predict_members(self, X: Any) -> np.ndarray:
        if not hasattr(self, "estimators_"):
            raise ValueError("NeuralMLPEnsembleRegressor is not fitted yet")
        X_arr = np.asarray(X, dtype=float)
        preds: list[np.ndarray] = []
        for estimator in self.estimators_:
            pred = np.asarray(estimator.predict(X_arr), dtype=float)
            if pred.ndim == 1:
                pred = pred.reshape(-1, 1)
            preds.append(pred)
        return np.stack(preds, axis=0)

    def predict(self, X: Any) -> np.ndarray:
        members = self.predict_members(X)
        return np.mean(members, axis=0)


def build_neural_mlp_ensemble(
    random_seed: int,
    model_params: dict[str, Any] | None = None,
) -> NeuralMLPEnsembleRegressor:
    """Build an ensemble of scaled MLP regressors.

    Accepted model_params include the normal MLP hyperparameters plus
    n_members and suppress_convergence_warnings.
    """
    params = dict(_DEFAULT_MLP_PARAMS)
    params.update(model_params or {})
    n_members = int(params.pop("n_members", 5))
    suppress = bool(params.pop("suppress_convergence_warnings", True))
    params["hidden_layer_sizes"] = _normalize_hidden_layer_sizes(
        params.get("hidden_layer_sizes", _DEFAULT_MLP_PARAMS["hidden_layer_sizes"])
    )
    params["random_state"] = int(params.get("random_state", random_seed))

    return NeuralMLPEnsembleRegressor(
        n_members=n_members,
        suppress_convergence_warnings=suppress,
        **params,
    )
