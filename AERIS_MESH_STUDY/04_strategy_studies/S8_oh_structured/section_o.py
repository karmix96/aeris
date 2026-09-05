"""S8 O-H: the section O-ring.

The C and D families split every section into six blocks, two of which are
collars at the leading and trailing edges.  That is the whole source of the
cp defect: the nose collar's point count (`end_points`) is a block dimension, it
is shared with the trailing-edge base block, and it caps leading-edge resolution
at 5 points no matter how fine the rest of the section is.

An O-ring has no such knob.  The section is one closed curve and the points are
placed on it by a stretching law, so leading-edge resolution is a *spacing*
request in metres, not a block dimension.  This is the section topology of the
O-H grids in Zhang et al. (2026), figure 28.

Loop convention, counter-clockwise starting at the upper trailing-edge corner:

    upper TE corner -> leading edge -> lower TE corner -> across the blunt base

The blunt base is part of the ring, so DECISION-0004's 1.0 mm trailing edge is
respected without a separate base block.
"""

from __future__ import annotations

import numpy as np

Array = np.ndarray


def vinokur(n: int, ds0: float, ds1: float, total: float) -> Array:
    """Two-sided stretched arc-length stations on [0, total].

    Returns `n` positions whose first and last intervals are ds0 and ds1.  This
    is the standard two-sided hyperbolic stretching; it is solved by bisection on
    the tanh parameter rather than by Vinokur's asymptotic fits, which are only
    accurate over part of the range and would silently miss the requested
    spacing at the leading edge -- the one number this whole strategy exists to
    control.
    """
    if n < 3:
        raise ValueError("a stretched distribution needs at least three points")
    if not (0.0 < ds0 < total and 0.0 < ds1 < total):
        raise ValueError(f"end spacings {ds0}, {ds1} must be inside (0, {total})")
    a0, a1 = ds0 / total, ds1 / total
    s = np.linspace(0.0, 1.0, n)

    def shaped(b: float) -> Array:
        # symmetric tanh core, then a linear reparameterisation that biases the
        # two ends independently
        u = 0.5 * (1.0 + np.tanh(b * (s - 0.5)) / np.tanh(0.5 * b))
        r = np.sqrt(a1 / a0)
        return u / (r + (1.0 - r) * u)

    lo, hi = 1.0e-6, 60.0
    target = 1.0 / ((n - 1) * np.sqrt(a0 * a1))
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        u = 0.5 * (1.0 + np.tanh(mid * (s - 0.5)) / np.tanh(0.5 * mid))
        got = 1.0 / ((n - 1) * (u[1] - u[0]) + 1.0e-300)
        if got < target:
            lo = mid
        else:
            hi = mid
    x = shaped(0.5 * (lo + hi))
    x = (x - x[0]) / (x[-1] - x[0])
    return total * x


def resample(points: Array, targets: Array) -> Array:
    """Sample a dense polyline at given arc-length positions."""
    d = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(d)])
    return np.column_stack([np.interp(targets, cum, points[:, k]) for k in range(3)])


def resample_u(points: Array, parameter: Array, targets: Array) -> Array:
    """The curve parameters at given arc-length positions.

    Kept separate from :func:`resample` because the ring is not built from the
    interpolated points.  A dense polyline is uniform in arc length here, about
    560 um per sample on the root section, so interpolating it cannot place a
    100 um cell at the nose -- the very cells this strategy exists to place.
    The polyline is used only to invert arc length to parameter; the points
    themselves are then re-evaluated on the exact loft at those parameters.
    """
    d = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(d)])
    return np.interp(targets, cum, parameter)


def arc_length(points: Array) -> float:
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def section_ring(
    upper: Array,
    lower: Array,
    *,
    n_side: int,
    n_base: int,
    ds_le: float,
    ds_te: float,
    parameter: Array | None = None,
    evaluate=None,
) -> tuple[Array, dict]:
    """One closed O-ring on a section.

    ``upper`` and ``lower`` come from the exact pyGeo loft after the declared TE
    opening, both ordered trailing edge -> leading edge.  ``ds_le`` and ``ds_te``
    are the requested arc-length spacings in metres at the leading edge and at
    the trailing-edge corners.

    Returns the unique ring points, counter-clockwise, and a metric block.
    """
    if n_base < 2:
        raise ValueError("the blunt base needs at least two points")
    up_len, lo_len = arc_length(upper), arc_length(lower)
    up_targets = vinokur(n_side, ds_te, ds_le, up_len)
    lo_targets = vinokur(n_side, ds_te, ds_le, lo_len)
    if evaluate is None:
        up = resample(upper, up_targets)
        lo = resample(lower, lo_targets)
        u_up = u_lo = None
    else:
        u_up = resample_u(upper, parameter, up_targets)
        u_lo = resample_u(lower, parameter, lo_targets)
        up = evaluate(u_up, True)
        lo = evaluate(u_lo, False)

    # upper: TE corner -> LE.  lower reversed: LE -> TE corner.
    ring = [up, lo[::-1][1:]]
    base_len = float(np.linalg.norm(upper[0] - lower[0]))
    if n_base > 2:
        t = np.linspace(0.0, 1.0, n_base)[1:-1]
        ring.append(lo[0][None, :] + t[:, None] * (up[0] - lo[0])[None, :])
    ring = np.vstack(ring)

    closed = np.vstack([ring, ring[:1]])
    seg = np.diff(closed, axis=0)
    length = np.linalg.norm(seg, axis=1)
    unit = seg / length[:, None]
    cos = np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)
    turn = np.degrees(np.arccos(cos))

    # the leading edge is the ring point at index n_side - 1
    le = n_side - 1
    nose = slice(max(le - 3, 0), min(le + 3, len(turn)))
    metrics = {
        "ring_points": int(len(ring)),
        "n_side": int(n_side),
        "n_base": int(n_base),
        "le_index": int(le),
        "min_spacing_m": float(length.min()),
        "max_spacing_m": float(length.max()),
        "spacing_range": float(length.max() / length.min()),
        "le_spacing_m": float(length[le - 1 : le + 1].mean()),
        "te_spacing_m": float(length[0]),
        "base_length_m": base_len,
        "max_turn_deg": float(turn.max()),
        "le_turn_per_cell_deg": float(turn[nose].max()),
        "total_turn_deg": float(turn.sum()),
        "u_upper": None if u_up is None else u_up,
        "u_lower": None if u_lo is None else u_lo,
    }
    return ring, metrics


def ring_for_target_turning(
    upper: Array,
    lower: Array,
    *,
    n_side: int,
    n_base: int,
    target_turn_deg: float,
    ds_te: float,
    parameter: Array | None = None,
    evaluate=None,
    tolerance: float = 0.02,
    max_iterations: int = 60,
) -> tuple[Array, dict]:
    """Build the ring whose leading-edge cells absorb `target_turn_deg` each.

    The spacing is solved for, not predicted.  A closed-form ``ds = R * theta``
    needs the nose radius, and a three-point circle fit across the nose
    overestimates it by a factor of three on a real aerofoil, where the
    curvature is still changing fast over the first cell: asking for 6 degrees
    that way delivered 20.  Measuring the turning on the ring that was actually
    built takes the estimate out of the loop, so the delivered number is the
    requested number at every station and on every aerofoil in the design space.
    That guarantee is the whole reason this strategy exists; the C family's
    `end_points` could not give it.
    """
    le_arc = min(arc_length(upper), arc_length(lower))
    # Floor on the solve.  With `evaluate` the nodes come off the exact loft, so
    # the dense polyline only has to invert arc length to parameter and the
    # floor can be loose.  Without it the ring is interpolated from the polyline
    # and cannot be finer than it: below about three dense samples per cell the
    # measured turning stops falling -- that is polyline noise, not geometry --
    # and a bisection that trusts it walks the spacing to zero and returns a
    # degenerate ring.  Seen at v=0.80 with dense_points=1601, where the target
    # looked unreachable and was not.
    dense_ds = max(
        arc_length(upper[-40:]) / 40.0, arc_length(lower[-40:]) / 40.0, 1.0e-12
    )
    floor = (0.02 if evaluate is not None else 3.0) * dense_ds
    lo, hi = floor, 0.25 * le_arc
    if lo >= hi:
        raise ValueError("dense curve sampling is too coarse for this section")
    best = None
    for _ in range(max_iterations):
        mid = 0.5 * (lo + hi)
        ring, metrics = section_ring(
            upper, lower, n_side=n_side, n_base=n_base, ds_le=mid, ds_te=ds_te,
            parameter=parameter, evaluate=evaluate,
        )
        got = metrics["le_turn_per_cell_deg"]
        best = (ring, metrics, mid)
        if abs(got - target_turn_deg) <= tolerance:
            break
        if got > target_turn_deg:
            hi = mid
        else:
            lo = mid
    ring, metrics, ds = best
    metrics["ds_le_solved_m"] = float(ds)
    metrics["target_turn_deg"] = float(target_turn_deg)
    metrics["ds_le_floor_m"] = float(floor)
    metrics["at_dense_sampling_floor"] = bool(ds <= floor * 1.001)
    metrics["turn_target_met"] = bool(
        abs(metrics["le_turn_per_cell_deg"] - target_turn_deg) <= 10.0 * tolerance
    )
    return ring, metrics
