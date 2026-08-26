"""Local surface controls for S6, without touching the S6 strategy.

`geometry.build_s6_surface` already builds the structured multiblock S6 marches;
what it cannot do is vary the resolution locally, because `strategy_s6`
`build_surface` reads its chord, end and collar counts from its own `LEVELS`
table rather than accepting them as arguments.

So a THROWAWAY level is registered under a name S6 does not use, the surface is
built against it, and it is removed again.  S6's four declared levels are never
read, written or shadowed - verified by comparing the table before and after -
and no S6 file is modified.  A lock serialises the add/remove because meshing
runs on a worker thread.

The quality metrics here are the reason the controls are worth having: the point
of a refinement UI is that you can see whether the refinement helped.
"""

from __future__ import annotations

import sys
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .environment import REPO_ROOT, S6_DIR, STRATEGY_DIR

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR), str(S6_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_LEVEL_LOCK = threading.Lock()

# Each control, and the name a commercial mesher would give it.
CONTROL_HELP = {
    "chord_points": "Chordwise divisions (edge sizing along the chord)",
    "end_points": "Divisions across the leading and trailing edge blocks",
    "collar_points": "Divisions around the tip collar",
    "span_cells": "Spanwise divisions — the lever for trailing-edge aspect ratio",
    "span_max_cell_m": "Largest spanwise cell, metres (face sizing)",
    "end_scale": "LE/TE clustering strength; higher packs more points at the edges",
    "te_abs_m": "Trailing edge thickness, metres",
    "te_floor_frac": "Trailing edge thickness floor, fraction of local chord",
    "tip_first_cell_frac_of_tip_chord": "First cell at the tip, fraction of tip chord",
}


@dataclass
class S6SurfaceSettings:
    level: str = "smoke"
    chord_points: int = 33
    end_points: int = 3
    collar_points: int = 7
    span_cells: int = 89
    span_max_cell_m: float = 0.015
    end_scale: float = 5.0
    te_abs_m: float = 0.001
    te_floor_frac: float = 0.005
    tip_first_cell_frac_of_tip_chord: float = 0.0045

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def settings_from_level(level: str) -> S6SurfaceSettings:
    from strategy_s6 import LEVELS  # noqa: PLC0415

    spec = LEVELS[level]
    return S6SurfaceSettings(
        level=level,
        chord_points=int(spec.chord_points),
        end_points=int(spec.end_points),
        collar_points=int(spec.collar_points),
        span_cells=int(spec.span_cells),
        span_max_cell_m=float(spec.span_max_cell_m),
    )


def build_with_controls(settings: S6SurfaceSettings, index: int, output_dir: Path,
                        *, set_name: str = "lhs100_seed42"):
    """S6's own surface builder, driven by the workbench's local controls."""
    from strategy_s6 import LEVELS, LevelSpec, build_locked_surface  # noqa: PLC0415

    base = LEVELS[settings.level]
    scratch = f"__workbench_{uuid.uuid4().hex[:8]}"
    override = LevelSpec(
        chord_points=int(settings.chord_points),
        end_points=int(settings.end_points),
        collar_points=int(settings.collar_points),
        span_cells=int(settings.span_cells),
        dense_curve_points=int(base.dense_curve_points),
        span_max_cell_m=float(settings.span_max_cell_m),
    )
    with _LEVEL_LOCK:
        LEVELS[scratch] = override
        try:
            blocks, info, case = build_locked_surface(
                set_name, int(index), Path(output_dir), level=scratch,
                te_abs_m=float(settings.te_abs_m),
                te_floor_frac=float(settings.te_floor_frac),
                end_scale=float(settings.end_scale),
                tip_first_cell_frac_of_tip_chord=float(
                    settings.tip_first_cell_frac_of_tip_chord),
                span_cells=int(settings.span_cells),
            )
        finally:
            LEVELS.pop(scratch, None)
    info = dict(info)
    info["workbench_level_basis"] = settings.level
    info["workbench_controls"] = settings.as_dict()
    return blocks, info, case


def _patch_metrics(grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Edge ratio and smallest corner angle for every quad in one patch."""
    p00, p10 = grid[:-1, :-1], grid[1:, :-1]
    p11, p01 = grid[1:, 1:], grid[:-1, 1:]
    edges = np.stack([
        np.linalg.norm(p10 - p00, axis=-1), np.linalg.norm(p11 - p10, axis=-1),
        np.linalg.norm(p01 - p11, axis=-1), np.linalg.norm(p00 - p01, axis=-1),
    ], axis=-1)
    ratio = edges.max(-1) / np.maximum(edges.min(-1), 1e-30)

    angles = []
    for first, corner, second in ((p01, p00, p10), (p00, p10, p11),
                                  (p10, p11, p01), (p11, p01, p00)):
        left, right = first - corner, second - corner
        cosine = np.sum(left * right, -1) / np.maximum(
            np.linalg.norm(left, axis=-1) * np.linalg.norm(right, axis=-1), 1e-30)
        angles.append(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
    return ratio.ravel(), np.stack(angles, -1).min(-1).ravel()


def quad_quality(blocks: list[Any]) -> dict[str, Any]:
    """Per-patch and overall quality, so a refinement claim is checkable."""
    ratios, angles, per_patch = [], [], []
    for block in blocks:
        grid = np.asarray(block.xyz, dtype=np.float64)
        if grid.shape[0] < 2 or grid.shape[1] < 2:
            continue
        ratio, angle = _patch_metrics(grid)
        ratios.append(ratio)
        angles.append(angle)
        per_patch.append({
            "patch": str(getattr(block, "name", "?")),
            "quads": int(ratio.size),
            "aspect_median": round(float(np.median(ratio)), 2),
            "aspect_p99": round(float(np.percentile(ratio, 99)), 2),
            "min_angle_deg": round(float(angle.min()), 2),
        })
    if not ratios:
        return {"patches": [], "quads": 0}
    ratio = np.concatenate(ratios)
    angle = np.concatenate(angles)
    per_patch.sort(key=lambda row: -row["aspect_median"])
    return {
        "patches": per_patch,
        "quads": int(ratio.size),
        "aspect_median": round(float(np.median(ratio)), 2),
        "aspect_p99": round(float(np.percentile(ratio, 99)), 2),
        "aspect_max": round(float(ratio.max()), 2),
        "min_angle_deg": round(float(angle.min()), 2),
        "per_cell_min_angle": angle,
    }
