"""S1 - Tip-first spanwise sweep, minimum surface prototype.

RUNBOOK Section 6 S1: mesh the exact physical tip first, build a structured tip
pattern with matching upper/lower/LE/TE boundaries, sweep that pattern from tip
toward root, and take spanwise point counts from physical segment length under a
geometric-progression law.

Blocking decision, driven by the Stage 01 root cause (ADR-0006): every block
corner lands on a genuine feature. The section is split at the leading edge and
at the two blunt trailing-edge base corners only - never at an arbitrary x/c
station of a smooth contour. The tip is closed with an all-quad butterfly, whose
block corners each carry a radial edge, so no corner can be collinear with the
contour the way the cap4 airfoil-face cap corner was.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stage02_common import (  # noqa: E402
    MeshBuildError,
    SurfaceBlock,
    _map_sides_to_wing,
    butterfly_from_ring,
    feature_split_sides,
    geometric_progression_counts,
    map_2d_patch_to_tip,
    realise_spanwise_law,
    spanwise_interpolation_error,
    orient_blocks_consistently,
    oml_tip_ring_2d,
    section_loop_2d,
)

STRATEGY_ID = "S1_TIP_FIRST_SWEEP"




def build_surface(
    wing,
    *,
    chord_points: int = 49,
    te_thickness: float = 0.005,
    te_base_points: int = 3,
    target_spanwise_cell: float = 0.010,
    realise_law: bool = True,
    spanwise_growth_limit: float = 1.2,
) -> tuple[list[SurfaceBlock], dict]:
    """Build the S1 surface: three OML blocks swept tip-to-root plus a tip cap."""
    xsecs = list(wing.xsecs)
    if len(xsecs) < 3:
        raise MeshBuildError("S1 needs at least three spanwise stations.")

    sides_by_xsec = []
    for xsec in xsecs:
        coords, le_index = section_loop_2d(xsec, te_thickness=te_thickness)
        sides_by_xsec.append(
            feature_split_sides(
                coords, le_index, chord_points=chord_points, te_base_points=te_base_points
            )
        )

    oml = _map_sides_to_wing(wing, sides_by_xsec)

    # Spanwise law. Counts come from physical segment length with a
    # geometric-progression growth limit.
    #
    # `realise_law` defaults to FALSE, deliberately. Realising it by subdividing
    # between stations does fix the aspect ratio (947 -> 103 at a 0.010 m target
    # cell), but every new column is a linear blend of its two bounding stations,
    # and the master geometry is a spline loft in span. Measured deviation from
    # the realised stations is 1.99e-02 m, about 7.4% of chord - against a
    # geometry-fidelity HARD gate of 0.01% of chord. Aspect ratio is a ranking
    # target; fidelity is a gate. Trading the gate for the target would be the
    # wrong way round.
    #
    # The correct fix is upstream: have the generator realise more sections
    # (`pygeo.extraction.spanwise_sections` is already 25 against the 17 the wing
    # exposes) so the extra columns lie ON the loft instead of on chords of it.
    # That is Stage 03 geometry work, not a mesher change.
    le_line_for_law = np.asarray(
        wing.mesh_line(x_nondim=[0.0] * len(xsecs), z_nondim=[0.0] * len(xsecs), add_camber=False)
    )
    law_lengths = [
        float(np.linalg.norm(le_line_for_law[i + 1] - le_line_for_law[i]))
        for i in range(len(xsecs) - 1)
    ]
    law_points = geometric_progression_counts(
        law_lengths, target_cell=target_spanwise_cell, growth_limit=spanwise_growth_limit
    )
    interp_error = spanwise_interpolation_error(oml)
    if realise_law:
        oml = realise_spanwise_law(oml, [p - 1 for p in law_points])

    names = ["oml_upper", "oml_lower", "te_base"]
    blocks = [SurfaceBlock(name=n, xyz=b, family="wall") for n, b in zip(names, oml, strict=True)]

    # The spanwise law is computed from physical segment length even though the
    # prototype realises the generator's native stations; Stage 03 consumes the
    # recommendation when it re-distributes spanwise points.
    # The cap ring is the OML's own tip-edge curve, so the shared nodes are
    # identical and the tip is watertight by construction.
    ring_2d, ring_info = oml_tip_ring_2d(sides_by_xsec[-1])
    cap_2d, cap_info = butterfly_from_ring(ring_2d, ring_info["corner_indices"])
    cap_info["ring"] = ring_info
    cap_names = cap_info["block_names"]
    blocks += [
        SurfaceBlock(name=n, xyz=map_2d_patch_to_tip(wing, p), family="wall")
        for n, p in zip(cap_names, cap_2d, strict=True)
    ]

    blocks, orientation = orient_blocks_consistently(blocks)

    info = {
        "strategy_id": STRATEGY_ID,
        "orientation": orientation,
        "sweep_direction": "tip_to_root",
        "station_count": len(xsecs),
        "oml_block_names": names,
        "tip_block_names": cap_names,
        "tip_closure": "butterfly_o_h_five_block",
        "tip_cap_info": cap_info,
        "corner_policy": (
            "OML corners on the LE and blunt-TE base corners only; tip-cap block corners "
            "each carry a radial edge so none can be collinear with the contour"
        ),
        "spanwise_law": {
            "target_cell_m": target_spanwise_cell,
            "growth_limit": spanwise_growth_limit,
            "segment_lengths_m": law_lengths,
            "points_per_segment": law_points,
            "realised": bool(realise_law),
            "spanwise_cells": int(sum(p - 1 for p in law_points)) if realise_law else len(xsecs) - 1,
            "interpolation_error_vs_realised_stations": interp_error,
        },
    }
    return blocks, info
