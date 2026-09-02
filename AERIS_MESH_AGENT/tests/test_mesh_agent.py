"""Invariants the paper's claims depend on.

These are not unit tests of convenience; each one guards a way the evaluation
could silently flatter itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh_agent import features as feature_builder
from mesh_agent.ledger import (
    OUTCOME_PASS,
    conflicts,
    load_attempts,
    outcome_matrix,
    production_pool,
)
from mesh_agent.outcome import fit_out_of_fold
from mesh_agent.policy import (
    accept_first_valid,
    atlas_baseline,
    ceiling_stopping,
    oracle,
    ranked_policy,
)

HEADLINE_CAMPAIGN = "development_atlas_qualified21_production_written_v3"


@pytest.fixture(scope="module")
def pool() -> pd.DataFrame:
    return production_pool(load_attempts())


@pytest.fixture(scope="module")
def recorded(pool: pd.DataFrame) -> pd.DataFrame:
    return pool[pool["campaign"] == HEADLINE_CAMPAIGN].reset_index(drop=True)


@pytest.fixture(scope="module")
def scores(pool: pd.DataFrame, recorded: pd.DataFrame) -> pd.Series:
    observations = outcome_matrix(pool).reset_index(drop=True)
    matrix, _ = feature_builder.build(observations, include_surface=False)
    predictions = fit_out_of_fold(matrix, observations, seed=0)
    series = predictions.score()
    series.index = pd.MultiIndex.from_arrays(
        [observations["geometry_index"], observations["template_index"]]
    )
    key = pd.MultiIndex.from_arrays([recorded["geometry_index"], recorded["template_index"]])
    return pd.Series(series.reindex(key).to_numpy(), index=recorded.index)


def test_pipeline_is_deterministic(pool: pd.DataFrame) -> None:
    """Cells measured twice must agree, or the ledger is not ground truth."""
    assert len(conflicts(pool)) == 0


def test_every_scored_cell_has_a_prediction(scores: pd.Series) -> None:
    """A NaN score would sort last and silently penalise that template."""
    assert scores.notna().all()


def test_learned_policy_cannot_invent_templates(recorded: pd.DataFrame, scores: pd.Series) -> None:
    """Restricted replay: a policy may only use cells whose outcome is recorded."""
    attempted = recorded.groupby("geometry_index")["template_index"].apply(set).to_dict()
    trace = ranked_policy(recorded, scores, name="t")
    for episode in trace.episodes:
        assert set(episode.order) <= attempted[episode.geometry_index]
        if episode.accepted_template is not None:
            assert episode.accepted_template in attempted[episode.geometry_index]


def test_no_policy_beats_the_oracle(recorded: pd.DataFrame, scores: pd.Series) -> None:
    """The oracle is the upper bound by construction; anything above it is a bug."""
    best = {e.geometry_index: e.accepted_quality for e in oracle(recorded).episodes}
    for stopping in (None, ceiling_stopping(), accept_first_valid()):
        for episode in ranked_policy(recorded, scores, name="t", stopping=stopping).episodes:
            if episode.accepted_quality is None:
                continue
            assert episode.accepted_quality <= best[episode.geometry_index] + 1e-12


def test_accepted_quality_never_below_the_floor(recorded: pd.DataFrame, scores: pd.Series) -> None:
    """A policy must not 'save' attempts by accepting a mesh the atlas would reject."""
    from mesh_agent.ledger import PRODUCTION_FLOOR

    for stopping in (None, ceiling_stopping(), accept_first_valid()):
        for episode in ranked_policy(recorded, scores, name="t", stopping=stopping).episodes:
            if episode.accepted_quality is not None:
                assert episode.accepted_quality >= PRODUCTION_FLOOR


def test_stopping_never_costs_more_attempts(recorded: pd.DataFrame, scores: pd.Series) -> None:
    """Adding a stopping rule can only end a search earlier, never later."""
    without = {e.geometry_index: e.attempts for e in ranked_policy(recorded, scores, name="t").episodes}
    for stopping in (ceiling_stopping(), accept_first_valid()):
        for episode in ranked_policy(recorded, scores, name="t", stopping=stopping).episodes:
            assert episode.attempts <= without[episode.geometry_index]


def test_out_of_fold_predictions_hold_out_their_own_geometry(pool: pd.DataFrame) -> None:
    """The split must group by target geometry, or the headline number is leakage."""
    observations = outcome_matrix(pool).reset_index(drop=True)
    matrix, _ = feature_builder.build(observations, include_surface=False)
    predictions = fit_out_of_fold(matrix, observations, seed=0)
    folds = pd.DataFrame(
        {"geometry": observations["geometry_index"], "fold": predictions.fold}
    )
    assert (folds.groupby("geometry")["fold"].nunique() == 1).all()


def test_atlas_baseline_matches_the_recorded_campaign(recorded: pd.DataFrame) -> None:
    """The baseline must be the campaign as it actually ran, not a reconstruction."""
    trace = atlas_baseline(recorded)
    assert sum(e.attempts for e in trace.episodes) == len(recorded)
    assert all(e.succeeded for e in trace.episodes)


def test_hold_out_set_is_never_used() -> None:
    """ADR-0011: the hold-out is run once, after freeze. Not from this package.

    Naming it in a comment is fine and is in fact how the rule is documented.
    What must never appear is the name as live code — a string the package could
    actually pass to the sampler — so comments are tokenised away before looking.
    """
    import io
    import tokenize

    package = Path(__file__).resolve().parents[1]
    hold_out = "round_c" + "_lhs10_seed42"  # split so this test is not its own hit
    offenders: list[str] = []
    for directory in ("src", "experiments", "paper"):
        for path in (package / directory).rglob("*.py"):
            with io.open(path, encoding="utf-8") as handle:
                for token in tokenize.generate_tokens(handle.readline):
                    if token.type == tokenize.COMMENT:
                        continue
                    if hold_out in token.string:
                        offenders.append(f"{path.name}:{token.start[0]}")
    assert offenders == [], offenders
