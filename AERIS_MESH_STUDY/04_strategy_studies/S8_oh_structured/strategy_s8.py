"""S8 O-H structured grid, after Zhang et al. (2026) figure 28.

Topology, and why it is different from every earlier AERIS strategy:

    xi    one O-ring around the section, trailing edge -> leading edge ->
          trailing edge -> across the blunt base.  ONE block, no collars.
    eta   wall-normal, marched in the section plane from the wall to a
          far-field circle.  This is the "O".
    zeta  spanwise, root symmetry plane -> tip.  This is the "H".

The C and D families split each section into six blocks and gave the leading
edge its own collar whose width was a block dimension shared with the trailing
edge.  That coupling is the documented cause of the impossible surface pressure
(reports/m2_a_c03_leading_edge_collar_defect_20260903.json) and of the volume
march failure that followed the attempt to fix it
(reports/m2_leading_edge_wrap_redesign_20260903.json).

An O-ring removes the coupling structurally.  Leading-edge resolution is
requested in degrees of surface turning per cell and solved for; there is no
`end_points`, so nothing the leading edge asks for can shrink the trailing edge
or the tip.

The tip is closed by a butterfly cap: a collar of rings inside the tip loop and
a transfinite H patch in the middle.  That is the second, smaller "H" of O-H,
and it is what keeps the topology free of collapsed edges.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent), str(HERE.parent / "S6_bounded_mesh_atlas")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from section_o import (  # noqa: E402
    ring_for_target_turning,
    section_ring,
    vinokur,
)
from shared.ingestion import SurfaceBlock  # noqa: E402

Array = np.ndarray
STRATEGY_ID = "S8_OH_STRUCTURED"


@dataclass(frozen=True)
class OHLevel:
    #: points from the trailing-edge corner to the leading edge on each side
    n_side: int
    #: points across the blunt trailing-edge base, including both corners
    n_base: int
    #: spanwise stations, root to tip
    n_span: int
    #: rings of collar inside the tip loop before the transfinite centre patch
    n_cap_collar: int
    #: surface turning absorbed by one leading-edge cell, in degrees.  This is
    #: the request the whole strategy exists to honour.  The conventional
    #: wall-resolved reference is 10; C03 delivers 25.7.
    target_le_turn_deg: float
    #: trailing-edge corner spacing as a fraction of local chord
    ds_te_frac: float
    #: dense samples per section curve.  Must stay well above the ring spacing;
    #: `ring_for_target_turning` floors the solve at three dense samples.
    dense_points: int
    #: wall-normal layers out to the far field
    n_normal: int
    #: far-field radius in root chords
    farfield_chords: float
    #: first cell height as a fraction of the bounding-box diagonal
    s0_frac: float
    #: Largest permitted station-to-station ratio of the leading-edge cell size
    #: measured as a fraction of local chord.  The per-station bisection solves
    #: each section in isolation, and its target -- the MAXIMUM turning over a
    #: six-segment window at the nose -- is a max over a discrete set, so it is
    #: piecewise in `ds_le` and the bisection can settle on a different branch
    #: at neighbouring stations even where the loft is smooth.  On oh_L3 that
    #: produced a 2.6x cliff in normalised leading-edge spacing between spanwise
    #: stations 11 and 12, invisible to `worst_le_turn_per_cell_deg` because
    #: every station still met 10 degrees.  See
    #: reports/s8_cp_excess_diagnosis_20260904.json.
    le_span_growth_max: float = 1.15
    #: The LAST spanwise cell on the OML, in multiples of s0.  This is not an
    #: OML requirement -- the spanwise direction is tangential to the OML wall --
    #: it is the TIP CAP's requirement.  The cap's wall normal IS the spanwise
    #: direction, so this number sets y+ on the cap, and the outboard stack
    #: starts from the same value so the o_wing/o_out interface carries no
    #: cell-size jump.  10 gives a cap y+ about ten times the OML's.
    tip_span_first_cell_in_s0: float = 10.0


def refined_level(base: OHLevel, ratio: float, *, scale_first_cell: bool = True,
                  name: str = "") -> OHLevel:
    """One level of a grid-convergence family, generated from a baseline.

    A convergence family is the SAME mesh at a different spacing, not three
    meshes that happen to have different cell counts.  Everything that defines
    where cells go is held fixed -- the leading-edge turning target, the
    trailing-edge fraction, the far-field distance, the clustering laws -- and
    only the number of INTERVALS changes, by `ratio` in all three directions.

    The hand-written oh_L3/L2/L1 ladder was not this.  It refined the three
    directions at 1.31 / 1.33 / 1.25, and it also moved the leading-edge target
    from 10 to 8 to 6 degrees and the trailing-edge fraction from 0.004 to
    0.003.  With the resolution LAW changing between levels, a shift in CD
    cannot be attributed to the grid, and Richardson extrapolation over it means
    nothing.  That ladder is kept below as the `legacy_*` names, because the
    alpha sweep was run on `oh_L3` and that mesh must remain reproducible.

    `scale_first_cell` divides s0 by the ratio as well, so the wall-normal
    direction is refined like the other two.  That is the honest choice for a
    formal study -- the whole mesh gets finer -- and it does mean y+ falls
    between levels rather than being held constant.  Both are defensible; this
    one is uniform refinement, and at a measured y+ of about 0.56 at p95 there
    is no risk of leaving the wall-resolved regime by making it smaller.  Pass
    False to hold the first cell instead, which isolates everything but the wall.
    """
    def intervals(points: int, *, odd: bool = False, minimum: int = 3) -> int:
        n = max(int(round((points - 1) * ratio)), minimum - 1) + 1
        if odd and n % 2 == 0:
            n += 1
        return n

    return OHLevel(
        n_side=intervals(base.n_side),
        # the nose arc must stay odd so it can centre on the leading edge and
        # match the base point count -- build_tip_cap raises otherwise
        n_base=intervals(base.n_base, odd=True),
        n_span=intervals(base.n_span),
        n_cap_collar=max(int(round(base.n_cap_collar * ratio)), 2),
        # HELD FIXED: the resolution requests, not the resolution
        target_le_turn_deg=base.target_le_turn_deg,
        ds_te_frac=base.ds_te_frac,
        farfield_chords=base.farfield_chords,
        le_span_growth_max=base.le_span_growth_max,
        tip_span_first_cell_in_s0=base.tip_span_first_cell_in_s0,
        # the dense sampling only has to stay well finer than the ring spacing
        dense_points=int(round(base.dense_points * ratio)),
        n_normal=intervals(base.n_normal),
        s0_frac=base.s0_frac / ratio if scale_first_cell else base.s0_frac,
    )


#: The grid-convergence family.  `gci_M` is the mesh the 2026-09-05 alpha sweep
#: ran on, bit for bit: it IS oh_L3.  Coarse and fine are generated from it by
#: one ratio, so the family is a refinement of one mesh rather than three
#: separately designed ones.
GCI_RATIO = 1.3

LEVELS: dict[str, OHLevel] = {
    # Matched to the C family's cells-around-a-section (120) so the leading-edge
    # comparison is like for like, then refined by span and normal count.
    "oh_L3": OHLevel(45, 5, 49, 4, 10.0, 0.004, 1601, 65, 40.0, 3.6e-6),
    "oh_L2": OHLevel(59, 5, 65, 5, 8.0, 0.004, 2401, 81, 40.0, 3.6e-6),
    "oh_L1": OHLevel(81, 7, 89, 6, 6.0, 0.003, 3201, 105, 40.0, 3.6e-6),
    "oh_L0": OHLevel(113, 9, 121, 8, 4.5, 0.002, 4801, 137, 40.0, 3.6e-6),
    "oh_probe": OHLevel(31, 5, 25, 3, 12.0, 0.005, 1201, 41, 40.0, 3.6e-6),
}

#: The hand-written ladder, kept reachable because the alpha sweep ran on oh_L3
#: and that mesh must stay reproducible.  It is NOT a convergence family; see
#: `refined_level`.
LEVELS["legacy_L2"] = LEVELS["oh_L2"]
LEVELS["legacy_L1"] = LEVELS["oh_L1"]
LEVELS["legacy_L0"] = LEVELS["oh_L0"]

#: gci_M is oh_L3 unchanged -- the mesh the sweep was run on.
LEVELS["gci_M"] = LEVELS["oh_L3"]
LEVELS["gci_C"] = refined_level(LEVELS["oh_L3"], 1.0 / GCI_RATIO, name="gci_C")
LEVELS["gci_F"] = refined_level(LEVELS["oh_L3"], GCI_RATIO, name="gci_F")


def _span_coordinate(pygeo: Any, v: float) -> float:
    """The spanwise coordinate of one section, used to invert arc length to v."""
    points = _surface_points_at_v(pygeo, v)
    return float(points[:, 1].mean())


def _surface_points_at_v(pygeo: Any, v: float, samples: int = 41) -> Array:
    u = np.linspace(0.0, 1.0, samples)
    vv = np.full_like(u, float(v))
    upper = np.asarray(pygeo.surfs[0](u, vv), dtype=float).reshape(samples, 3)
    lower = np.asarray(pygeo.surfs[1](u, vv), dtype=float).reshape(samples, 3)
    return np.vstack([upper, lower])


def _span_stations(pygeo: Any, n: int, ds_tip: float, probes: int = 401) -> tuple[Array, dict]:
    """Spanwise station fractions whose LAST cell is `ds_tip` metres.

    A pure tanh clustering was used first and cannot express this: it controls
    the shape of the distribution but not the size of any particular cell, and
    the last cell is the one the tip cap's y+ depends on.  A two-sided
    stretching takes the end spacings as the request, so the tip cell is a
    number rather than a consequence.

    The stretching is solved in spanwise ARC LENGTH and then inverted onto the
    loft parameter v, because v is not linear in span.
    """
    probe_v = np.linspace(0.0, 1.0, probes)
    span = np.array([_span_coordinate(pygeo, float(v)) for v in probe_v])
    span = span - span[0]
    total = float(span[-1])
    ds_root = total / (n - 1)
    targets = vinokur(n, ds_root, min(ds_tip, 0.4 * ds_root), total)
    fractions = np.interp(targets, span, probe_v)
    fractions[0], fractions[-1] = 0.0, 1.0
    cells = np.diff(targets)
    info = {
        "span_length_m": total,
        "ds_root_m": float(cells[0]),
        "ds_tip_m": float(cells[-1]),
        "ds_tip_requested_m": float(ds_tip),
        "max_span_growth_ratio": float(np.max(cells[:-1] / cells[1:])),
    }
    return fractions, info


def smooth_le_spacing(ds_le: Array, chord: Array, growth_max: float) -> tuple[Array, dict]:
    """Remove spanwise cliffs from the solved leading-edge spacing.

    Takes the per-station solved spacings and returns a spanwise-smooth
    envelope of them, expressed as a fraction of local chord so the natural
    taper of the wing is not mistaken for a discontinuity.

    The filter is a MINIMUM envelope: it sweeps outboard and then inboard,
    allowing the normalised spacing to grow by at most `growth_max` per station
    and clamping it wherever it would grow faster.  Every output is therefore
    less than or equal to the solved input.  That direction is deliberate and is
    what makes the change safe: a smaller leading-edge cell absorbs LESS turning,
    so no station can come out worse than the target it was solved for, and
    `all_stations_met_target` cannot be broken by smoothing.  Refining rather
    than coarsening also costs nothing -- `n_side` is fixed, so a smaller end
    spacing redistributes the section's points, it does not add any.
    """
    normalised = np.asarray(ds_le, dtype=float) / np.asarray(chord, dtype=float)
    out = normalised.copy()
    for i in range(1, len(out)):
        out[i] = min(out[i], out[i - 1] * growth_max)
    for i in range(len(out) - 2, -1, -1):
        out[i] = min(out[i], out[i + 1] * growth_max)
    # Denormalising is a round trip through a division and a multiplication, so
    # an unclamped station can come back a few ulps ABOVE the value it went in
    # at -- measured at 1.4e-16 relative on two of oh_L3's 49 stations.  That is
    # noise, but "this filter never coarsens" is the entire safety argument for
    # it, and an argument that rests on rounding luck is not an argument.  The
    # elementwise minimum makes it true by construction.
    spacing = np.minimum(out * np.asarray(chord, dtype=float), np.asarray(ds_le, dtype=float))
    ratios = out[1:] / out[:-1]
    before = normalised[1:] / normalised[:-1]
    info = {
        "growth_max": float(growth_max),
        "stations_clamped": int((out < normalised * (1.0 - 1.0e-12)).sum()),
        "worst_step_before": float(max(before.max(), 1.0 / before.min())),
        "worst_step_after": float(max(ratios.max(), 1.0 / ratios.min())),
        "spacing_reduced_by_max_factor": float((normalised / out).max()),
    }
    return spacing, info


def build_oml_ring(
    pygeo: Any,
    level: OHLevel,
    *,
    te_abs_m: float = 0.001,
    te_floor_frac: float = 0.005,
) -> tuple[Array, dict[str, Any]]:
    """The O-ring OML surface: (n_ring, n_span, 3), root to tip.

    Returns the ring array and a report carrying the delivered leading-edge
    turning at every station, which is the acceptance number for this strategy.
    """
    import strategy_s6

    # s0 is needed to size the tip spanwise cell, and s0 is a fraction of the
    # bounding-box diagonal, so the diagonal is estimated from the root and tip
    # sections before the real span law is built.
    probe = np.vstack([_surface_points_at_v(pygeo, 0.0), _surface_points_at_v(pygeo, 1.0)])
    s0 = level.s0_frac * float(np.linalg.norm(np.ptp(probe, axis=0)))
    fractions, span_info = _span_stations(
        pygeo, level.n_span, level.tip_span_first_cell_in_s0 * s0
    )
    # Pass 1: solve every station in isolation, exactly as before, and keep the
    # curves so a station can be rebuilt without re-evaluating the loft.
    solved: list[dict[str, Any]] = []
    for v in fractions:
        u_dense, upper, lower, frame = strategy_s6._frame_and_opened_curves(
            pygeo,
            float(v),
            dense_points=level.dense_points,
            te_abs_m=te_abs_m,
            te_floor_frac=te_floor_frac,
        )

        def evaluate(u: Array, is_upper: bool, _v=float(v), _frame=frame) -> Array:
            """Exact loft points at tracked parameters, after the declared TE law.

            This is the same instrument S6 uses for its fidelity check, so the
            O-ring nodes sit on the identical CFD surface the C family used.
            """
            return strategy_s6._opened_points_at_u(
                pygeo, np.asarray(u, dtype=float), _v, frame=_frame, upper=is_upper
            )

        ring, metrics = ring_for_target_turning(
            upper,
            lower,
            n_side=level.n_side,
            n_base=level.n_base,
            target_turn_deg=level.target_le_turn_deg,
            ds_te=level.ds_te_frac * frame.chord,
            parameter=u_dense,
            evaluate=evaluate,
        )
        solved.append({
            "v": float(v), "ring": ring, "metrics": metrics, "frame": frame,
            "upper": upper, "lower": lower, "u_dense": u_dense,
            "evaluate": evaluate,
        })

    # Pass 2: enforce spanwise smoothness of the leading-edge spacing, and
    # rebuild only the stations the envelope actually moved.  Rebuilding calls
    # `section_ring` directly at the clamped spacing rather than re-solving,
    # because the whole point is that the solve's own answer is what jumped.
    ds_solved = np.array([d["metrics"]["ds_le_solved_m"] for d in solved])
    chords = np.array([float(d["frame"].chord) for d in solved])
    ds_smooth, le_smoothing = smooth_le_spacing(
        ds_solved, chords, level.le_span_growth_max
    )

    rings: list[Array] = []
    stations: list[dict[str, Any]] = []
    for d, ds_new, ds_old in zip(solved, ds_smooth, ds_solved):
        ring, metrics = d["ring"], d["metrics"]
        rebuilt = bool(ds_new < ds_old * (1.0 - 1.0e-12))
        if rebuilt:
            ring, metrics = section_ring(
                d["upper"],
                d["lower"],
                n_side=level.n_side,
                n_base=level.n_base,
                ds_le=float(ds_new),
                ds_te=level.ds_te_frac * d["frame"].chord,
                parameter=d["u_dense"],
                evaluate=d["evaluate"],
            )
            metrics["ds_le_solved_m"] = float(ds_new)
            # Refining can only reduce the turning a cell absorbs, so the target
            # stays met; recorded from the rebuilt ring rather than assumed.
            metrics["turn_target_met"] = bool(
                metrics["le_turn_per_cell_deg"] <= level.target_le_turn_deg + 0.2
            )
            metrics["at_dense_sampling_floor"] = False
        rings.append(ring)
        stations.append({
            "v": d["v"],
            "chord_m": float(d["frame"].chord),
            "le_turn_per_cell_deg": metrics["le_turn_per_cell_deg"],
            "ds_le_m": float(ds_new),
            "ds_le_solved_m": float(ds_old),
            "le_spacing_smoothed": rebuilt,
            "min_spacing_m": metrics["min_spacing_m"],
            "spacing_range": metrics["spacing_range"],
            "turn_target_met": metrics["turn_target_met"],
            "at_dense_sampling_floor": metrics["at_dense_sampling_floor"],
        })
    xyz = np.stack(rings, axis=1)
    report = {
        "n_ring": int(xyz.shape[0]),
        "n_span": int(xyz.shape[1]),
        "target_le_turn_deg": level.target_le_turn_deg,
        "worst_le_turn_per_cell_deg": max(s["le_turn_per_cell_deg"] for s in stations),
        "all_stations_met_target": all(s["turn_target_met"] for s in stations),
        "any_station_at_sampling_floor": any(s["at_dense_sampling_floor"] for s in stations),
        "min_surface_spacing_m": min(s["min_spacing_m"] for s in stations),
        "le_spacing_smoothing": le_smoothing,
        "span": span_info,
        "s0_estimate_m": s0,
        "stations": stations,
    }
    return xyz, report


def build_tip_cap(tip_ring: Array, level: OHLevel) -> tuple[list[SurfaceBlock], dict[str, Any]]:
    """Close the tip with ONE chordwise H patch whose perimeter is the tip ring.

    xi runs chordwise from the nose arc to the trailing-edge base; eta runs
    across the thickness from the lower surface to the upper surface.  Its four
    sides are exactly the four pieces of the ring, so the cap and the O-ring
    share every perimeter node and there is no interface to interpolate.

    Why not a butterfly.  The first version pulled the ring inward toward its
    own centroid and filled the middle with a transfinite square.  On a circle
    that is textbook; on an aerofoil it is nonsense, and measurably so: the tip
    ring's distance to its centroid ranges 7.7 mm to 80.2 mm, a ratio of 10.4,
    so a 65 percent pull moves points up to 52 mm across a section that is only
    22.9 mm thick.  Upper and lower surfaces crossed.  The collar reached a
    minimum scaled Jacobian of 0.0075 with a 180 degree normal flip and the
    centre patch went negative at -0.1485.

    Chords across the thickness cannot cross, because the section is convex in
    the thickness direction everywhere.  The nose arc carries the same number
    of points as the base, which is what lets a single quad patch close the loop
    with no collapsed edge -- the collapsed leading-edge line a naive H cap
    leaves behind, and the collapsed pole a naive O cap leaves behind, are both
    avoided.
    """
    ring = np.asarray(tip_ring, dtype=float)
    n_base = level.n_base
    if n_base % 2 == 0:
        raise ValueError(
            f"n_base must be odd so the nose arc can be centred on the leading "
            f"edge and match the base point count; got {n_base}"
        )
    half_nose = (n_base - 1) // 2
    n_side = level.n_side
    le = n_side - 1
    n_chord = n_side - half_nose
    if n_chord < 3:
        raise ValueError("n_side is too small for this nose arc")

    # ring layout: upper[0..n_side-1] = TE corner -> LE, then lower LE -> TE
    # corner, then the interior of the base.
    upper = ring[: le + 1]                       # TE corner -> LE
    lower = ring[le : 2 * n_side - 1]            # LE -> TE corner
    base_interior = ring[2 * n_side - 1 :]       # interior of the base only

    nose = np.vstack([upper[le - half_nose:], lower[1 : half_nose + 1]])
    upper_side = upper[: le - half_nose + 1][::-1]    # nose end -> TE corner
    lower_side = lower[half_nose:]                    # nose end -> TE corner
    # base_interior already runs lower TE corner -> upper TE corner, matching
    # eta.  Reversing it here put the base side backwards against the nose side
    # and drove the patch's minimum scaled Jacobian to -0.977.  The perimeter
    # check below is what makes that impossible to ship again.
    base = np.vstack([lower_side[-1:], base_interior, upper_side[-1:]])

    if not (len(nose) == len(base) == n_base):
        raise AssertionError(f"nose {len(nose)} and base {len(base)} must both be {n_base}")
    if not len(upper_side) == len(lower_side) == n_chord:
        raise AssertionError(f"chordwise sides must both be {n_chord}")

    # transfinite interpolation, xi = chordwise, eta = lower -> upper
    xi = np.linspace(0.0, 1.0, n_chord)
    et = np.linspace(0.0, 1.0, n_base)
    patch = (
        (1.0 - et)[None, :, None] * lower_side[:, None, :]
        + et[None, :, None] * upper_side[:, None, :]
        + (1.0 - xi)[:, None, None] * nose[None, ::-1, :]
        + xi[:, None, None] * base[None, :, :]
        - (
            (1.0 - xi)[:, None, None] * (1.0 - et)[None, :, None] * lower_side[0]
            + (1.0 - xi)[:, None, None] * et[None, :, None] * upper_side[0]
            + xi[:, None, None] * (1.0 - et)[None, :, None] * lower_side[-1]
            + xi[:, None, None] * et[None, :, None] * upper_side[-1]
        )
    )
    # The patch perimeter must BE the ring, node for node.  A transfinite patch
    # is happy to interpolate a perimeter assembled in the wrong order and hand
    # back a folded result, so this is checked rather than assumed.
    perimeter = np.vstack([
        patch[0, :, :],          # nose arc, lower -> upper
        patch[1:, -1, :],        # upper surface, nose -> TE
        patch[-1, -2::-1, :],    # base, upper -> lower
        patch[-2::-1, 0, :],     # lower surface, TE -> nose
    ])
    if len(perimeter) != len(ring) + 1:
        raise AssertionError(
            f"patch perimeter has {len(perimeter)} nodes, ring has {len(ring)}"
        )
    gap = float(np.abs(np.sort(perimeter[:-1], axis=0) - np.sort(ring, axis=0)).max())
    if gap > 1.0e-12:
        raise AssertionError(f"patch perimeter is not the tip ring: {gap:.3e} m apart")

    patch = _smooth_patch(patch, iterations=400)

    # Orient the patch so that i x j points OUTBOARD (+y for this half model).
    # xi runs aft along the chord and eta from the lower surface up, which makes
    # i x j = x_hat x z_hat = -y_hat: extruding that outboard gives a
    # left-handed cell and every one of the 3864 cap cells reported a negative
    # volume.  Same signature as the far-field frame bug, same cause, and again
    # not a fold -- so it is fixed by construction here rather than left for the
    # volume report to catch.
    normal = np.cross(
        patch[1, patch.shape[1] // 2] - patch[0, patch.shape[1] // 2],
        patch[patch.shape[0] // 2, 1] - patch[patch.shape[0] // 2, 0],
    )
    if float(normal[1]) < 0.0:
        patch = patch[:, ::-1, :]

    info = {
        "construction": "single chordwise transfinite H patch, perimeter shared with the O-ring",
        "patch_shape": [int(n_chord), int(n_base)],
        "nose_arc_points": int(n_base),
        "half_nose_offset": int(half_nose),
        "collapsed_edges": 0,
        "perimeter_matches_ring": True,
        "eta_reversed_for_outboard_handedness": bool(float(normal[1]) < 0.0),
    }
    return [SurfaceBlock(name="tip_cap", xyz=patch, family="wall")], info


def _smooth_patch(patch: Array, iterations: int) -> Array:
    """Laplacian smoothing of a patch interior with every edge held fixed."""
    out = patch.copy()
    for _ in range(iterations):
        out[1:-1, 1:-1] = 0.25 * (
            out[:-2, 1:-1] + out[2:, 1:-1] + out[1:-1, :-2] + out[1:-1, 2:]
        )
    return out
