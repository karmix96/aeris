"""Predicting what a meshing attempt will do, before making it.

Two heads, because the four outcomes are not one ordered scale:

* a classifier over {PASS, FAIL_FOLDED, FAIL_LOW_QUALITY, SURFACE_BUILD_ERROR};
* a regressor for ``min_scaled_quality``, which only exists when a volume was
  actually written (a surface-build error has no quality at all, and imputing
  one would invent data).

Both are fitted out-of-fold with a grouped split on the *target* geometry, so a
geometry never informs its own prediction. That is the only split that answers
the question the paper asks: a BWB the atlas has never seen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

from .ledger import OUTCOME_PASS, OUTCOME_SURFACE_BUILD_ERROR

RANDOM_STATE = 0


def _classifier() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.06,
        max_leaf_nodes=15,
        min_samples_leaf=8,
        l2_regularization=1.0,
        random_state=RANDOM_STATE,
    )


def _regressor() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.06,
        max_leaf_nodes=15,
        min_samples_leaf=8,
        l2_regularization=1.0,
        random_state=RANDOM_STATE,
    )


@dataclass
class OutOfFoldPredictions:
    """Everything downstream policies are allowed to see."""

    probability: pd.DataFrame          # class probabilities, columns = class names
    quality: pd.Series                 # predicted min_scaled_quality
    fold: pd.Series                    # which fold each row was held out in
    classes: list[str]

    @property
    def p_pass(self) -> pd.Series:
        return self.probability[OUTCOME_PASS]

    def score(self) -> pd.Series:
        """Ranking score: expected quality, discounted by the risk of no mesh.

        A template that usually yields excellent quality but occasionally fails
        to build a surface at all is worse than its quality alone suggests, so
        the surface-build-error probability multiplies it down.
        """
        buildable = 1.0 - self.probability.get(
            OUTCOME_SURFACE_BUILD_ERROR, pd.Series(0.0, index=self.quality.index)
        )
        return buildable * self.quality


def _assign_folds(groups: np.ndarray, n_splits: int, seed: int | None) -> np.ndarray:
    """Which fold each row is held out in.

    With ``seed=None`` this is sklearn's deterministic GroupKFold. With a seed,
    geometries are shuffled before being dealt into folds, so the whole
    evaluation can be repeated and reported with a spread rather than as a
    single lucky partition.
    """
    if seed is None:
        assignment = np.empty(len(groups), dtype=int)
        splitter = GroupKFold(n_splits=n_splits)
        for index, (_train, test) in enumerate(splitter.split(groups, groups, groups)):
            assignment[test] = index
        return assignment

    unique = np.unique(groups)
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(unique)
    fold_of_group = {group: position % n_splits for position, group in enumerate(shuffled)}
    return np.array([fold_of_group[g] for g in groups], dtype=int)


def fit_out_of_fold(
    features: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    n_splits: int = 5,
    seed: int | None = None,
) -> OutOfFoldPredictions:
    """Grouped out-of-fold predictions for every observed (geometry, template)."""
    groups = observations["geometry_index"].to_numpy()
    labels = observations["outcome"].to_numpy()
    quality_truth = pd.to_numeric(observations["min_scaled_quality"], errors="coerce")

    classes = sorted(set(labels))
    probability = pd.DataFrame(
        np.nan, index=observations.index, columns=classes, dtype=float
    )
    quality = pd.Series(np.nan, index=observations.index, dtype=float)
    fold = pd.Series(-1, index=observations.index, dtype=int)

    n_splits = min(n_splits, len(np.unique(groups)))
    assignment = _assign_folds(groups, n_splits, seed)
    matrix = features.to_numpy(dtype=float)

    for index in range(n_splits):
        test = np.flatnonzero(assignment == index)
        train = np.flatnonzero(assignment != index)
        if test.size == 0 or train.size == 0:
            continue
        fold.iloc[test] = index

        classifier = _classifier().fit(matrix[train], labels[train])
        predicted = classifier.predict_proba(matrix[test])
        for position, name in enumerate(classifier.classes_):
            probability.iloc[test, probability.columns.get_loc(name)] = predicted[:, position]

        # Quality is only defined where a volume was written.
        defined = train[np.isfinite(quality_truth.to_numpy()[train])]
        regressor = _regressor().fit(matrix[defined], quality_truth.to_numpy()[defined])
        quality.iloc[test] = regressor.predict(matrix[test])

    probability = probability.fillna(0.0)
    return OutOfFoldPredictions(
        probability=probability, quality=quality, fold=fold, classes=classes
    )
