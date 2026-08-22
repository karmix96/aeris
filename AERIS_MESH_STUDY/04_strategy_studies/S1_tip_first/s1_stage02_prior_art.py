"""S1's private construction — tip closure and spanwise distribution.

ADR-0011 section 4.1 moved these out of the Stage 02 shared module. They are S1's
blocking decisions, not infrastructure: `butterfly_from_ring` is a tip closure,
`oml_tip_ring_2d` is tip staging, `realise_spanwise_law` and
`geometric_progression_counts` are a spanwise distribution law, and
`butterfly_cap_2d` / `camber_and_thickness` / `map_2d_patch_to_tip` are S1 cap
internals. Under the independence line no other strategy may import from this file.

Migrated byte-for-byte from `04_strategy_prototypes/stage02_common.py`. Docstrings
still describe the Stage 02 development history, including `butterfly_cap_2d`,
which is a **recorded negative result** kept for provenance and is not on S1's
working path.

NOTE for the S1 study: this file is the Stage 02 implementation. ADR-0011 requires
S1 to be re-implemented from scratch like every other strategy. Treat this as the
prior art to read and beat, not as the S1 entry.
"""

from __future__ import annotations

import numpy as np

from shared.ingestion import (
    Array,
    MeshBuildError,
    _open_trailing_edge,
    _map_sides_to_wing,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    _tfi_patch,
)
from shared.qc import orient_patches_2d


def feature_split_sides(
    coords: Array,
    le_index: int,
    *,
    chord_points: int,
    te_base_points: int,
    distribution: str,
    beta: float = 2.0,
) -> list[Array]:
    """Split a section into sides whose corners are all genuine features.

    Returns three sides in order: upper (LE -> upper TE), lower (LE -> lower TE),
    and the blunt TE base as its own short side. Corners land on the leading edge
    and on the two trailing-edge base corners - all real curvature features.

    SHARED CONTROL (ADR-0011 section 4). This function is ingestion: it turns the
    generator's section into side curves. It does NOT choose a chordwise law.
    ``distribution``, ``beta`` and ``te_base_points`` are **required** and must be
    supplied by the calling strategy, because chordwise clustering and point
    allocation are per-strategy under the independence line. Stage 02 defaulted
    these to S1's answers, which is exactly what ADR-0011 exists to prevent.

    COMMON_BRIEF section 9.2 records the measurement behind S1's own choice - on
    lhs7_00, cosine gave a 396x cell-size range and uniform gave 99x - as prior
    knowledge available to every strategy, not as a default.
    """
    upper = coords[: le_index + 1][::-1]  # LE -> upper TE
    lower = coords[le_index:]  # LE -> lower TE
    te_top = upper[-1]
    te_bot = lower[-1]

    upper_r = _resample_polyline(upper, chord_points, distribution=distribution, beta=beta)
    lower_r = _resample_polyline(lower, chord_points, distribution=distribution, beta=beta)
    base = _resample_polyline(
        np.vstack([te_bot, te_top]), max(2, int(te_base_points)), distribution="uniform", beta=1.0
    )
    return [upper_r, lower_r, base]


def geometric_progression_counts(
    lengths: list[float],
    *,
    target_cell: float,
    growth_limit: float = 1.2,
    minimum: int = 3,
) -> list[int]:
    """Spanwise point counts from physical segment length.

    RUNBOOK S1 requires spanwise counts to come from physical segment length and
    a geometric-progression law rather than a fixed panel count. Counts are then
    reconciled so that adjacent segments never differ by more than
    ``growth_limit``, which is the abrupt-size-transition failure Openblademesh
    warns about.
    """
    raw = [max(minimum, int(round(length / max(target_cell, 1e-12))) + 1) for length in lengths]
    for _ in range(len(raw) * 2):
        changed = False
        for i in range(len(raw) - 1):
            hi, lo = max(raw[i], raw[i + 1]), min(raw[i], raw[i + 1])
            if hi > lo * growth_limit:
                capped = int(np.ceil(lo * growth_limit))
                if raw[i] > raw[i + 1]:
                    raw[i] = capped
                else:
                    raw[i + 1] = capped
                changed = True
        if not changed:
            break
    return raw


def camber_and_thickness(coords: Array, le_index: int, x_query: Array) -> tuple[Array, Array]:
    """Camber z and half-thickness of a 2D section at given x/c stations."""
    upper = coords[: le_index + 1][::-1]  # LE -> upper TE
    lower = coords[le_index:]  # LE -> lower TE
    zu = np.interp(x_query, upper[:, 0], upper[:, 1])
    zl = np.interp(x_query, lower[:, 0], lower[:, 1])
    return 0.5 * (zu + zl), 0.5 * (zu - zl)


def _point_at_x(curve: Array, x: float) -> Array:
    """Point on a monotone-in-x curve at the requested x."""
    return np.array([x, float(np.interp(x, curve[:, 0], curve[:, 1]))])


def _arc_between_x(curve: Array, x0: float, x1: float, count: int) -> Array:
    """Sub-arc of a monotone-in-x curve between two x stations, resampled."""
    lo, hi = min(x0, x1), max(x0, x1)
    mask = (curve[:, 0] > lo) & (curve[:, 0] < hi)
    arc = np.vstack([_point_at_x(curve, lo), curve[mask], _point_at_x(curve, hi)])
    if x1 < x0:
        arc = arc[::-1]
    return _resample_polyline(arc, count, distribution="uniform", beta=1.0)


def butterfly_cap_2d(
    coords: Array,
    le_index: int,
    *,
    ring_x_fore: float = 0.15,
    ring_x_aft: float = 0.85,
    offset_frac: float = 0.45,
    inner_smooth_iters: int = 40,
    patch_smooth_iters: int = 0,
    chord_points: int = 33,
    wrap_points: int = 17,
    radial_points: int = 7,
) -> tuple[list[Array], dict]:
    """All-quad butterfly (O-H) cap for a thin closed section, built in 2D.

    A single structured block cannot cap an airfoil section without a degenerate
    corner: the block needs four boundary corners, but the contour only offers
    the leading edge and the two blunt trailing-edge base corners, so at least
    one corner is forced onto a smooth part of the contour where the meeting
    edges are collinear. That is the ~180 degree corner that failed cap4 in
    Stage 01, and it is topological, not tunable (ADR-0006).

    Construction, in order:

    1. Work in a frame where z is normalized by the section half-thickness. An
       airfoil is roughly 10:1 thin, so a butterfly laid out in raw coordinates
       has diagonals nearly tangential to the contour. Normalizing makes the
       section roughly round. Scaling z back afterwards is a positive diagonal
       map, which changes aspect ratio but cannot reverse a cell.
    2. Build an inner ring by moving each contour point toward the camber line
       at the same chord station, so every radial connector follows the local
       inward normal and stays perpendicular to the contour. The camber target
       is clamped away from the leading and trailing edges, otherwise the
       offset collapses to a point there.
    3. Fill between the outer and inner rings with four side patches, and cap
       the middle with a transfinite core over the four inner arcs.

    Every block corner therefore carries one radial edge crossing the section,
    so no corner can be collinear with the contour.
    """
    z_scale = float(np.ptp(coords[:, 1])) / 2.0
    if z_scale <= 0.0:
        raise MeshBuildError("section has zero thickness.")
    coords = np.column_stack([coords[:, 0], coords[:, 1] / z_scale])

    upper = coords[: le_index + 1][::-1]  # LE -> upper TE
    lower = coords[le_index:]  # LE -> lower TE
    if not (0.0 < ring_x_fore < ring_x_aft < 1.0):
        raise MeshBuildError("butterfly cap requires 0 < ring_x_fore < ring_x_aft < 1.")

    # Ring split stations. Two placements were measured: splitting the aft arc
    # at a smooth station (below) leaves the two blunt-TE corners inside the aft
    # arc and folds a few cells there; splitting exactly at the TE corners moves
    # the same fold into the lower arc instead. Neither clears it, and the
    # smooth-station variant is the milder of the two, so it is kept while the
    # tip closure stays an open defect.
    arc_upper = _arc_between_x(upper, ring_x_fore, ring_x_aft, chord_points)
    arc_lower = _arc_between_x(lower, ring_x_aft, ring_x_fore, chord_points)
    aft_pieces = [
        np.vstack([_point_at_x(upper, ring_x_aft), upper[upper[:, 0] > ring_x_aft]]),
        np.vstack([upper[-1], lower[-1]]),
        np.vstack([lower[lower[:, 0] > ring_x_aft][::-1], _point_at_x(lower, ring_x_aft)]),
    ]
    aft_alloc = _split_counts(aft_pieces, wrap_points, {1: max(3, int(round(wrap_points * 0.25)))})
    arc_aft = _resample_piecewise(
        aft_pieces, aft_alloc, distribution=["cluster_end", "uniform", "cluster_start"], beta=2.0
    )
    # The leading edge is shared by the reversed lower run and the upper run;
    # dropping the duplicate keeps the arc free of zero-length segments.
    fore_wrap = np.vstack(
        [
            _point_at_x(lower, ring_x_fore),
            lower[lower[:, 0] < ring_x_fore][::-1],
            upper[upper[:, 0] < ring_x_fore][1:],
            _point_at_x(upper, ring_x_fore),
        ]
    )
    arc_fore = _resample_polyline(fore_wrap, wrap_points, distribution="uniform", beta=1.0)
    arcs = [arc_upper, arc_aft, arc_lower, arc_fore]

    # The inner ring is a uniform shrink toward the section centroid, taken in
    # the thickness-normalized frame where the section is roughly round. A
    # camber-directed offset looks more natural but pinches to nothing at the
    # leading and trailing edges, which collapses the core block there; a
    # uniform shrink of a round shape cannot pinch.
    # Inner ring: uniform shrink toward the section centroid in the
    # thickness-normalized frame, then Laplacian smoothing of the closed ring.
    # Alternatives tried and rejected: a camber-directed offset pinches to
    # nothing at the leading and trailing edges and collapses the core block,
    # and an inward-bisector offset overshoots near the trailing edge and
    # inverts it completely. Only the outer ring is prescribed geometry; the
    # inner ring is free.
    ring = np.concatenate([arcs[k][:-1] for k in range(4)], axis=0)
    counts = [len(a_) for a_ in arcs]
    centroid = ring.mean(axis=0)
    ring = centroid + (1.0 - offset_frac) * (ring - centroid)
    for _ in range(max(0, int(inner_smooth_iters))):
        ring = 0.5 * ring + 0.25 * (np.roll(ring, 1, axis=0) + np.roll(ring, -1, axis=0))

    split, inner = 0, []
    for k in range(4):
        take = counts[k] - 1
        seg = ring[split : split + take]
        inner.append(np.vstack([seg, ring[(split + take) % len(ring)]]))
        split += take

    # Orientation matters: the side patches run j outward from the inner ring,
    # so the core must run j from the lower inner arc to the upper inner arc to
    # keep the same surface normal. Building it the other way round flips every
    # core cell.
    core = _tfi_patch(
        bottom=inner[2][::-1],
        top=inner[0],
        left=inner[3],
        right=inner[1][::-1],
    )

    patches = [core]
    radial = np.linspace(0.0, 1.0, max(3, int(radial_points)))[None, :, None]
    for k in range(4):
        patches.append((1.0 - radial) * inner[k][:, None, :] + radial * arcs[k][:, None, :])

    # Optional, default off. Measured: interior relaxation HURTS this cap
    # (worst scaled Jacobian -0.038 -> -0.191) because the side patches are
    # only 7-9 nodes thick radially, so averaging pulls nodes across them. It
    # helped the old cap4 collar, which was thicker. Kept as a knob, not a
    # default.
    # The remaining defect is a parameterisation mismatch, not a spacing one:
    # point i of the inner ring is displaced ALONG the ring rather than inward
    # from point i of the outer ring, so the connectors are not radial and the
    # cells against the blunt-TE corner come out as rhombi. surface.py already
    # solves this for the old cap4 collar - relax each patch interior toward
    # the average of its structured neighbours. Only interior nodes move, so
    # every block boundary, and therefore all connectivity, is preserved.
    patches = [_smooth_patch_interior(p, patch_smooth_iters) for p in patches]

    patches = [np.stack([p[..., 0], p[..., 1] * z_scale], axis=-1) for p in patches]

    info = {
        "topology": "butterfly_o_h_five_block",
        "block_names": ["tip_core", "tip_upper", "tip_aft_wrap", "tip_lower", "tip_fore_wrap"],
        "ring_x_fore": ring_x_fore,
        "ring_x_aft": ring_x_aft,
        "offset_frac": offset_frac,
        "inner_smooth_iters": int(inner_smooth_iters),
        "patch_smooth_iters": int(patch_smooth_iters),
        "z_scale": z_scale,
        "chord_points": int(chord_points),
        "wrap_points": int(wrap_points),
        "radial_points": int(radial_points),
        "arc_point_counts": [int(len(a)) for a in arcs],
        "rationale": (
            "inner ring generated by camber-directed offset so every radial edge follows the "
            "local inward normal; built in a thickness-normalized frame"
        ),
    }
    return patches, info


def _closed_arclength_fractions(ring: Array) -> Array:
    """Cumulative arc-length fraction of each node around a closed ring."""
    closed = np.vstack([ring, ring[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1] or 1.0
    return cum / total


def _match_closed_parameterisation(inner: Array, outer: Array) -> Array:
    """Re-sample a closed curve at another closed curve's arc-length fractions.

    Node counts are preserved, so block indexing and the arc split points are
    untouched; only where each inner node sits along its own curve changes.
    """
    s_in = _closed_arclength_fractions(inner)
    s_out = _closed_arclength_fractions(outer)
    closed = np.vstack([inner, inner[:1]])
    return np.column_stack(
        [np.interp(s_out[:-1], s_in, closed[:, 0]), np.interp(s_out[:-1], s_in, closed[:, 1])]
    )


def oml_tip_ring_2d(sides: list[Array]) -> tuple[Array, dict]:
    """Closed tip ring assembled from the OML side curves themselves.

    Watertightness is a hard gate and cannot be achieved by resampling the same
    contour twice: a cap that builds its own ring at a different point count
    never shares nodes with the OML tip edge, so every block passes QC alone and
    the assembled surface still has a hole. Building the ring FROM the OML sides
    makes the shared nodes identical by construction.

    ``sides`` is the output of :func:`feature_split_sides`: upper (LE -> TE top),
    lower (LE -> TE bottom) and the blunt base (TE bottom -> TE top).
    """
    upper, lower, base = sides
    n_chord = len(upper)
    n_base = len(base)
    if len(lower) != n_chord:
        raise MeshBuildError("upper and lower sides must have equal point counts.")
    if n_base % 2 == 0:
        raise MeshBuildError("te_base_points must be odd so the ring splits symmetrically.")

    # LE -> upper -> TE top -> base -> TE bottom -> lower back toward LE.
    ring = np.vstack([upper, base[::-1][1:], lower[::-1][1:-1]])
    idx_le = 0
    idx_te_top = n_chord - 1
    idx_te_bot = idx_te_top + (n_base - 1)
    total = len(ring)

    # Opposite butterfly arcs must have equal counts. Splitting at the two blunt
    # base corners fixes arcs 1 and 3 to the base and the leading-edge wrap, so
    # the wrap must span (n_base - 1) / 2 points either side of the leading edge.
    k = (n_base - 1) // 2
    if k < 1 or 2 * k + 1 > total:
        raise MeshBuildError("te_base_points too small for a leading-edge wrap arc.")
    corners = (k, idx_te_top, idx_te_bot, total - k)
    info = {
        "ring_points": int(total),
        "le_index": idx_le,
        "te_top_index": int(idx_te_top),
        "te_bottom_index": int(idx_te_bot),
        "corner_indices": [int(c) for c in corners],
        "arc_counts": [
            int(idx_te_top - k + 1),
            int(n_base),
            int(total - k - idx_te_bot + 1),
            int(2 * k + 1),
        ],
        "source": "OML side curves; no resampling, so tip-edge nodes are shared exactly",
    }
    return ring, info


def butterfly_from_ring(
    ring: Array,
    corners: tuple[int, int, int, int],
    *,
    width_frac: float = 0.30,
    chord_inset: float = 0.02,
    collar_points: int = 3,
    **_legacy,
) -> tuple[list[Array], dict]:
    """Camber-aligned tip cap over a ring whose nodes are fixed by the OML.

    This is the construction proven in commit bfaeaf1 ("cap4 camber-split tip
    cap - full-resolution pyHyp march validated at L1"), rebuilt here on the
    OML-locked ring. Two properties make it work, and every earlier attempt in
    this stage lacked both:

    1. **The inner boundary is built from the section, not from the outer ring.**
       ``rect = camber + width_frac * (surface - camber)`` is a convex
       combination of the camber line and the actual surface, so it lies inside
       the section BY CONSTRUCTION. Deriving the inner ring by shrinking,
       smoothing or offsetting the outer ring carries no such guarantee, and on
       a cambered lower surface it leaves the section and the patch inverts.

    2. **The inner rectangle is inset chordwise.** Without the inset the collar
       end edges are collinear with the rectangle's short sides, which
       degenerates the corner cells to zero Jacobian - the same ~180 degree
       corner that failed cap4 at the OML level.

    The cap is a chordwise rectangle aligned with the camber line plus four thin
    collars of near-uniform width joining it to the tip edge, so there are no
    long-side-to-short-side fans.

    ``collar_points`` defaults to 5, not 13. The blunt trailing edge is 4.70 mm
    wide at the root but only 0.78 mm at the tip, so a fixed radial count makes
    microscopic cells at the narrow end: 13 gave a smallest surface cell of
    11.9 um, BELOW pyHyp's first-layer height s0 of 13.4 um, and the march
    inverted at layer 2. 5 gives 29.9 um at the same minimum scaled Jacobian.
    Surface cell QUALITY and MARCHABILITY are different properties; optimising
    the first while ignoring the second is what produced a beautiful surface
    that could not be marched.
    """
    total = len(ring)
    idx = [int(c) % total for c in corners]
    arcs = []
    for a_, b_ in zip(idx, idx[1:] + idx[:1], strict=True):
        arcs.append(ring[a_ : b_ + 1] if b_ > a_ else np.vstack([ring[a_:], ring[: b_ + 1]]))

    # Re-express the four ring arcs in the orientation the proven cap uses.
    e_up = arcs[0][::-1]  # upper, TE -> nose
    e_te = arcs[1][::-1]  # trailing wrap, lower -> upper
    e_low = arcs[2][::-1]  # lower, nose -> TE
    e_nose = arcs[3][::-1]  # nose wrap, upper -> lower

    n_chord = len(e_low)
    n_wrap = len(e_nose)
    if len(e_up) != n_chord or len(e_te) != n_wrap:
        raise MeshBuildError(
            f"tip ring arcs must pair up: chord {n_chord}/{len(e_up)}, wrap {n_wrap}/{len(e_te)}"
        )
    if collar_points < 3:
        raise MeshBuildError("collar_points must be at least 3.")
    if not (0.15 <= width_frac <= 0.85):
        raise MeshBuildError("width_frac must lie between 0.15 and 0.85.")

    lower = e_low  # nose -> TE
    upper = e_up[::-1]  # nose -> TE

    # Chordwise inset, so the collar end edges slant from the OML corners to the
    # rectangle corners instead of running collinear with its short sides.
    pos = np.linspace(chord_inset, 1.0 - chord_inset, n_chord) * (n_chord - 1)
    lo_i = np.floor(pos).astype(int)
    hi_i = np.minimum(lo_i + 1, n_chord - 1)
    frac = (pos - lo_i)[:, None]

    def _at(arr: Array) -> Array:
        return (1.0 - frac) * arr[lo_i] + frac * arr[hi_i]

    lower_s = _at(lower)
    upper_s = _at(upper)
    camber = 0.5 * (upper_s + lower_s)
    rect_top = camber + width_frac * (upper_s - camber)
    rect_bot = camber + width_frac * (lower_s - camber)

    def _straight(p0: Array, p1: Array, n: int) -> Array:
        s = np.linspace(0.0, 1.0, n)[:, None]
        return (1.0 - s) * p0 + s * p1

    rect_left = _straight(rect_top[0], rect_bot[0], n_wrap)  # upper -> lower
    rect_right = _straight(rect_bot[-1], rect_top[-1], n_wrap)  # lower -> upper

    end_up_nose = _straight(e_nose[0], rect_top[0], collar_points)
    end_lo_nose = _straight(e_nose[-1], rect_bot[0], collar_points)
    end_lo_te = _straight(e_low[-1], rect_bot[-1], collar_points)
    end_up_te = _straight(e_up[0], rect_top[-1], collar_points)

    collar_nose = _tfi_patch(end_up_nose, end_lo_nose, e_nose, rect_left).transpose(1, 0, 2)
    collar_low = _tfi_patch(end_lo_nose, end_lo_te, e_low, rect_bot).transpose(1, 0, 2)
    collar_te = _tfi_patch(end_lo_te, end_up_te, e_te, rect_right).transpose(1, 0, 2)
    collar_up = _tfi_patch(end_up_te, end_up_nose, e_up, rect_top[::-1]).transpose(1, 0, 2)
    center = _tfi_patch(rect_bot, rect_top, rect_left[::-1], rect_right)

    patches = [center, collar_up, collar_te, collar_low, collar_nose]
    patches, flipped = orient_patches_2d(patches)
    info = {
        "topology": "camber_split_rectangle_plus_four_collars",
        "block_names": ["tip_center", "tip_collar_upper", "tip_collar_te",
                        "tip_collar_lower", "tip_collar_nose"],
        "provenance": "construction from commit bfaeaf1, validated at L1 with a full pyHyp march",
        "width_frac": width_frac,
        "chord_inset": chord_inset,
        "collar_points": int(collar_points),
        "n_chord": int(n_chord),
        "n_wrap": int(n_wrap),
        "orientation_flipped": flipped,
        "outer_ring": "exact OML tip-edge nodes",
    }
    return patches, info


def map_2d_patch_to_tip(wing, patch_2d: Array) -> Array:
    """Map a 2D (ni, nj, 2) section patch onto the wing's outermost station."""
    n_xsec = len(wing.xsecs)
    ni = patch_2d.shape[0]
    sides_by_xsec = [[patch_2d[i] for i in range(ni)] for _ in range(n_xsec)]
    mapped = _map_sides_to_wing(wing, sides_by_xsec)  # ni blocks of (nj, n_xsec, 3)
    return np.stack([m[:, -1, :] for m in mapped], axis=0)


def realise_spanwise_law(blocks: list[Array], cells_per_interval: list[int]) -> list[Array]:
    """Subdivide each spanwise interval into the number of cells the law asks for.

    S1 computes a geometric-progression spanwise law from physical segment length
    and then, until now, threw it away and used the generator's native stations.
    That left cells about 50x longer spanwise than chordwise.

    New columns are linear blends of the two bounding station columns, which is
    what `aeris.mesh.surface._refine_spanwise` already does for cap4. **This is an
    approximation**: the master geometry is a spline loft in span, so an
    interpolated column is a chord of that loft, not a point on it. The error is
    measured rather than assumed - see `spanwise_interpolation_error`.
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
