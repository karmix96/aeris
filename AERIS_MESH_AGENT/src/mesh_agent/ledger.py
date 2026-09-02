"""Flatten S6 atlas validation checkpoints into one tidy attempt table.

Every meshing attempt the atlas ever made is a row: which geometry, which
template, what happened, how good the result was and how long it took. This is
the observational dataset the whole paper rests on.

Read-only with respect to the atlas artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from .paths import ATLAS_ARTIFACTS

#: Production acceptance floor used by the atlas campaigns (S6 guide).
PRODUCTION_FLOOR = 0.10

OUTCOME_PASS = "PASS"
OUTCOME_SURFACE_BUILD_ERROR = "SURFACE_BUILD_ERROR"
OUTCOME_FAIL_FOLDED = "FAIL_FOLDED"
OUTCOME_FAIL_LOW_QUALITY = "FAIL_LOW_QUALITY"


def _classify(attempt: dict[str, Any]) -> str:
    """Three failure modes, not one.

    The atlas records a single ``FAIL`` state, but a mesh that folded (negative
    cell volumes) and a mesh that is perfectly valid yet sits below the quality
    floor are different events needing different responses. Separating them is a
    modelling decision, made here, once.
    """
    state = attempt.get("state")
    if state == OUTCOME_PASS:
        return OUTCOME_PASS
    if state == OUTCOME_SURFACE_BUILD_ERROR:
        return OUTCOME_SURFACE_BUILD_ERROR
    inverted = attempt.get("inverted_cells")
    if inverted is not None and int(inverted) > 0:
        return OUTCOME_FAIL_FOLDED
    return OUTCOME_FAIL_LOW_QUALITY


def _config_key(configuration: dict[str, Any]) -> str:
    """Identity of the meshing configuration an attempt was made under.

    Attempts are only comparable within one configuration: ``eps_e`` and the
    first-cell fraction are the very knobs the agent is allowed to choose, so
    pooling across them would silently mix action with outcome.
    """
    template_config = configuration.get("template_configuration") or {}
    return "|".join(
        str(value)
        for value in (
            configuration.get("eps_e", template_config.get("eps_e")),
            template_config.get("first_cell_fraction_characteristic"),
            template_config.get("normal_points"),
            template_config.get("volume_level"),
        )
    )


def _checkpoints() -> Iterator[Path]:
    yield from sorted(ATLAS_ARTIFACTS.glob("*/atlas_validation_checkpoint.json"))


def load_attempts() -> pd.DataFrame:
    """One row per meshing attempt, across every recorded atlas campaign."""
    records: list[dict[str, Any]] = []
    for path in _checkpoints():
        payload = json.loads(path.read_text())
        rows = payload.get("rows") or []
        if not rows:
            continue
        configuration = payload.get("configuration") or {}
        template_config = configuration.get("template_configuration") or {}
        campaign = path.parent.name
        for row in rows:
            attempts = row.get("attempts") or []
            for ordinal, attempt in enumerate(attempts, start=1):
                records.append(
                    {
                        "campaign": campaign,
                        "config_key": _config_key(configuration),
                        "eps_e": configuration.get("eps_e", template_config.get("eps_e")),
                        "first_cell_fraction": template_config.get(
                            "first_cell_fraction_characteristic"
                        ),
                        "normal_points": template_config.get("normal_points"),
                        "volume_level": template_config.get("volume_level"),
                        "preferred_quality": configuration.get("preferred_quality"),
                        "geometry_id": row.get("geometry_id"),
                        "geometry_index": row.get("geometry_index"),
                        "template_index": attempt.get("template_index"),
                        "attempt_ordinal": ordinal,
                        "n_attempts_for_geometry": len(attempts),
                        "state": attempt.get("state"),
                        "outcome": _classify(attempt),
                        "selected": bool(attempt.get("selected", False)),
                        "min_scaled_quality": attempt.get("min_scaled_quality"),
                        "surface_min_scaled_jacobian": attempt.get("surface_min_scaled_jacobian"),
                        "inverted_cells": attempt.get("inverted_cells"),
                        "min_volume": attempt.get("min_volume"),
                        "distance_rms": attempt.get("distance_rms"),
                        "elapsed_s": attempt.get("elapsed_s"),
                        "wall_error_m": attempt.get("wall_error_m"),
                        "interface_max_mismatch_m": attempt.get("interface_max_mismatch_m"),
                        "is_identity": attempt.get("template_index") == row.get("geometry_index"),
                        "row_state": row.get("state"),
                        "accepted_template_index": row.get("accepted_template_index"),
                        "accepted_min_scaled_quality": row.get("accepted_min_scaled_quality"),
                    }
                )
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise RuntimeError(f"no atlas checkpoints found under {ATLAS_ARTIFACTS}")
    return frame


def production_pool(frame: pd.DataFrame) -> pd.DataFrame:
    """The largest set of attempts sharing one meshing configuration.

    Campaigns that recorded no configuration (the early smoke runs) are dropped
    rather than assumed comparable.
    """
    complete = frame[frame["volume_level"].notna()]
    if complete.empty:
        raise RuntimeError("no campaign recorded a complete meshing configuration")
    counts = complete.groupby("config_key").size().sort_values(ascending=False)
    return complete[complete["config_key"] == counts.index[0]].copy()


def conflicts(pool: pd.DataFrame) -> pd.DataFrame:
    """Cells measured more than once within one configuration, disagreeing.

    The pipeline is meant to be deterministic, so a disagreement is evidence of
    a problem and must be surfaced, never averaged away.
    """
    keys = ["geometry_index", "template_index"]
    grouped = pool.groupby(keys)["outcome"].nunique()
    disagreeing = grouped[grouped > 1].index
    if len(disagreeing) == 0:
        return pool.iloc[0:0]
    mask = pool.set_index(keys).index.isin(disagreeing)
    return pool[mask].sort_values(keys)


def outcome_matrix(pool: pd.DataFrame) -> pd.DataFrame:
    """Deduplicated (geometry, template) -> outcome/quality observations."""
    ordered = pool.sort_values(["geometry_index", "template_index", "attempt_ordinal"])
    return ordered.drop_duplicates(subset=["geometry_index", "template_index"], keep="first")
