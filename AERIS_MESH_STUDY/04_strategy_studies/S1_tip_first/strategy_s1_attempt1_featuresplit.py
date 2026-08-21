"""S1 — tip-first spanwise sweep. Written from scratch under ADR-0011.

RUNBOOK §6 S1, and the Openblademesh thesis (§§1.1.2, 1.1.4, 3.1.4–3.1.7, 3.3, 4.2)
via `01_references/S1_tip_first_sweep_implementation_note.md`:

    mesh the exact physical tip FIRST; build a structured tip pattern with matching
    upper/lower/LE/TE boundaries; sweep that pattern from tip toward root; take
    spanwise point counts from physical segment length under a geometric-progression
    law; enforce cell-size matching at every planform break; treat abrupt
    tip-to-wing spacing change as the main risk.

`s1_stage02_prior_art.py` in this folder is the **Stage 02** implementation. It is
prior art to read and beat — not this entry. Its recorded result is the number to
beat: min scaled Jacobian **+0.045**, cell-size range **99×**, and a clean march
(0/128 bad layers, min quality +0.224) at epsE 1.5.

--------------------------------------------------------------------------------
THE BLOCKING — S1's own, and deliberately different from S0's
--------------------------------------------------------------------------------

**OML, 3 blocks.** The section is split at *genuine curvature features* only: the
leading edge, and the two blunt trailing-edge base corners.

    upper   LE -> upper TE base corner       chord_points
    lower   LE -> lower TE base corner       chord_points
    base    lower base corner -> upper       te_base_points

S0 splits instead at x/c = ±`wrap_x`, which are arbitrary stations on a smooth
contour. That difference is the whole point of running both: S1 tests the claim
that corners belong on features.

**Tip, 5 blocks.** A camber-aligned rectangle plus four collars. The ring corners
are the two blunt-base corners and two points straddling the leading edge, so every
cap corner sits where the contour genuinely turns.

The inner boundary is `camber + width_frac * (surface - camber)` — a convex
combination, inside the section by construction (COMMON_BRIEF §1) — and is inset
chordwise so collar end edges slant (§2).

**Why this survives what killed S0's cap.** S0 could not get a good trailing-edge
collar because its ring corners are at the shoulders, so a collar had to reach from
the 0.005-chord blunt base to an inner boundary ~0.12 chord away (COMMON_BRIEF
§11.3). S1's corners ARE the base corners and its inner boundary follows the
section, so that gap never opens.

--------------------------------------------------------------------------------
WHAT THE SOURCE STATES VERSUS WHAT HAD TO BE INVENTED
--------------------------------------------------------------------------------

Recorded in `STUDY.md` §1. In short: Openblademesh supplies the *pattern* — close
the tip first, control curve progressions explicitly, sweep inward through ordered
stations — and no BWB block graph, no tip subdivision, and no growth-law constants.
All three had to be designed here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

STUDIES = Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.ingestion import (  # noqa: E402
    MeshBuildError,
    SurfaceBlock,
    _map_sides_to_wing,
    _resample_polyline,
    _tfi_patch,
    section_loop_2d,
)
from shared.qc import orient_blocks_consistently, orient_patches_2d  # noqa: E402

Array = np.ndarray

STRATEGY_ID = "S1_TIP_FIRST_SWEEP"

#: S1's own five-level family. `te_base_points` and `collar_points` scale with
#: `chord_points` per COMMON_BRIEF §11.1 — a fixed count over a fixed chord
#: fraction drifts out of proportion across the family. The blunt base is 0.005
#: chord, so its share is small and its counts stay low on purpose: putting points
#: into a 0.005-chord feature shrinks the smallest cell, which is what governs the
#: march (ADR-0010).
LEVELS = {
    "L1_coarse": dict(le_wrap_points=3, chord_points=25, te_base_points=3, collar_points=3, target_cell_m=0.020),
    "L2_smoke": dict(le_wrap_points=3, chord_points=33, te_base_points=3, collar_points=3, target_cell_m=0.015),
    "L3_medium": dict(le_wrap_points=3, chord_points=49, te_base_points=3, collar_points=5, target_cell_m=0.010),
    "L4_fine": dict(le_wrap_points=5, chord_points=65, te_base_points=5, collar_points=5, target_cell_m=0.008),
    "L5_production": dict(le_wrap_points=5, chord_points=97, te_base_points=5, collar_points=7, target_cell_m=0.006),
}

TE_THICKNESS = 0.005
WIDTH_FRAC = 0.30
CHORD_INSET = 0.02
GROWTH_LIMIT = 1.2


# ---------------------------------------------------------------------------
# S1's chordwise blocking: split on features only
# ---------------------------------------------------------------------------


def feature_sides(
    coords: Array,
    le_index: int,
    *,
    chord_points: int,
    te_base_points: int,
    distribution: str,
    beta: float = 2.0,
) -> list[Array]:
    """Split a section at the LE and the two blunt-TE base corners.

    Returns ``[upper, lower, base]``:

        upper  LE -> upper TE base corner
        lower  LE -> lower TE base corner
        base   lower base corner -> upper base corner

    Three corners, all genuine curvature features. This is S1's central claim and
    the thing S0's `wrap_x` split does not do.

    ``te_base_points`` must be **odd** so the ring splits symmetrically about the
    base when the tip cap is built (see :func:`tip_ring_2d`).
    """
    if te_base_points < 3 or te_base_points % 2 == 0:
        raise MeshBuildError("te_base_points must be odd and at least 3.")
    upper = coords[: le_index + 1][::-1]  # LE -> upper TE
    lower = coords[le_index:]  # LE -> lower TE
    upper_r = _resample_polyline(upper, chord_points, distribution=distribution, beta=beta)
    lower_r = _resample_polyline(lower, chord_points, distribution=distribution, beta=beta)
    base = _resample_polyline(
        np.vstack([lower[-1], upper[-1]]), te_base_points, distribution="uniform", beta=1.0
    )
    return [upper_r, lower_r, base]


# ---------------------------------------------------------------------------
# S1's spanwise law: geometric progression from physical segment length
# ---------------------------------------------------------------------------


def spanwise_counts(
    lengths: list[float], *, target_cell: float, growth_limit: float = GROWTH_LIMIT, minimum: int = 2
) -> list[int]:
    """Cells per spanwise interval from physical length, growth-limited.

    RUNBOOK §6 S1 requires the count to come from physical segment length rather
    than a fixed panel count, and the Openblademesh thesis names abrupt cell-size
    change as the failure mode pyHyp punishes. Adjacent intervals are therefore
    reconciled until none exceeds its neighbour by more than ``growth_limit`` —
    which is also RUNBOOK §6's "enforce exact cell-size matching at every planform
    break", applied as a bounded ratio rather than an equality.
    """
    raw = [max(minimum, int(round(length / max(target_cell, 1e-12)))) for length in lengths]
    for _ in range(len(raw) * 3):
        changed = False
        for i in range(len(raw) - 1):
            hi, lo = max(raw[i], raw[i + 1]), min(raw[i], raw[i + 1])
            if hi > lo * growth_limit:
                capped = max(minimum, int(np.ceil(lo * growth_limit)))
                if raw[i] > raw[i + 1]:
                    raw[i] = capped
                else:
                    raw[i + 1] = capped
                changed = True
        if not changed:
            break
    return raw


def sweep_tip_to_root(blocks: list[Array], cells_per_interval: list[int]) -> list[Array]:
    """Realise the spanwise law by subdividing each interval, tip-first.

    Intervals are consumed from the TIP inward, which is what makes this a
    tip-first sweep rather than a root-first one: the tip interval's spacing is
    fixed by the tip cap and every interval inboard is grown from it under the
    progression law.

    New columns are linear blends of their bounding stations. That is an
    approximation of a spline loft with a measured fidelity cost (COMMON_BRIEF
    §9.5); `shared.verify.oml_fidelity` reports which columns are on a station and
    which are not.
    """
    n_int = blocks[0].shape[1] - 1
    if len(cells_per_interval) != n_int:
        raise MeshBuildError(
            f"law gives {len(cells_per_interval)} intervals, blocks have {n_int}"
        )
    out = []
    for blk in blocks:
        cols = []
        for j, n_cells in enumerate(cells_per_interval):
            for k in range(int(n_cells)):
                s = k / float(n_cells)
                cols.append((1.0 - s) * blk[:, j, :] + s * blk[:, j + 1, :])
        cols.append(blk[:, -1, :])
        out.append(np.stack(cols, axis=1))
    return out


# ---------------------------------------------------------------------------
# S1's tip closure: camber rectangle + four collars, cornered on features
# ---------------------------------------------------------------------------


def tip_ring_2d(
    sides: list[Array], *, le_wrap_points: int
) -> tuple[Array, tuple[int, int, int, int], dict]:
    """Closed tip ring taken from the OML side curves themselves.

    Watertightness cannot be achieved by resampling the section a second time: a
    cap that builds its own ring at its own point count never shares nodes with the
    OML tip edge, and every block still passes QC alone (COMMON_BRIEF §9.4). The
    ring is therefore assembled from the OML sides, so the shared nodes are
    identical by construction.

    Corners: two points straddling the leading edge, and two points straddling the
    blunt base. Opposite arcs of the cap must carry equal counts, so the
    leading-edge arc and the trailing arc are the same length.

    **The Stage 02 version put the corners exactly ON the two base corners**, which
    forces ``le_wrap_points == te_base_points``. That coupling is fatal: the blunt
    base is 0.005 chord and wants FEW points (more points there shrink the smallest
    cell, which governs the march — ADR-0010), while the leading edge is a tight
    turn and wants MANY. Measured at `te_base_points = 3`: the nose collar gets 3
    ring points and 4 cells, and folds at **-0.97585**, while every other block is
    positive. Raising `te_base_points` to 5 to feed the nose fails too, because it
    then crams points into the base.

    Decoupling was ATTEMPTED and REJECTED (see STUDY.md): letting the trailing arc
    extend ``m`` points onto the
    upper and lower surfaces either side of the base, so it reaches
    ``le_wrap_points`` without those points landing inside the 0.005-chord feature:

        te_base_points + 2m == le_wrap_points == 2k + 1

    surfaces either side of the base does satisfy the count constraint, but it moves
    the arcs' chordwise extent while the inner rectangle still spans the full chord,
    so every collar is stretched at one end: measured cell-size range **705.5** at
    every level and min scaled Jacobian -0.976 to -1.000. `le_wrap_points` is kept
    as a knob, defaulted to ``te_base_points`` (m = 0, the corners exactly on the
    base corners), so the negative result stays reproducible. Fixing it properly
    would require the inner rectangle to follow the arcs' extent, which is a
    different cap construction.
    """
    upper, lower, base = sides
    n_chord, n_base = len(upper), len(base)
    if len(lower) != n_chord:
        raise MeshBuildError("upper and lower sides must have equal point counts.")
    if n_base % 2 == 0:
        raise MeshBuildError("te_base_points must be odd so the ring splits symmetrically.")

    # LE -> upper -> TE top -> base -> TE bottom -> lower back toward LE.
    ring = np.vstack([upper, base[::-1][1:], lower[::-1][1:-1]])
    idx_te_top = n_chord - 1
    idx_te_bot = idx_te_top + (n_base - 1)
    total = len(ring)
    if le_wrap_points % 2 == 0 or le_wrap_points < n_base:
        raise MeshBuildError(
            f"le_wrap_points must be odd and >= te_base_points ({n_base}), got {le_wrap_points}"
        )
    m = (le_wrap_points - n_base) // 2
    k = (le_wrap_points - 1) // 2
    if k < 1 or 2 * k + 1 > total or idx_te_top - m <= k:
        raise MeshBuildError(
            f"le_wrap_points {le_wrap_points} too large for a {n_chord}-point chord side."
        )
    corners = (k, idx_te_top - m, idx_te_bot + m, total - k)
    info = {
        "ring_points": int(total),
        "corner_indices": [int(c) for c in corners],
        "le_wrap_points": int(le_wrap_points),
        "te_arc_extra_per_side": int(m),
        "arc_counts": [
            int(idx_te_top - m - k + 1), int(n_base + 2 * m),
            int(total - k - idx_te_bot - m + 1), int(2 * k + 1),
        ],
        "source": "OML side curves; no resampling, so tip-edge nodes are shared exactly",
    }
    return ring, corners, info


def camber_cap_2d(
    ring: Array,
    corners: tuple[int, int, int, int],
    coords: Array,
    le_index: int,
    *,
    width_frac: float,
    chord_inset: float,
    collar_points: int,
) -> tuple[list[Array], dict]:
    """Camber-aligned rectangle plus four collars, over a ring fixed by the OML.

    The inner rectangle is `camber + width_frac * (surface - camber)` evaluated on
    the section, so it lies inside by construction, and it is inset chordwise so
    the collar end edges slant instead of running collinear with its short sides
    (COMMON_BRIEF §§1–2).
    """
    total = len(ring)
    idx = [int(c) % total for c in corners]
    arcs = []
    for a_, b_ in zip(idx, idx[1:] + idx[:1], strict=True):
        arcs.append(ring[a_ : b_ + 1] if b_ > a_ else np.vstack([ring[a_:], ring[: b_ + 1]]))

    e_up = arcs[0][::-1]    # upper, TE -> nose
    e_te = arcs[1][::-1]    # trailing wrap, lower -> upper
    e_low = arcs[2][::-1]   # lower, nose -> TE
    e_nose = arcs[3][::-1]  # nose wrap, upper -> lower

    n_chord, n_wrap = len(e_low), len(e_nose)
    if len(e_up) != n_chord or len(e_te) != n_wrap:
        raise MeshBuildError(
            f"tip ring arcs must pair up: chord {n_chord}/{len(e_up)}, wrap {n_wrap}/{len(e_te)}"
        )
    if collar_points < 3:
        raise MeshBuildError("collar_points must be at least 3.")
    if not (0.05 <= width_frac <= 0.95):
        raise MeshBuildError("width_frac must lie between 0.05 and 0.95.")

    upper_s = coords[: le_index + 1][::-1]
    lower_s = coords[le_index:]
    xs = np.linspace(chord_inset, 1.0 - chord_inset, n_chord)
    x0, x1 = float(upper_s[0, 0]), float(upper_s[-1, 0])
    xq = x0 + (x1 - x0) * xs
    zu = np.interp(xq, upper_s[:, 0], upper_s[:, 1])
    zl = np.interp(xq, lower_s[:, 0], lower_s[:, 1])
    camber = 0.5 * (zu + zl)
    rect_top = np.column_stack([xq, camber + width_frac * (zu - camber)])
    rect_bot = np.column_stack([xq, camber + width_frac * (zl - camber)])

    def _straight(p0: Array, p1: Array, n: int) -> Array:
        s = np.linspace(0.0, 1.0, n)[:, None]
        return (1.0 - s) * p0 + s * p1

    rect_left = _straight(rect_top[0], rect_bot[0], n_wrap)
    rect_right = _straight(rect_bot[-1], rect_top[-1], n_wrap)

    collar_nose = _tfi_patch(
        _straight(e_nose[0], rect_top[0], collar_points),
        _straight(e_nose[-1], rect_bot[0], collar_points),
        e_nose, rect_left,
    ).transpose(1, 0, 2)
    collar_low = _tfi_patch(
        _straight(e_nose[-1], rect_bot[0], collar_points),
        _straight(e_low[-1], rect_bot[-1], collar_points),
        e_low, rect_bot,
    ).transpose(1, 0, 2)
    collar_te = _tfi_patch(
        _straight(e_low[-1], rect_bot[-1], collar_points),
        _straight(e_up[0], rect_top[-1], collar_points),
        e_te, rect_right,
    ).transpose(1, 0, 2)
    collar_up = _tfi_patch(
        _straight(e_up[0], rect_top[-1], collar_points),
        _straight(e_nose[0], rect_top[0], collar_points),
        e_up, rect_top[::-1],
    ).transpose(1, 0, 2)
    centre = _tfi_patch(rect_bot, rect_top, rect_left[::-1], rect_right)

    patches = [centre, collar_up, collar_te, collar_low, collar_nose]
    patches, flipped = orient_patches_2d(patches)
    info = {
        "topology": "camber_rectangle_plus_four_collars",
        "block_names": ["tip_centre", "tip_collar_upper", "tip_collar_te",
                        "tip_collar_lower", "tip_collar_nose"],
        "width_frac": width_frac,
        "chord_inset": chord_inset,
        "collar_points": int(collar_points),
        "n_chord": int(n_chord),
        "n_wrap": int(n_wrap),
        "ring_corners": "two blunt-base corners + two points straddling the LE",
        "orientation_flipped": flipped,
        "outer_boundary": "exact OML tip-edge nodes",
    }
    return patches, info


def map_patch_2d_to_tip(wing, patch_2d: Array) -> Array:
    """Map a 2D (ni, nj, 2) section patch onto the wing's outermost station."""
    n_xsec = len(wing.xsecs)
    ni = patch_2d.shape[0]
    sides_by_xsec = [[patch_2d[i] for i in range(ni)] for _ in range(n_xsec)]
    mapped = _map_sides_to_wing(wing, sides_by_xsec)
    return np.stack([m[:, -1, :] for m in mapped], axis=0)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

OML_NAMES = ["oml_upper", "oml_lower", "oml_te_base"]


def build_surface(
    wing,
    *,
    level: str = "L2_smoke",
    te_thickness: float = TE_THICKNESS,
    chordwise_distribution: str = "uniform",
    chordwise_beta: float = 2.0,
    width_frac: float = WIDTH_FRAC,
    chord_inset: float = CHORD_INSET,
    growth_limit: float = GROWTH_LIMIT,
    realise_law: bool = True,
    **overrides,
) -> tuple[list[SurfaceBlock], dict]:
    """Build S1's surface: 3 OML blocks swept tip-to-root plus a 5-block tip cap."""
    if level not in LEVELS:
        raise MeshBuildError(f"unknown level {level!r}; known: {sorted(LEVELS)}")
    cfg = dict(LEVELS[level])
    cfg.update({k: v for k, v in overrides.items() if v is not None})

    xsecs = list(wing.xsecs)
    if len(xsecs) < 3:
        raise MeshBuildError("S1 needs at least three spanwise stations.")

    sides_by_xsec = []
    tip_coords = tip_le = None
    for xsec in xsecs:
        coords, le_index = section_loop_2d(xsec, te_thickness=te_thickness)
        tip_coords, tip_le = coords, le_index
        sides_by_xsec.append(
            feature_sides(
                coords, le_index,
                chord_points=cfg["chord_points"],
                te_base_points=cfg["te_base_points"],
                distribution=chordwise_distribution,
                beta=chordwise_beta,
            )
        )

    oml = _map_sides_to_wing(wing, sides_by_xsec)

    le_line = np.asarray(
        wing.mesh_line(x_nondim=[0.0] * len(xsecs), z_nondim=[0.0] * len(xsecs), add_camber=False)
    )
    lengths = [float(np.linalg.norm(le_line[i + 1] - le_line[i])) for i in range(len(xsecs) - 1)]
    counts = spanwise_counts(lengths, target_cell=cfg["target_cell_m"], growth_limit=growth_limit)
    if realise_law:
        oml = sweep_tip_to_root(oml, counts)

    blocks = [SurfaceBlock(name=n, xyz=b, family="wall") for n, b in zip(OML_NAMES, oml, strict=True)]

    ring, corners, ring_info = tip_ring_2d(
        sides_by_xsec[-1], le_wrap_points=cfg["le_wrap_points"]
    )
    cap_2d, cap_info = camber_cap_2d(
        ring, corners, tip_coords, tip_le,
        width_frac=width_frac, chord_inset=chord_inset, collar_points=cfg["collar_points"],
    )
    cap_info["ring"] = ring_info
    blocks += [
        SurfaceBlock(name=n, xyz=map_patch_2d_to_tip(wing, p), family="wall")
        for n, p in zip(cap_info["block_names"], cap_2d, strict=True)
    ]

    blocks, orientation = orient_blocks_consistently(blocks)

    info = {
        "strategy_id": STRATEGY_ID,
        "level": level,
        "level_settings": cfg,
        "te_thickness": te_thickness,
        "chordwise_distribution": chordwise_distribution,
        "sweep_direction": "tip_to_root",
        "oml_block_names": OML_NAMES,
        "tip_block_names": cap_info["block_names"],
        "tip_closure": cap_info["topology"],
        "tip_cap_info": cap_info,
        "orientation": orientation,
        "corner_policy": (
            "OML corners on the leading edge and the two blunt-TE base corners only; "
            "tip-cap ring corners on the base corners and two points straddling the LE"
        ),
        "spanwise": {
            "target_cell_m": cfg["target_cell_m"],
            "growth_limit": growth_limit,
            "segment_lengths_m": lengths,
            "cells_per_interval": counts,
            "realised": bool(realise_law),
            "spanwise_cells": int(sum(counts)) if realise_law else len(xsecs) - 1,
            "native_stations": len(xsecs),
        },
    }
    return blocks, info
