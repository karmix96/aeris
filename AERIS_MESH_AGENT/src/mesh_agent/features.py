"""Features available to the agent *before* it commits to a meshing attempt.

Two deliberately separated feature sets:

``design``
    The 20 sampled design variables of the target and of the template, their
    difference, and a normalised design-space distance. All of this is free —
    it exists before any geometry, surface or volume is built.

``design+surface``
    Adds quantities that require the cheap steps (geometry realisation and the
    bounded surface deformation) but not the expensive one (hyperbolic
    extrusion): realised planform metrics and the recorded deformation
    ``distance_rms``.

Keeping them apart is the experiment: it says whether paying for the cheap
build-up buys enough routing accuracy to be worth it.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import ATLAS_ARTIFACTS, DEVELOPMENT_SET, STUDY_SHARED

#: Realised metrics worth having: they capture size and slenderness, which the
#: raw sampled ratios only imply.
SUMMARY_METRICS = (
    "semi_span_m",
    "approx_area_m2",
    "aspect_ratio_pygeo",
    "volume_pygeo_m3",
    "wetted_area_pygeo_m2",
)
SUMMARY_PLANFORM = ("c2_m", "c3_m", "c4_m", "b1_m", "b2_m", "b3_m")


@lru_cache(maxsize=1)
def design_matrix() -> tuple[np.ndarray, list[str]]:
    """The development set's design matrix, regenerated from the sampler.

    Regenerating rather than reading a CSV keeps the sampler as the single
    source of truth, exactly as `shared.geometry_sets` intends.
    """
    for path in (STUDY_SHARED, STUDY_SHARED.parents[1] / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from shared.geometry_sets import design_matrix as _design_matrix

    matrix, names = _design_matrix(DEVELOPMENT_SET)
    return np.asarray(matrix, dtype=float), list(names)


@lru_cache(maxsize=1)
def geometry_summaries() -> pd.DataFrame:
    """Realised per-geometry metrics, read from the atlas geometry summaries.

    Missing summaries are left as NaN rather than imputed; the caller decides.
    """
    roots = sorted(ATLAS_ARTIFACTS.glob("*/_geometry"))
    records: dict[int, dict[str, float]] = {}
    for root in roots:
        for directory in sorted(root.iterdir()):
            summary = directory / "geometry_summary.json"
            if not summary.is_file():
                continue
            index = int(directory.name.rsplit("_", 1)[-1])
            if index in records:
                continue
            payload = json.loads(summary.read_text())
            metrics = payload.get("metrics") or {}
            planform = payload.get("sampled_planform") or {}
            row = {f"metric_{k}": metrics.get(k) for k in SUMMARY_METRICS}
            row.update({f"planform_{k}": planform.get(k) for k in SUMMARY_PLANFORM})
            records[index] = row
    frame = pd.DataFrame.from_dict(records, orient="index").sort_index()
    frame.index.name = "geometry_index"
    return frame


def _normalised(matrix: np.ndarray) -> np.ndarray:
    span = matrix.max(axis=0) - matrix.min(axis=0)
    span[span == 0] = 1.0
    return (matrix - matrix.min(axis=0)) / span


def build(observations: pd.DataFrame, *, include_surface: bool) -> tuple[pd.DataFrame, list[str]]:
    """Feature frame aligned to ``observations`` rows.

    ``observations`` needs ``geometry_index`` and ``template_index`` columns.
    """
    matrix, names = design_matrix()
    normalised = _normalised(matrix)

    target = observations["geometry_index"].to_numpy(dtype=int)
    template = observations["template_index"].to_numpy(dtype=int)

    columns: dict[str, np.ndarray] = {}
    for position, name in enumerate(names):
        columns[f"target_{name}"] = matrix[target, position]
        columns[f"template_{name}"] = matrix[template, position]
        columns[f"delta_{name}"] = matrix[target, position] - matrix[template, position]

    difference = normalised[target] - normalised[template]
    columns["design_distance_l2"] = np.linalg.norm(difference, axis=1)
    columns["design_distance_linf"] = np.abs(difference).max(axis=1)
    columns["is_identity"] = (target == template).astype(float)

    if include_surface:
        summaries = geometry_summaries()
        for column in summaries.columns:
            target_values = summaries[column].reindex(target).to_numpy(dtype=float)
            template_values = summaries[column].reindex(template).to_numpy(dtype=float)
            columns[f"target_{column}"] = target_values
            columns[f"ratio_{column}"] = np.divide(
                target_values,
                template_values,
                out=np.full_like(target_values, np.nan),
                where=np.asarray(template_values) != 0,
            )
        if "distance_rms" in observations:
            columns["distance_rms"] = observations["distance_rms"].to_numpy(dtype=float)

    frame = pd.DataFrame(columns, index=observations.index)
    return frame, list(frame.columns)
