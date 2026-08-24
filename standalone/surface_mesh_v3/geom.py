"""Build (and cache) the canonical BWB pyGeo loft for surface-mesh development.

One place that produces the authoritative ``PyGeoBuild`` from
``configs/geometry/bwb.yaml`` at the registered study baseline, so every
experiment in this package meshes the same aircraft.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data" / "surface_mesh_v3" / "baseline_build.pkl"


def _spec_and_config() -> tuple[Any, Any]:
    from standalone.pygeo_surface_mesh_study.runner import load_generator_config
    from standalone.pygeo_surface_mesh_study.spec import load_study_spec

    spec = load_study_spec(REPO / "configs" / "cfd" / "pygeo_surface_mesh_study.yaml")
    return spec, load_generator_config(spec)


def build_baseline(source_sections: int | None = None):
    """Return ``(carrier, build, geometry)`` for the registered baseline sample."""
    import dataclasses

    from standalone.pygeo_surface_mesh_study.runner import build_geometry

    spec, config = _spec_and_config()
    if source_sections is not None:
        spec = dataclasses.replace(spec, source_sections=int(source_sections))
    return build_geometry(spec, config, spec.baseline_case())


def baseline_build(refresh: bool = False):
    """pyGeo build only, cached to disk (the loft costs a few seconds)."""
    if CACHE.is_file() and not refresh:
        with CACHE.open("rb") as fh:
            return pickle.load(fh)
    _carrier, build, _geom = build_baseline()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("wb") as fh:
        pickle.dump(build, fh)
    return build


def surface_pair(build):
    """``(upper, lower)`` pySpline surfaces, oriented TE->LE in u at the root."""
    return build.geometry.surfs[0], build.geometry.surfs[1]


def evaluate(surface, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Evaluate a pySpline surface on matching flat arrays, returning (N, 3)."""
    return np.asarray(surface(np.asarray(u, float), np.asarray(v, float)), dtype=float)
