"""Neural scalar surrogate backends for AERIS ML.

This package deliberately starts with tabular/scalar neural models. It does not
implement field prediction, GNNs, neural operators, CFD execution, or geometry
encoders. The goal is to plug neural regressors into the existing AERIS trust
chain: promoted data -> train/compare/tune -> diagnostics -> promotion ->
inference guard -> quality/confidence reports.
"""

from __future__ import annotations

from aeris.ml.neural.sklearn_mlp import (
    NeuralMLPEnsembleRegressor,
    build_neural_mlp,
    build_neural_mlp_ensemble,
)

__all__ = [
    "NeuralMLPEnsembleRegressor",
    "build_neural_mlp",
    "build_neural_mlp_ensemble",
]
