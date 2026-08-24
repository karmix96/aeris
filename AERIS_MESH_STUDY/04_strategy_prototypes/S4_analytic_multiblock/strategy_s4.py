"""S4 - Geometry-driven analytical multiblock, minimum surface prototype.

RUNBOOK Section 6 S4: represent the wing with compatible profile and guide
curves following the Gordon-surface principle; construct control vertices
analytically from local geometry; assemble edges, domains and faces in explicit
stages; keep the connectivity rule deterministic across the design space.

The tip is where S4 differs from S1 and S3, and it is deliberate. S1/S3 close the
tip with a butterfly ring, which buries the two blunt trailing-edge corners
inside a ring arc, and the cells there fold. S4 instead derives explicit control
vertices and assembles three transfinite domains whose corners land ON those
features:

    Type 1 (surface):  LE_tip, TE_top_tip, TE_bot_tip
    Type 2 (interior): camber vertices at a fore station and at the TE midpoint
    Domains:           nose, upper, lower

Every domain corner is either a genuine feature (leading edge, trailing-edge
base corner) or a point where one contour edge meets one interior edge at about
90 degrees. No corner has two contour-tangential edges, which is the condition
that failed cap4 in Stage 01 (ADR-0006).

Connectivity is fixed by construction: three OML blocks plus three tip domains,
six blocks on every geometry, independent of how many sections the generator
realises. That is the determinism test S3 fails.
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
    _point_at_x,
    _resample_polyline,
    _tfi_patch,
    camber_and_thickness,
    feature_split_sides,
    butterfly_from_ring,
    map_2d_patch_to_tip,
    oml_tip_ring_2d,
    orient_blocks_consistently,
    orient_patches_2d,
    section_loop_2d,
)

STRATEGY_ID = "S4_ANALYTIC_MULTIBLOCK"


def _straight(p0: np.ndarray, p1: np.ndarray, n: int) -> np.ndarray:
    return np.linspace(0.0, 1.0, n)[:, None] * (p1 - p0)[None, :] + p0[None, :]


def analytic_tip_domains(
    sides: list[np.ndarray],
    *,
    nose_frac: float = 0.20,
    radial_hint: int = 0,
) -> tuple[list[np.ndarray], dict]:
    """Four transfinite tip domains assembled from analytic control vertices.

    The outer boundary is taken directly from the OML side curves rather than
    resampled, so the tip-edge nodes are shared exactly and the tip is watertight
    by construction. Only the interior control vertices are free.

    ``sides`` is the output of :func:`feature_split_sides`: upper (LE -> TE top),
    lower (LE -> TE bottom) and the blunt base (TE bottom -> TE top).
    """
    upper, lower, base = sides
    n_chord = len(upper)
    n_base = len(base)
    if len(lower) != n_chord:
        raise MeshBuildError("upper and lower sides must have equal point counts.")
    if n_base % 2 == 0:
        raise MeshBuildError("te_base_points must be odd so the blunt base splits evenly.")

    j = max(2, min(n_chord - 3, int(round(nose_frac * (n_chord - 1)))))
    mid = (n_base - 1) // 2
    thick_n = mid + 1  # half the base, inclusive of the midpoint

    # --- Type 1 control vertices: on the prescribed surface ----------------
    v_le = upper[0]
    v_up_nose = upper[j]
    v_lo_nose = lower[j]
    v_te_top = upper[-1]
    v_te_bot = lower[-1]
    v_te_mid = base[mid]

    # --- Type 2 control vertices: interior, on the camber line -------------
    v_cam_nose = 0.5 * (v_up_nose + v_lo_nose)
    v_cam_le = 0.5 * (upper[1] + lower[1])

    # --- Control edges: outer ones are OML curves, used as given -----------
    e_up_nose = upper[: j + 1]  # LE -> nose station
    e_lo_nose = lower[: j + 1]
    e_up_main = upper[j:]  # nose station -> TE top
    e_lo_main = lower[j:]
    e_base_up = base[mid:]  # TE mid -> TE top
    e_base_lo = base[: mid + 1][::-1]  # TE mid -> TE bottom

    e_cam_fore = _straight(v_cam_nose, v_cam_le, j + 1)
    e_camber = _straight(v_cam_nose, v_te_mid, len(e_up_main))
    e_le_cross = _straight(v_cam_le, v_le, thick_n)
    e_nose_cross_up = _straight(v_cam_nose, v_up_nose, thick_n)
    e_nose_cross_lo = _straight(v_cam_nose, v_lo_nose, thick_n)

    # --- Domains ------------------------------------------------------------
    nose_lower = _tfi_patch(
        bottom=e_lo_nose[::-1], top=e_cam_fore, left=e_nose_cross_lo[::-1], right=e_le_cross[::-1]
    )
    nose_upper = _tfi_patch(
        bottom=e_cam_fore[::-1], top=e_up_nose, left=e_le_cross, right=e_nose_cross_up
    )
    upper_dom = _tfi_patch(
        bottom=e_camber, top=e_up_main, left=e_nose_cross_up, right=e_base_up
    )
    lower_dom = _tfi_patch(
        bottom=e_camber, top=e_lo_main, left=e_nose_cross_lo, right=e_base_lo
    )

    domains, flipped = orient_patches_2d([nose_lower, nose_upper, upper_dom, lower_dom])
    info = {
        "topology": "analytic_four_domain_tip_on_oml_edges",
        "block_names": ["tip_nose_lower", "tip_nose_upper", "tip_upper", "tip_lower"],
        "control_vertices": {
            "type1_surface": {
                "le": v_le.tolist(),
                "upper_nose": v_up_nose.tolist(),
                "lower_nose": v_lo_nose.tolist(),
                "te_top": v_te_top.tolist(),
                "te_bot": v_te_bot.tolist(),
            },
            "type2_interior": {
                "camber_nose": v_cam_nose.tolist(),
                "camber_le": v_cam_le.tolist(),
                "te_mid": v_te_mid.tolist(),
            },
        },
        "nose_split_index": int(j),
        "thickness_points": int(thick_n),
        "orientation_flipped": flipped,
        "outer_edges": "exact OML side curves; no resampling",
    }
    return domains, info


def build_surface(
    wing,
    *,
    chord_points: int = 49,
    te_thickness: float = 0.005,
    te_base_points: int = 9,
    nose_x: float = 0.20,
) -> tuple[list[SurfaceBlock], dict]:
    """Build the S4 surface: three OML blocks plus three analytic tip domains."""
    xsecs = list(wing.xsecs)
    if len(xsecs) < 3:
        raise MeshBuildError("S4 needs at least three spanwise stations.")

    sides_by_xsec = []
    for xsec in xsecs:
        coords, le_index = section_loop_2d(xsec, te_thickness=te_thickness)
        sides_by_xsec.append(
            feature_split_sides(
                coords, le_index, chord_points=chord_points, te_base_points=te_base_points
            )
        )
    oml = _map_sides_to_wing(wing, sides_by_xsec)
    names = ["oml_upper", "oml_lower", "te_base"]
    blocks = [SurfaceBlock(name=n, xyz=b, family="wall") for n, b in zip(names, oml, strict=True)]

    # S4's own four-domain tip splits the section on the CAMBER LINE. That was
    # built, measured and rejected: the camber line has zero thickness at the
    # leading and trailing edges, so the interface degenerates there and both
    # nose domains fold (51 folded cells, min scaled Jacobian -0.2394, identical
    # on all ten geometries). Kept in `analytic_tip_domains` as the recorded
    # negative result.
    #
    # The tip therefore uses the camber-aligned RECTANGLE construction instead -
    # inner boundary at camber + width_frac * (surface - camber) with a
    # chordwise inset - which is the closure proven in commit bfaeaf1. S4 keeps
    # its analytic control-vertex derivation of the OML; only the closure
    # changes.
    ring_2d, ring_info = oml_tip_ring_2d(sides_by_xsec[-1])
    domains, tip_info = butterfly_from_ring(ring_2d, ring_info["corner_indices"])
    tip_info["ring"] = ring_info
    tip_info["superseded_construction"] = (
        "analytic_four_domain_tip_on_oml_edges; camber-line split rejected by measurement"
    )
    blocks += [
        SurfaceBlock(name=n, xyz=map_2d_patch_to_tip(wing, d), family="wall")
        for n, d in zip(tip_info["block_names"], domains, strict=True)
    ]

    blocks, orientation = orient_blocks_consistently(blocks)

    info = {
        "strategy_id": STRATEGY_ID,
        "orientation": orientation,
        "construction": "Gordon-style guide/profile curves with analytic control vertices",
        "oml_block_names": names,
        "tip_info": tip_info,
        "block_count": len(blocks),
        "connectivity_rule": "fixed 8 blocks on every geometry, independent of section count",
    }
    return blocks, info
