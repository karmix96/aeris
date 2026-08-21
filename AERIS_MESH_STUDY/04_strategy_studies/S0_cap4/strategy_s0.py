"""S0 — the `cap4` control, reimplemented on the shared control module.

RUNBOOK section 6 S0: *preserve the current method; apply only corrections that
are also available to other candidates; keep its known weak regions visible.*

ADR-0011 section 3.1 changed S0's standing. ADR-0006 had recorded it as failing
the volume gate and deliberately **not repaired**, on the grounds that repairing
it meant investing in the topology the tournament exists to replace. That
reasoning assumed the conclusion, and it is reversed: S0 is now developed to its
best achievable state and then judged, like every other entrant.

S0 starts with a real advantage. It is the only strategy that has ever produced a
complete valid volume march — min volume +2.11e-11, `passed: True`, first invalid
layer *none*, on `lhs7_00` at Stage 01 settings — at a time when every other
strategy had marched nothing.

--------------------------------------------------------------------------------
THE BLOCKING (this is S0's own; nothing here is shared)
--------------------------------------------------------------------------------

**OML, 4 blocks.** Each section is split into four sides at x/c = ``wrap_x`` and
``1 - wrap_x`` on both surfaces:

    0  nose wrap    upper shoulder -> LE -> lower shoulder     wrap_points
    1  lower chord  lower nose shoulder -> lower TE shoulder   chord_points
    2  TE wrap      lower TE shoulder -> TE base -> upper      wrap_points
    3  upper chord  upper TE shoulder -> upper nose shoulder   chord_points

The two wrap sides are narrow bands whose *middle* is the leading (or trailing)
edge; the two chord sides are long. Unequal per-side counts are the point of the
topology — they keep surface cell size near-uniform around the airfoil, where a
uniform-count topology over-resolves the tiny LE/TE arcs.

**Tip, 1 block.** A single structured airfoil-face patch whose boundary IS the
four OML tip edges. Built as a lower-to-upper ruled surface with the curved
nose/TE end columns blended a short distance inward under a power law, then the
four boundaries restored exactly. A plain TFI over the same boundary folds at the
shoulders when the wrap edge is strongly curved.

Total: **5 blocks**, on every geometry.

--------------------------------------------------------------------------------
WHAT THE SOURCE STATES VERSUS WHAT HAD TO BE INVENTED (ADR-0011 section 7.1)
--------------------------------------------------------------------------------

S0's "source" is this repository, not a paper: `src/aeris/mesh/surface.py`
(`_airfoil_cap4_sides`, `_build_tip_airfoil_face_cap4`, `_refine_spanwise`) and
the surface-law studies in `configs/cfd/SURFACE_MESH_LAWS.md` and
`configs/cfd/MESH_FAMILY_V2.md`. The construction below follows those functions;
what had to be decided here is recorded in `STUDY.md`.

The one substantive departure is the **default recipe**. `build_surface_mesh`
ships `cap_wrap_x = 0.03` and `cap_wrap_points = 17`, but the repository's own
selected baseline recipe (SURFACE_MESH_LAWS.md, 2026-07-22) and the five-level
family (MESH_FAMILY_V2.md) use ``wrap_x = 0.15`` with ``wrap_points`` scaled per
level. Stage 01 characterised cap4 at the *shipped defaults*, not at the selected
recipe. See :data:`LEVELS` and `STUDY.md` section 4.
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
    _insert_point_at_x,
    _map_sides_to_wing,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    section_loop_2d,
)
from shared.ingestion import _tfi_patch  # noqa: E402
from shared.qc import orient_blocks_consistently, orient_patches_2d  # noqa: E402

Array = np.ndarray

STRATEGY_ID = "S0_CAP4"

#: The five-level family from `configs/cfd/MESH_FAMILY_V2.md`, which is the
#: production recipe this strategy is the control for. `wrap_points` and
#: `tip_blend_points` MUST scale with `chord_points`: fixing `wrap_points` at 17
#: degraded OML aspect ratio 3.5 -> 8.1 across the family, because `wrap_x` tiles
#: a fixed *fraction* of chord while `chord_points` covers the rest.
#:
#:     wrap_points ~ chord_points * wrap_x / (0.5 - wrap_x)
LEVELS = {
    "L1_coarse": dict(chord_points=25, spanwise_panels=8, wrap_points=11, tip_blend_points=5),
    "L2_smoke": dict(chord_points=33, spanwise_panels=12, wrap_points=15, tip_blend_points=7),
    "L3_medium": dict(chord_points=49, spanwise_panels=16, wrap_points=21, tip_blend_points=9),
    "L4_fine": dict(chord_points=65, spanwise_panels=24, wrap_points=29, tip_blend_points=13),
    "L5_production": dict(chord_points=97, spanwise_panels=32, wrap_points=43, tip_blend_points=17),
}

def wrap_points_for(chord_points: int, wrap_x: float) -> int:
    """The family's own wrap-count law, MESH_FAMILY_V2.md.

        wrap_points ~ chord_points * wrap_x / (0.5 - wrap_x)

    `wrap_x` tiles a fixed FRACTION of chord while `chord_points` covers the
    rest, so a fixed wrap count degrades aspect ratio across the family — the
    documented case is 3.5 -> 8.1 from L2 to L5.

    Applying the law is what made S0 work, and it took a while to see. Every
    earlier wrap_x sweep held wrap_points at its per-level value, which packs a
    fixed number of points into a band that is being narrowed — so shrinking
    wrap_x bought Jacobian and paid for it in cell-size range (545x at 0.03).
    Obeying the law instead gives BOTH: at wrap_x 0.03 the wrap blocks carry 5
    points and the surface reaches +0.191 with a 113x range, level-invariantly.

    Odd counts only, so the wrap arcs stay symmetric about the LE and the blunt
    base.
    """
    n = max(5, int(round(chord_points * wrap_x / (0.5 - wrap_x))))
    return n if n % 2 else n + 1


#: Held constant at every level (MESH_FAMILY_V2.md).
WRAP_X = 0.03
TE_THICKNESS_ABS_M = 0.001  # DECISION-0004: constant absolute, not a chord fraction
TIP_SMOOTH_ITERS = 20
SPANWISE_ALLOCATION = "proportional"


# ---------------------------------------------------------------------------
# S0's chordwise blocking: the four-side split at +/- wrap_x
# ---------------------------------------------------------------------------


def cap4_sides(
    coords: Array,
    le_index: int,
    *,
    wrap_x: float,
    chord_points: int,
    wrap_points: int,
    te_base_points: int,
    chordwise_distribution: str,
    chordwise_beta: float,
    te_wrap_points: int | None = None,
) -> tuple[list[Array], dict]:
    """Split one section into cap4's four sides.

    Corners land at x/c = ``wrap_x`` and ``1 - wrap_x`` on both surfaces, so the
    leading edge and the trailing-edge base sit in block *interiors* rather than
    at corners. That is cap4's central design claim and also its known weakness:
    the four corners lie on smooth parts of the contour, where the two meeting
    edges are near-collinear (ADR-0006).

    ``chordwise_distribution = "junction"`` is cap4's own mode and the one the
    production recipe uses: it clusters only the two long chord sides, whose ends
    ARE the wrap-block junctions, and leaves the two wrap sides uniform.
    Clustering a wrap side would coarsen its middle — which is the leading edge,
    the point most needing resolution.
    """
    if not (0.01 <= wrap_x <= 0.45):
        raise MeshBuildError("wrap_x must lie between 0.01 and 0.45.")
    if wrap_points < 3:
        raise MeshBuildError("wrap_points must be at least 3.")
    # The nose wrap and the TE wrap are SEPARATE OML blocks, so nothing forces
    # them to carry the same point count. Stage 02 and the shipped code tied
    # them together; decoupling is what lets the TE wrap carry enough points to
    # pin the two blunt-base corners while the nose wrap stays coarse enough not
    # to manufacture tiny cells at the leading edge.
    n_te_wrap = int(te_wrap_points or wrap_points)
    shoulder_x = 1.0 - wrap_x

    upper_te_to_le = coords[: le_index + 1].copy()  # upper TE -> LE
    lower_le_to_te = coords[le_index:].copy()  # LE -> lower TE

    upper_te_to_le, upper_shoulder_idx = _insert_point_at_x(upper_te_to_le, shoulder_x)
    upper_te_to_le, upper_nose_idx = _insert_point_at_x(upper_te_to_le, wrap_x)
    lower_le_to_te, lower_nose_idx = _insert_point_at_x(lower_le_to_te, wrap_x)
    lower_le_to_te, lower_shoulder_idx = _insert_point_at_x(lower_le_to_te, shoulder_x)
    te_mid = 0.5 * (upper_te_to_le[0] + lower_le_to_te[-1])

    raw_sides = [
        # nose wrap: upper shoulder -> LE -> lower shoulder
        np.vstack([upper_te_to_le[upper_nose_idx:], lower_le_to_te[1 : lower_nose_idx + 1]]),
        # lower chord
        lower_le_to_te[lower_nose_idx : lower_shoulder_idx + 1],
        # TE wrap: lower shoulder -> blunt base -> upper shoulder
        np.vstack(
            [lower_le_to_te[lower_shoulder_idx:], [te_mid], upper_te_to_le[: upper_shoulder_idx + 1]]
        ),
        # upper chord
        upper_te_to_le[upper_shoulder_idx : upper_nose_idx + 1],
    ]
    counts = [wrap_points, chord_points, n_te_wrap, chord_points]
    if chordwise_distribution == "junction":
        per_side = ["uniform", "cosine", "uniform", "cosine"]
    else:
        per_side = [chordwise_distribution] * 4

    sides = []
    for index, (side, n, mode) in enumerate(zip(raw_sides, counts, per_side, strict=True)):
        if index == 2 and te_base_points >= 2:
            # The TE wrap is (lower arc | blunt base | upper arc). Both base
            # corners are pinned by resampling the three pieces separately —
            # arc-length resampling across them smears the two ~90 degree turns
            # and pushes the base midpoint aft of its neighbours. The arcs are
            # then clustered INTO the corner, so the short base cells do not sit
            # beside long surface cells.
            base = np.vstack([lower_le_to_te[-1], te_mid, upper_te_to_le[0]])
            pieces = [
                lower_le_to_te[lower_shoulder_idx:],
                base,
                upper_te_to_le[: upper_shoulder_idx + 1],
            ]
            allocation = _split_counts(pieces, n, {1: te_base_points})
            sides.append(
                _resample_piecewise(
                    pieces,
                    allocation,
                    distribution=["cluster_end", "uniform", "cluster_start"],
                    beta=chordwise_beta,
                )
            )
        else:
            sides.append(_resample_polyline(side, n, distribution=mode, beta=chordwise_beta))

    for k in range(4):
        nxt = (k + 1) % 4
        if not np.allclose(sides[k][-1], sides[nxt][0], atol=1e-12):
            raise MeshBuildError("cap4 side corners are disconnected.")

    # Index of each blunt-base corner inside the TE wrap side, located
    # geometrically rather than assumed, so it survives any resampling choice.
    te = sides[2]
    k_low = int(np.argmin(np.linalg.norm(te - lower_le_to_te[-1], axis=1)))
    k_up = int(np.argmin(np.linalg.norm(te - upper_te_to_le[0], axis=1)))
    if k_low > k_up:
        k_low, k_up = k_up, k_low
    meta = {"te_base_index_lower": k_low, "te_base_index_upper": k_up,
            "n_te_wrap": len(te), "n_nose_wrap": len(sides[0])}
    return sides, meta


# ---------------------------------------------------------------------------
# S0's spanwise law
# ---------------------------------------------------------------------------


def refine_spanwise(blocks: list[Array], panels_per_section: int, *, allocation: str) -> list[Array]:
    """Subdivide each spanwise interval.

    ``allocation="proportional"`` is what the production recipe uses and it
    matters: the generator's sections are not equally spaced, so giving every
    interval the same panel count makes cell size jump wherever section spacing
    changes — a measured 1.50x step at one kink, which was the whole of the
    mesh's spanwise growth ratio. Proportional allocation spends one budget in
    proportion to each interval's spanwise extent instead.

    New columns are linear blends of their bounding station columns. That is an
    approximation of a spline loft and it has a measured fidelity cost
    (COMMON_BRIEF section 9.5); cap4 has always done this, refining 17 native
    stations to 255.
    """
    if panels_per_section < 1:
        raise MeshBuildError("panels_per_section must be at least 1.")
    if allocation not in ("uniform", "proportional"):
        raise MeshBuildError("allocation must be 'uniform' or 'proportional'.")

    n_intervals = blocks[0].shape[1] - 1
    if allocation == "proportional":
        centroids = np.stack(
            [
                np.mean(np.concatenate([b[:, j, :] for b in blocks], axis=0), axis=0)
                for j in range(n_intervals + 1)
            ]
        )
        lengths = np.linalg.norm(np.diff(centroids, axis=0), axis=1)
        total = float(lengths.sum()) or 1.0
        budget = panels_per_section * n_intervals
        raw = np.maximum(1, np.round(budget * lengths / total).astype(int))
        panels = [int(v) for v in raw]
    else:
        panels = [panels_per_section] * n_intervals

    out = []
    for blk in blocks:
        cols = []
        for j, n_panels in enumerate(panels):
            for k in range(n_panels):
                s = k / float(n_panels)
                cols.append((1.0 - s) * blk[:, j, :] + s * blk[:, j + 1, :])
        cols.append(blk[:, -1, :])
        out.append(np.stack(cols, axis=1))
    return out, panels


# ---------------------------------------------------------------------------
# S0's tip closure: the one-block airfoil face
# ---------------------------------------------------------------------------


def airfoil_face_tip(oml_blocks: list[Array], *, blend_points: int, smooth_iters: int):
    """One structured quad block covering the whole tip face.

    Its boundary IS the four OML tip edges, so the tip is watertight by
    construction — the closure never resamples the section a second time
    (COMMON_BRIEF section 9.4).

    A plain TFI over this boundary folds at the LE/TE shoulders when the wrap
    edge is strongly curved. Instead the patch starts as a lower-to-upper ruled
    surface and the curved end columns are propagated a short distance inward
    under a power law, keeping the effect local and avoiding the concave
    first/last cells an abrupt wrap-to-thickness transition creates. All four
    boundaries are then restored exactly.
    """
    if len(oml_blocks) != 4:
        raise MeshBuildError("the airfoil-face closure requires exactly 4 OML blocks.")

    e_nose = oml_blocks[0][:, -1, :]  # upper shoulder -> LE -> lower shoulder
    e_low = oml_blocks[1][:, -1, :]  # lower nose shoulder -> lower TE shoulder
    e_te = oml_blocks[2][:, -1, :]  # lower TE shoulder -> TE base -> upper shoulder
    e_up = oml_blocks[3][:, -1, :]  # upper TE shoulder -> upper nose shoulder
    n_wrap, n_chord = len(e_nose), len(e_low)
    if len(e_te) != n_wrap or len(e_up) != n_chord:
        raise MeshBuildError("airfoil-face tip edges have inconsistent point counts.")

    lower = e_low
    upper = e_up[::-1]
    nose_col = e_nose[::-1]  # lower -> upper
    te_col = e_te  # lower -> upper

    v = np.linspace(0.0, 1.0, n_wrap)[None, :, None]
    ruled = (1.0 - v) * lower[:, None, :] + v * upper[:, None, :]

    s = np.linspace(0.0, 1.0, n_chord)[:, None, None]
    blend_power = max(4.0, 40.0 / float(blend_points))
    patch = (
        ruled
        + (1.0 - s) ** blend_power * (nose_col - ruled[0])[None, :, :]
        + s**blend_power * (te_col - ruled[-1])[None, :, :]
    )
    patch[0, :, :] = nose_col
    patch[-1, :, :] = te_col
    patch[:, 0, :] = lower
    patch[:, -1, :] = upper

    if smooth_iters:
        patch = _smooth_patch_interior(patch, smooth_iters)
    return patch


# ---------------------------------------------------------------------------
# S0's developed tip closure: the shoulder-cornered collar cap
# ---------------------------------------------------------------------------
#
# WHY THE ONE-BLOCK FACE HAD TO GO (measured, `STUDY.md` section 4).
#
# The airfoil-face cap uses the four OML tip edges as the four sides of ONE
# structured block. Two of those edges — the nose wrap and the TE wrap — are
# *chordwise-extended arcs*: the nose wrap covers x/c 0 to wrap_x on both
# surfaces, and the TE wrap covers 1-wrap_x to the blunt base and back. Using
# them as the block's first and last index COLUMNS squashes 15% of chord (30%
# at the TE, counting both surfaces) into a single cell width. Measured on
# lhs7_00 at L2_smoke: chordwise spacing runs ~4 mm through the interior and
# the last column reaches 0.15c beyond its neighbour. It cannot not fold.
#
# The folded cells are exactly there — i = 30, 31 of 32 — and no amount of
# relaxation helps, because it is a boundary problem, not a distribution one.
# TFI, Laplacian and Winslow smoothing were all measured; every elliptic
# variant converges to the same -0.02345, which is what an elliptic solver
# doing its job looks like when the boundary itself is the defect:
#
#     ruled + blend (shipped)      -0.02345      TFI                  -0.18446
#     ruled + blend + smooth 20    -0.03340      TFI + smooth 20      -0.12631
#     ruled + blend + winslow 1e3  -0.02345      TFI + winslow 1e3    -0.02345
#                                                TFI + winslow 3e3    -0.02345
#
# Widening wrap_x helps monotonically (-0.060 at 0.03 to -0.006 at 0.40) and
# never reaches zero, while cell-size range explodes from 123x to 756x — it
# buys shape with marchability, which is the trade ADR-0010 warns about.
#
# THE FIX, AND WHY IT IS STILL S0.
#
# Each OML tip edge gets its own collar block joining it to an inner boundary,
# with a central quad inside. Two things follow:
#
# 1. The wrap regions are resolved along their own arcs instead of being
#    squashed into one column.
# 2. At each shoulder node TWO collars meet, so the ~180 degree contour angle
#    is split into two ~90 degree block corners. That is what makes the corner
#    survivable without moving it off the smooth contour — and moving it is not
#    available to S0, because corners at x/c = wrap_x and 1-wrap_x ARE cap4.
#
# The corner policy is cap4's own and is what keeps this distinct from S1:
# S1 corners its cap on the leading edge and the two blunt-TE base corners,
# and sizes one camber-aligned rectangle plus four near-uniform collars. S0
# corners on its four OML shoulders at +/- wrap_x, inherits cap4's unequal
# 15/33/15/33 edge counts, and its collars are consequently two long and two
# short. Same family — any all-quad cap of a closed contour is — but a
# different corner policy, a different block sizing, and a different failure
# mode if it is wrong.
#
# The inner boundary follows COMMON_BRIEF section 1: it is built FROM THE
# SECTION as `camber + width_frac * (surface - camber)`, a convex combination
# that lies inside the section by construction. It is NOT derived by displacing
# the outer ring; about fifteen constructions that did that all failed.


def _camber_and_surfaces(coords: Array, le_index: int, x_query: Array):
    """Camber and the two surfaces of a 2D section at requested x/c stations."""
    upper = coords[: le_index + 1][::-1]  # LE -> upper TE
    lower = coords[le_index:]  # LE -> lower TE
    zu = np.interp(x_query, upper[:, 0], upper[:, 1])
    zl = np.interp(x_query, lower[:, 0], lower[:, 1])
    return 0.5 * (zu + zl), zu, zl


def shoulder_collar_tip_2d(
    sides_2d: list[Array],
    coords: Array,
    le_index: int,
    *,
    wrap_x: float,
    width_frac: float,
    x_fore: float,
    x_aft: float,
    wrap_bulge: float,
    split_te_base: bool,
    collar_points: int,
) -> tuple[list[Array], dict]:
    """S0's five-block tip cap, built in the 2D section frame.

    ``sides_2d`` are the tip section's four cap4 sides, so the cap's outer
    boundary is the OML tip edge node-for-node and the tip is watertight by
    construction (COMMON_BRIEF section 9.4).
    """
    e_nose, e_low, e_te, e_up = sides_2d
    n_wrap, n_chord = len(e_nose), len(e_low)
    if len(e_te) != n_wrap or len(e_up) != n_chord:
        raise MeshBuildError("cap4 tip sides have inconsistent point counts.")
    if collar_points < 3:
        raise MeshBuildError("collar_points must be at least 3.")
    if not (0.05 <= width_frac <= 0.95):
        raise MeshBuildError("width_frac must lie between 0.05 and 0.95.")

    # The inner boundary is a band spanning [x_fore, x_aft] in chord, built FROM
    # THE SECTION as `camber + width_frac * (surface - camber)` — a convex
    # combination, so it lies inside the section by construction (COMMON_BRIEF
    # section 1). The two wrap ends are closed with straight thickness lines.
    #
    # `x_fore` and `x_aft` are INDEPENDENT of the OML shoulders at wrap_x and
    # 1-wrap_x, and that independence is the whole point: they set each collar's
    # chordwise depth. Tying the aft limit to the shoulder (x_aft = 0.82) forced
    # `tip_collar_te` to span from x/c 0.82 out to the blunt base at 1.0 and back
    # — a depth of 0.18c against 0.03c for the other collars — and that one block
    # held the entire surface back at +0.029, aspect ratio 18.0, skewness 0.982,
    # while every other block sat above +0.18.
    #
    # A contracted-ring inner boundary (every outer point mapped inward in both
    # chord and thickness, so each collar keeps a uniform width) was built and
    # measured as the alternative. It is WORSE across the whole parameter space —
    # best -0.020 against this construction's +0.029 — because contracting the
    # long chord arcs redistributes their points unevenly. Recorded in STUDY.md
    # as a rejected construction, not deleted.
    # HARD CONSTRAINT, found by measurement. The inner band must lie strictly
    # INSIDE the OML shoulders. Push x_fore forward of wrap_x, or x_aft aft of
    # 1-wrap_x, and the corresponding collar turns inside out: measured -0.996
    # at x_fore 0.10 against wrap_x 0.15, and -0.999 at x_aft 0.94 against a
    # shoulder at 0.85.
    #
    # The consequence is the design driver for this cap: each wrap collar's
    # chordwise depth is fixed at `wrap_x` by cap4's own corner policy. The TE
    # collar must reach from the shoulder at 1-wrap_x out to the blunt base, a
    # depth of exactly wrap_x. SMALL wrap_x therefore makes both wrap collars
    # shallow and well-shaped — the opposite of what wrap_x does for the shipped
    # one-block face, where widening it helped monotonically.
    if not (wrap_x < x_fore < x_aft < 1.0 - wrap_x):
        raise MeshBuildError(
            f"inner band [{x_fore:.4f}, {x_aft:.4f}] must lie strictly inside the "
            f"OML shoulders [{wrap_x:.4f}, {1.0 - wrap_x:.4f}]"
        )

    xs = np.linspace(x_fore, x_aft, n_chord)
    camber, zu, zl = _camber_and_surfaces(coords, le_index, xs)
    inner_up = np.column_stack([xs, camber + width_frac * (zu - camber)])
    inner_low = np.column_stack([xs, camber + width_frac * (zl - camber)])

    def _straight(p0: Array, p1: Array, n: int) -> Array:
        s = np.linspace(0.0, 1.0, n)[:, None]
        return (1.0 - s) * p0 + s * p1

    # Inner arcs, wound the same way as their outer partners.
    #
    # The two wrap ends are NOT straight lines. A straight inner boundary against
    # a wrap arc that bulges 0.17c gives a collar whose width runs from 0.02c at
    # its ends to 0.17c at its middle — measured as aspect ratio 18.0, skewness
    # 0.982, and the single block holding the whole surface back. `wrap_bulge`
    # gives the inner arc the same SHAPE as its outer partner, scaled: the outer
    # arc's deviation from its own end-to-end chord is copied at `wrap_bulge` of
    # full size onto the inner straight line. At 0 this is the straight line; at
    # 1 the inner arc would touch the outer one. The collar width becomes near
    # uniform without touching the two long chord arcs, which is what a global
    # ring contraction got wrong — it redistributed those arcs' points and made
    # everything worse (-0.020 against +0.029).
    #
    # MEASURED, AND THE DEFAULT IS 0.0: bulging the inner wrap arcs helps the
    # collars and wrecks the CENTRE block, which is bounded by those same arcs.
    # Every value above zero is worse, monotonically — +0.034 at 0.0, +0.022 at
    # 0.3, -0.030 at 0.5, -0.056 at 0.65, -0.194 at 0.8 — because a rearward
    # bulging edge on a TFI patch folds it. The knob is kept, set to zero, so the
    # negative result stays reproducible rather than merely written down.
    def _wrap_arc(outer_arc: Array, p0: Array, p1: Array) -> Array:
        n = len(outer_arc)
        base = _straight(p0, p1, n)
        chord = _straight(outer_arc[0], outer_arc[-1], n)
        return base + wrap_bulge * (outer_arc - chord)

    i_nose = _wrap_arc(e_nose, inner_up[0], inner_low[0])  # upper -> lower
    i_low = inner_low  # fore -> aft
    i_te = _wrap_arc(e_te, inner_low[-1], inner_up[-1])  # lower -> upper
    i_up = inner_up[::-1]  # aft -> fore

    outer = [e_nose, e_low, e_te, e_up]
    inner = [i_nose, i_low, i_te, i_up]
    names = ["tip_collar_nose", "tip_collar_lower", "tip_collar_te", "tip_collar_upper"]

    # SPLIT THE TE COLLAR AT THE TWO BLUNT-BASE CORNERS.
    #
    # Without this the TE collar has to march radially inward from an arc that
    # turns through ~180 degrees over the blunt base — radius te_thickness/2,
    # about 0.0025c — to a depth of `wrap_x`, about 0.15c. That is an offset
    # curve taken sixty times its own radius of curvature, and it self-
    # intersects. The signature is unmistakable and was measured layer by layer:
    # quality decays MONOTONICALLY inward and crosses zero part-way, at the
    # middle of the arc, which is the base:
    #
    #   L2 (7 radial)   +0.390 +0.174 +0.100 +0.062 +0.040 +0.025
    #   L3 (9 radial)   +0.491 +0.217 +0.117 +0.066 +0.037 +0.017 +0.003 -0.008
    #   L5 (17 radial)  +0.586 ... +0.016 -0.001 -0.014 ... -0.058
    #
    # Refining makes it worse, because more radial layers reach further in
    # before meeting the inner boundary. No parameter fixes it: shrinking wrap_x
    # to 0.03 does make the collar shallow enough to stay positive and even to
    # IMPROVE with refinement (+0.092 -> +0.106), but the cell-size range then
    # runs to 545x, which trades the shape gate for marchability — the exact
    # trade ADR-0010 warns against.
    #
    # Splitting at the base corners removes the tight turn from the interior of
    # an arc and makes it a block CORNER, where the section's own interior angle
    # is about 90 degrees and two sub-collars share it. Each sub-collar then
    # offsets from a gently curved arc. cap4's OML corner policy is untouched —
    # the four OML blocks still corner at +/- wrap_x — so this is a refinement of
    # the cap's internal blocking, not a change of strategy.
    if split_te_base:
        te_low_corner = coords[-1]
        te_up_corner = coords[0]
        k_low = int(np.argmin(np.linalg.norm(e_te - te_low_corner, axis=1)))
        k_up = int(np.argmin(np.linalg.norm(e_te - te_up_corner, axis=1)))
        if k_low > k_up:
            k_low, k_up = k_up, k_low
        if k_low < 1 or k_up > len(e_te) - 2 or k_up - k_low < 1:
            raise MeshBuildError(
                f"blunt-base corners at indices {k_low}, {k_up} of a {len(e_te)}-point TE "
                "arc leave no room to split; raise wrap_points or te_base_points."
            )
        cuts = [(0, k_low), (k_low, k_up), (k_up, len(e_te) - 1)]
        sub_names = ["tip_collar_te_lower", "tip_collar_te_base", "tip_collar_te_upper"]
        te_outer = [e_te[a : b + 1] for a, b in cuts]
        te_inner = [i_te[a : b + 1] for a, b in cuts]
        outer = [e_nose, e_low, *te_outer, e_up]
        inner = [i_nose, i_low, *te_inner, i_up]
        names = ["tip_collar_nose", "tip_collar_lower", *sub_names, "tip_collar_upper"]

    patches = []
    for o, n in zip(outer, inner, strict=True):
        left = _straight(o[0], n[0], collar_points)
        right = _straight(o[-1], n[-1], collar_points)
        patches.append(_tfi_patch(bottom=o, top=n, left=left, right=right))

    centre = _tfi_patch(bottom=i_low, top=i_up[::-1], left=i_nose[::-1], right=i_te)
    patches.append(centre)
    names.append("tip_centre")

    patches, flipped = orient_patches_2d(patches)
    info = {
        "topology": (
            "cap4_shoulder_collar_seven_block" if split_te_base
            else "cap4_shoulder_collar_five_block"
        ),
        "block_names": names,
        "width_frac": width_frac,
        "inner_band_x": [float(x_fore), float(x_aft)],
        "wrap_bulge": wrap_bulge,
        "split_te_base": bool(split_te_base),
        "collar_points": int(collar_points),
        "corner_policy": "cap4 shoulders at +/- wrap_x; two collars meet at each",
        "orientation_flipped": flipped,
        "outer_boundary": "exact OML tip-edge nodes",
    }
    return patches, info


def base_cornered_tip_2d(
    sides_2d: list[Array],
    meta: dict,
    coords: Array,
    le_index: int,
    *,
    width_frac: float,
    x_fore: float,
    x_aft: float,
    collar_points: int,
) -> tuple[list[Array], dict]:
    """S0's refined tip cap: ring corners at the shoulders AND the base corners.

    The shoulder-collar cap put the whole TE wrap into one collar, so that collar
    had to turn 180 degrees around the blunt base — radius te_thickness/2, about
    0.0025c — inside its own interior. Quality decayed monotonically inward and
    crossed zero (STUDY.md section 6), and every attempt to resolve it better made
    it worse, because more points in a 0.005c feature means smaller cells and
    ADR-0010 says the smallest cell governs the march.

    Here the two blunt-base corners become ring CORNERS. The turn stops being
    something a collar must interpolate through and becomes something two collars
    share, each seeing about half of it. The ring is regrouped as:

        A  nose wrap     upper shoulder -> LE -> lower shoulder
        B  lower run     lower shoulder -> ... -> LOWER BASE CORNER
        C  blunt base    lower base corner -> upper base corner
        D  upper run     upper base corner -> ... -> upper shoulder

    B and D each span two OML blocks, which is allowed: a cap block may cross an
    OML block boundary, it only has to land on the same nodes.

    Opposite arcs must pair for the centre TFI, so **len(A) == len(C)**: the nose
    wrap and the blunt base carry the same point count. That is why `cap4_sides`
    had to decouple the nose and TE wrap counts — the TE wrap needs enough points
    to pin both base corners with arc points either side, while the nose wrap must
    stay coarse or it manufactures tiny leading-edge cells.

    The OML blocking is untouched: four blocks, corners at +/- wrap_x. This is a
    refinement of the cap's internal blocking only.
    """
    e_nose, e_low, e_te, e_up = sides_2d
    k_low, k_up = meta["te_base_index_lower"], meta["te_base_index_upper"]
    if k_low < 1 or k_up > len(e_te) - 2:
        raise MeshBuildError(
            f"blunt-base corners at {k_low},{k_up} of a {len(e_te)}-point TE wrap "
            "leave no arc points outside them; raise te_wrap_points."
        )

    a_out = e_nose
    b_out = np.vstack([e_low, e_te[1 : k_low + 1]])
    c_out = e_te[k_low : k_up + 1]
    d_out = np.vstack([e_te[k_up:], e_up[1:]])
    if len(a_out) != len(c_out):
        raise MeshBuildError(
            f"nose wrap has {len(a_out)} points and the blunt base has {len(c_out)}; "
            "they are opposite arcs of the cap and must match."
        )
    if len(b_out) != len(d_out):
        raise MeshBuildError(
            f"lower run {len(b_out)} vs upper run {len(d_out)}: the TE wrap must "
            "split symmetrically about the blunt base."
        )

    # The inner run must follow the OUTER run's spacing, not a uniform grid in
    # x. The outer run spans the chord side plus part of the TE wrap, so its
    # points crowd hard against the blunt base; an inner boundary sampled
    # uniformly in x shears every collar cell against that crowding. Measured:
    # skewness 0.999-1.000 and min scaled Jacobian -0.049 at best, always in a
    # run collar. Matching arc-length fractions removes the shear.
    def _arc_fractions(curve: Array) -> Array:
        seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        return cum / (cum[-1] or 1.0)

    s_low = _arc_fractions(b_out)
    s_up = _arc_fractions(d_out[::-1])
    xs_low = x_fore + (x_aft - x_fore) * s_low
    xs_up = x_fore + (x_aft - x_fore) * s_up
    c_lo, _zu, zl_lo = _camber_and_surfaces(coords, le_index, xs_low)
    c_up, zu_up, _zl = _camber_and_surfaces(coords, le_index, xs_up)
    inner_low = np.column_stack([xs_low, c_lo + width_frac * (zl_lo - c_lo)])
    inner_up = np.column_stack([xs_up, c_up + width_frac * (zu_up - c_up)])

    def _straight(p0: Array, p1: Array, n: int) -> Array:
        t = np.linspace(0.0, 1.0, n)[:, None]
        return (1.0 - t) * p0 + t * p1

    a_in = _straight(inner_up[0], inner_low[0], len(a_out))
    b_in = inner_low
    c_in = _straight(inner_low[-1], inner_up[-1], len(c_out))
    d_in = inner_up[::-1]
    a_in[-1] = b_in[0]
    a_in[0] = d_in[-1]
    c_in[0] = b_in[-1]
    c_in[-1] = d_in[0]

    outer = [a_out, b_out, c_out, d_out]
    inner = [a_in, b_in, c_in, d_in]
    names = ["tip_collar_nose", "tip_collar_lower", "tip_collar_base", "tip_collar_upper"]

    patches = []
    for o, n in zip(outer, inner, strict=True):
        patches.append(
            _tfi_patch(
                bottom=o, top=n,
                left=_straight(o[0], n[0], collar_points),
                right=_straight(o[-1], n[-1], collar_points),
            )
        )
    patches.append(_tfi_patch(bottom=b_in, top=d_in[::-1], left=a_in[::-1], right=c_in))
    names.append("tip_centre")

    patches, flipped = orient_patches_2d(patches)
    info = {
        "topology": "cap4_base_cornered_five_block",
        "block_names": names,
        "width_frac": width_frac,
        "inner_band_x": [float(x_fore), float(x_aft)],
        "collar_points": int(collar_points),
        "ring_corners": "two OML shoulders (nose side) + the two blunt-base corners",
        "arc_points": [len(a_out), len(b_out), len(c_out), len(d_out)],
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

OML_NAMES = ["oml_nose_wrap", "oml_lower", "oml_te_wrap", "oml_upper"]
TIP_NAME = "tip_airfoil_face"


def build_surface(
    wing,
    *,
    level: str = "L2_smoke",
    wrap_x: float = WRAP_X,
    te_thickness_abs_m: float = TE_THICKNESS_ABS_M,
    te_base_points: int = 0,
    chordwise_distribution: str = "uniform",
    chordwise_beta: float = 2.0,
    tip_smooth_iters: int = TIP_SMOOTH_ITERS,
    spanwise_allocation: str = SPANWISE_ALLOCATION,
    tip_closure: str = "shoulder_collar",
    te_wrap_points: int | None = None,
    collar_points_override: int | None = None,
    width_frac: float = 0.35,
    chord_inset: float = 0.01,
    te_arc_points: int = 2,
    wrap_bulge: float = 0.0,
    split_te_base: bool = False,
    **level_overrides,
) -> tuple[list[SurfaceBlock], dict]:
    """Build S0's cap4 surface.

    ``tip_closure`` selects the tip cap:

    ``"shoulder_collar"``  S0's developed five-block cap (default, and the best
                           measured: +0.19113).
    ``"base_cornered"``    ring corners at the shoulders AND the two blunt-base
                           corners, so the 180 degree base turn is a block corner
                           rather than a collar interior. Built, swept and
                           REJECTED: best -0.04917 against +0.19113, with skewness
                           0.998-1.000 in a run collar at every setting. Matching
                           the inner boundary to the outer arc-length distribution
                           changed almost nothing (-0.0538 -> -0.0537), which is
                           what identifies the cause: the blunt base is a
                           0.005-chord feature and any block edge reaching from it
                           to the cap interior is stretched, whatever the
                           parameterisation. Kept selectable so the result stays
                           reproducible.
    ``"airfoil_face"``     the shipped one-block cap, kept so its failure stays
                           reproducible rather than merely recorded. It does not
                           pass the surface gate on any geometry or setting
                           measured so far.
    """
    if level not in LEVELS:
        raise MeshBuildError(f"unknown level {level!r}; known: {sorted(LEVELS)}")
    cfg = dict(LEVELS[level])
    cfg.update({k: v for k, v in level_overrides.items() if v is not None})
    if "wrap_points" not in level_overrides:
        cfg["wrap_points"] = wrap_points_for(cfg["chord_points"], wrap_x)

    xsecs = list(wing.xsecs)
    if len(xsecs) < 2:
        raise MeshBuildError("S0 needs at least two spanwise stations.")

    sides_by_xsec = []
    tip_coords = tip_le_index = tip_meta = None
    for xsec in xsecs:
        coords, le_index = section_loop_2d(xsec, te_thickness_abs_m=te_thickness_abs_m)
        tip_coords, tip_le_index = coords, le_index
        # The blunt base carries `wrap_points` so it pairs with the nose wrap
        # (they are opposite arcs of the cap), and the TE wrap carries enough
        # extra points to leave real arc either side of it.
        n_base = cfg["wrap_points"] if tip_closure == "base_cornered" else te_base_points
        n_te_wrap = te_wrap_points or (
            cfg["wrap_points"] + 2 * te_arc_points if tip_closure == "base_cornered" else None
        )
        sides, meta = cap4_sides(
            coords,
            le_index,
            wrap_x=wrap_x,
            chord_points=cfg["chord_points"],
            wrap_points=cfg["wrap_points"],
            te_base_points=n_base,
            te_wrap_points=n_te_wrap,
            chordwise_distribution=chordwise_distribution,
            chordwise_beta=chordwise_beta,
        )
        sides_by_xsec.append(sides)
        tip_meta = meta

    oml = _map_sides_to_wing(wing, sides_by_xsec)
    oml, panels = refine_spanwise(
        oml, cfg["spanwise_panels"], allocation=spanwise_allocation
    )

    blocks = [SurfaceBlock(name=n, xyz=b, family="wall") for n, b in zip(OML_NAMES, oml, strict=True)]

    if tip_closure == "airfoil_face":
        tip = airfoil_face_tip(
            oml, blend_points=cfg["tip_blend_points"], smooth_iters=tip_smooth_iters
        )
        blocks.append(SurfaceBlock(name=TIP_NAME, xyz=tip, family="wall"))
        cap_info = {"topology": "one_block_airfoil_face", "block_names": [TIP_NAME]}
    elif tip_closure == "base_cornered":
        cap_2d, cap_info = base_cornered_tip_2d(
            sides_by_xsec[-1], tip_meta, tip_coords, tip_le_index,
            width_frac=width_frac,
            x_fore=wrap_x + chord_inset,
            x_aft=1.0 - chord_inset,
            collar_points=collar_points_override or cfg["tip_blend_points"],
        )
        blocks += [
            SurfaceBlock(name=n, xyz=map_patch_2d_to_tip(wing, p), family="wall")
            for n, p in zip(cap_info["block_names"], cap_2d, strict=True)
        ]
    elif tip_closure == "shoulder_collar":
        cap_2d, cap_info = shoulder_collar_tip_2d(
            sides_by_xsec[-1],
            tip_coords,
            tip_le_index,
            wrap_x=wrap_x,
            width_frac=width_frac,
            x_fore=wrap_x + chord_inset,
            x_aft=(1.0 - wrap_x) - chord_inset,
            wrap_bulge=wrap_bulge,
            split_te_base=split_te_base,
            collar_points=collar_points_override or cfg["tip_blend_points"],
        )
        blocks += [
            SurfaceBlock(name=n, xyz=map_patch_2d_to_tip(wing, p), family="wall")
            for n, p in zip(cap_info["block_names"], cap_2d, strict=True)
        ]
    else:
        raise MeshBuildError(
            f"unknown tip_closure {tip_closure!r}; use 'base_cornered', "
            "'shoulder_collar' or 'airfoil_face'"
        )

    blocks, orientation = orient_blocks_consistently(blocks)

    info = {
        "strategy_id": STRATEGY_ID,
        "level": level,
        "level_settings": cfg,
        "wrap_x": wrap_x,
        "te_thickness_abs_m": te_thickness_abs_m,
        "te_base_points": te_base_points,
        "chordwise_distribution": chordwise_distribution,
        "tip_smooth_iters": tip_smooth_iters,
        "spanwise": {
            "allocation": spanwise_allocation,
            "panels_per_interval": panels,
            "spanwise_cells": int(sum(panels)),
            "native_stations": len(xsecs),
        },
        "oml_block_names": OML_NAMES,
        "tip_block_names": cap_info["block_names"],
        "tip_closure": tip_closure,
        "tip_cap_info": cap_info,
        "orientation": orientation,
        "corner_policy": (
            "OML corners at x/c = wrap_x and 1-wrap_x on both surfaces; LE and TE "
            "base sit in block interiors. The four corners therefore lie on smooth "
            "contour, which is cap4's known weakness (ADR-0006)."
        ),
    }
    return blocks, info
