"""Meshing policies, and the atlas rule they are measured against.

The atlas acceptance rule, recovered from the campaign records, has two
thresholds rather than one:

* accept immediately at ``min_scaled_quality >= preferred_quality`` (0.15);
* otherwise keep trying, and fall back at the end to the best result at or
  above the production floor (0.10).

The second half has no stopping rule, and that is where most of the avoidable
cost sits: geometry ``lhs100_seed42_095`` scanned all 21 templates and then
accepted its own first result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from .ledger import OUTCOME_PASS, PRODUCTION_FLOOR

PREFERRED_QUALITY = 0.15


@dataclass
class Episode:
    """What one policy did on one geometry."""

    geometry_index: int
    order: list[int]
    attempts: int
    seconds: float
    accepted_template: int | None
    accepted_quality: float | None
    reached_preferred: bool
    stopped_early: bool = False

    @property
    def succeeded(self) -> bool:
        return self.accepted_template is not None


@dataclass
class Trace:
    """Per-geometry outcomes for one policy, plus the aggregate the paper reports."""

    name: str
    episodes: list[Episode] = field(default_factory=list)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "policy": self.name,
                    "geometry_index": e.geometry_index,
                    "attempts": e.attempts,
                    "seconds": e.seconds,
                    "accepted_template": e.accepted_template,
                    "accepted_quality": e.accepted_quality,
                    "reached_preferred": e.reached_preferred,
                    "succeeded": e.succeeded,
                    "stopped_early": e.stopped_early,
                }
                for e in self.episodes
            ]
        )

    def summary(self) -> dict[str, float]:
        frame = self.frame()
        return {
            "policy": self.name,
            "geometries": float(len(frame)),
            "total_attempts": float(frame["attempts"].sum()),
            "total_seconds": float(frame["seconds"].sum()),
            "mean_attempts": float(frame["attempts"].mean()),
            "max_attempts": float(frame["attempts"].max()),
            "success_rate": float(frame["succeeded"].mean()),
            "first_attempt_success": float((frame["attempts"] == 1).mean()),
            "mean_accepted_quality": float(frame["accepted_quality"].mean(skipna=True)),
            "reached_preferred_rate": float(frame["reached_preferred"].mean()),
        }


def _run_order(
    geometry_index: int,
    order: Sequence[int],
    quality_of: dict[int, float | None],
    outcome_of: dict[int, str],
    elapsed_of: dict[int, float] | None = None,
    *,
    stop_after: Callable[[int, float | None], bool] | None = None,
) -> Episode:
    """Walk an ordering under the atlas acceptance rule.

    ``stop_after(position, best_quality_so_far)`` may end the search early; that
    is the only difference between the baseline rule and a policy with a
    learned stopping rule.
    """
    best_template: int | None = None
    best_quality: float | None = None
    attempts = 0
    seconds = 0.0
    reached_preferred = False
    stopped_early = False
    elapsed_of = elapsed_of or {}

    for position, template in enumerate(order, start=1):
        attempts = position
        # Outcomes cost very different amounts of time: a surface-build error is
        # nearly free, a successful extrusion is not. Counting attempts alone
        # would mis-rank a policy that fails fast.
        seconds += float(elapsed_of.get(template, 0.0) or 0.0)
        outcome = outcome_of.get(template)
        quality = quality_of.get(template)
        if outcome == OUTCOME_PASS and quality is not None:
            if best_quality is None or quality > best_quality:
                best_quality, best_template = quality, template
            if quality >= PREFERRED_QUALITY:
                reached_preferred = True
                break
        if stop_after is not None and stop_after(position, best_quality):
            stopped_early = True
            break

    return Episode(
        geometry_index=geometry_index,
        order=list(order),
        attempts=attempts,
        seconds=seconds,
        accepted_template=best_template,
        accepted_quality=best_quality,
        reached_preferred=reached_preferred,
        stopped_early=stopped_early,
    )


def atlas_baseline(recorded: pd.DataFrame) -> Trace:
    """The policy actually run, replayed from the ledger."""
    trace = Trace("atlas (as run)")
    for geometry_index, group in recorded.groupby("geometry_index"):
        group = group.sort_values("attempt_ordinal")
        passes = group[group["outcome"] == OUTCOME_PASS]
        quality = pd.to_numeric(passes["min_scaled_quality"], errors="coerce")
        best = quality.max() if len(quality) else np.nan
        best_template = (
            int(passes.loc[quality.idxmax(), "template_index"]) if len(quality) and quality.notna().any() else None
        )
        trace.episodes.append(
            Episode(
                geometry_index=int(geometry_index),
                order=[int(t) for t in group["template_index"]],
                attempts=int(len(group)),
                seconds=float(pd.to_numeric(group["elapsed_s"], errors="coerce").fillna(0).sum()),
                accepted_template=best_template,
                accepted_quality=float(best) if best == best else None,
                reached_preferred=bool(best >= PREFERRED_QUALITY) if best == best else False,
            )
        )
    return trace


def ranked_policy(
    recorded: pd.DataFrame,
    score: pd.Series,
    *,
    name: str,
    stopping: Callable[[int, float | None, np.ndarray], bool] | None = None,
) -> Trace:
    """Try templates in descending predicted score.

    Restricted to the templates the atlas actually attempted for that geometry:
    those are the only cells whose true outcome is known. This makes the result
    a *reordering* gain and therefore a lower bound — a policy allowed to reach
    into the unobserved part of the matrix can only do better.
    """
    trace = Trace(name)
    for geometry_index, group in recorded.groupby("geometry_index"):
        ordered = group.assign(score=score.reindex(group.index)).sort_values(
            "score", ascending=False
        )
        quality_of = {
            int(row.template_index): (
                float(row.min_scaled_quality)
                if pd.notna(row.min_scaled_quality)
                else None
            )
            for row in ordered.itertuples()
        }
        outcome_of = {int(row.template_index): row.outcome for row in ordered.itertuples()}
        elapsed_of = {
            int(row.template_index): (
                float(row.elapsed_s) if pd.notna(row.elapsed_s) else 0.0
            )
            for row in ordered.itertuples()
        }
        remaining = ordered["score"].to_numpy(dtype=float)

        stop_after = None
        if stopping is not None:
            def stop_after(position: int, best: float | None, _r=remaining) -> bool:
                return stopping(position, best, _r)

        trace.episodes.append(
            _run_order(
                int(geometry_index),
                [int(t) for t in ordered["template_index"]],
                quality_of,
                outcome_of,
                elapsed_of,
                stop_after=stop_after,
            )
        )
    return trace


def ceiling_stopping(margin: float = 0.0) -> Callable[[int, float | None, np.ndarray], bool]:
    """Stop when no remaining candidate is predicted to beat what we already hold.

    This is the rule that geometry 095 needed: its first attempt was the best of
    all twenty-one, and nothing in the loop was able to say so.

    Note the comparison is between a *predicted* score and a *measured* quality.
    The score is an expected quality discounted by the probability that no
    surface builds, so the two are on the same scale but not the same footing;
    the discount makes the rule slightly conservative, which is the direction an
    acceptance decision should err in.
    """

    def rule(position: int, best: float | None, remaining: np.ndarray) -> bool:
        if best is None or best < PRODUCTION_FLOOR:
            return False
        future = remaining[position:]
        if future.size == 0:
            return True
        return bool(future.max() <= best + margin)

    return rule


def oracle(recorded: pd.DataFrame) -> Trace:
    """Perfect foresight: one attempt, the best template available."""
    trace = Trace("oracle (upper bound)")
    for geometry_index, group in recorded.groupby("geometry_index"):
        passes = group[group["outcome"] == OUTCOME_PASS]
        quality = pd.to_numeric(passes["min_scaled_quality"], errors="coerce")
        if len(quality) and quality.notna().any():
            best_quality = float(quality.max())
            best_template = int(passes.loc[quality.idxmax(), "template_index"])
        else:
            best_quality, best_template = None, None
        trace.episodes.append(
            Episode(
                geometry_index=int(geometry_index),
                order=[best_template] if best_template is not None else [],
                attempts=1,
                seconds=float(
                    pd.to_numeric(
                        group.loc[group["template_index"] == best_template, "elapsed_s"],
                        errors="coerce",
                    ).fillna(0).sum()
                ) if best_template is not None else 0.0,
                accepted_template=best_template,
                accepted_quality=best_quality,
                reached_preferred=bool(
                    best_quality is not None and best_quality >= PREFERRED_QUALITY
                ),
            )
        )
    return trace


def accept_first_valid() -> Callable[[int, float | None, np.ndarray], bool]:
    """Stop at the first mesh that clears the production floor.

    The cheapest possible stopping rule: no model, no prediction, just a
    decision to stop bargaining for quality once a usable mesh exists. It is the
    ablation that says how much of any saving is really machine learning and how
    much is simply the absence of a stopping rule in the incumbent.
    """

    def rule(position: int, best: float | None, remaining: np.ndarray) -> bool:
        return best is not None and best >= PRODUCTION_FLOOR

    return rule


def recorded_order_policy(
    recorded: pd.DataFrame,
    *,
    name: str,
    stopping: Callable[[int, float | None, np.ndarray], bool] | None = None,
    score: pd.Series | None = None,
) -> Trace:
    """The atlas's own nearest-template-first ordering, with a different stopping rule.

    `development_atlas.py` picks candidates by ``argsort(distances[index])``, so
    the incumbent already routes by proximity in normalised design space. Holding
    that ordering fixed and changing only when to stop isolates the two halves of
    the problem.
    """
    trace = Trace(name)
    for geometry_index, group in recorded.groupby("geometry_index"):
        ordered = group.sort_values("attempt_ordinal")
        quality_of = {
            int(row.template_index): (
                float(row.min_scaled_quality) if pd.notna(row.min_scaled_quality) else None
            )
            for row in ordered.itertuples()
        }
        outcome_of = {int(row.template_index): row.outcome for row in ordered.itertuples()}
        elapsed_of = {
            int(row.template_index): (
                float(row.elapsed_s) if pd.notna(row.elapsed_s) else 0.0
            )
            for row in ordered.itertuples()
        }
        # A stopping rule that reasons about what is still to come needs the
        # model's view of the remaining candidates, even when the *ordering* is
        # left to the incumbent. That separation is the point of this policy.
        if score is None:
            remaining = np.zeros(len(ordered))
        else:
            remaining = score.reindex(ordered.index).to_numpy(dtype=float)

        stop_after = None
        if stopping is not None:
            def stop_after(position: int, best: float | None, _r=remaining) -> bool:
                return stopping(position, best, _r)

        trace.episodes.append(
            _run_order(
                int(geometry_index),
                [int(t) for t in ordered["template_index"]],
                quality_of,
                outcome_of,
                elapsed_of,
                stop_after=stop_after,
            )
        )
    return trace
