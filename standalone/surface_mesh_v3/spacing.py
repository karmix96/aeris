"""Node distributions that take PHYSICAL spacings, not tuning constants.

Why this module replaces the ``cosine``/``tanh``/``beta`` family in
``aeris.mesh.surface``
----------------------------------------------------------------------
The existing distributions answer "how strongly should I cluster?" with a
dimensionless knob. That question has no defensible answer on its own: how
strongly you must cluster at a leading edge depends on the leading-edge
radius, and how strongly at a trailing edge depends on the base thickness.
Because ``beta`` knows neither, the cluster strength has to be re-tuned for
every geometry — which is exactly the thing an automated DoE cannot do.

Vinokur's two-sided stretching inverts the question. You state the first and
last cell sizes you want in metres, and it returns the smoothest distribution
that delivers them. The clustering strength becomes an *output*. That is what
makes a spacing law geometry-conditioned and therefore automatable:

    s_LE  = leading-edge radius / le_radius_cells
    s_TE  = trailing-edge base thickness / te_base_cells

Reference
---------
M. Vinokur, "On One-Dimensional Stretching Functions for Finite-Difference
Calculations", Journal of Computational Physics 50(2), 1983, pp. 215-234.
The one-sided and two-sided hyperbolic forms, and the small/large-argument
series used here to invert sinh(d)/d and sin(d)/d, are from that paper
(Appendix, eqs. 62-68) as reproduced in Thompson, Soni & Weatherill,
*Handbook of Grid Generation*, CRC Press 1999, section 3.6.
"""

from __future__ import annotations

import numpy as np

Array = np.ndarray


class SpacingError(ValueError):
    """A requested spacing cannot be realised on the given interval."""


# ------------------------------------------------------- solve sinh(d)/d ----
def _inverse_sinh_over_x(target: float) -> float:
    """Solve sinh(d)/d = target for d > 0 (target > 1)."""
    if target <= 1.0:
        raise SpacingError("_inverse_sinh_over_x needs target > 1")
    if target < 2.7829681:
        y = target - 1.0
        return float(
            np.sqrt(6.0 * y)
            * (
                1.0
                - 0.15 * y
                + 0.057321429 * y**2
                - 0.024907295 * y**3
                + 0.0077424461 * y**4
                - 0.0010794123 * y**5
            )
        )
    v = np.log(target)
    w = 1.0 / target - 0.028527431
    return float(
        v
        + (1.0 + 1.0 / v) * np.log(2.0 * v)
        - 0.02041793
        + 0.24902722 * w
        + 1.9496443 * w**2
        - 2.6294547 * w**3
        + 8.56795911 * w**4
    )


def _vinokur_raw(n: int, d0: float, d1: float) -> Array:
    """Vinokur's two-sided hyperbolic distribution for normalised end slopes.

    Only the ``sinh`` branch is implemented. The ``sin`` branch covers
    b < 1, i.e. both end cells LARGER than the uniform cell — a de-clustering
    request that no aerodynamic surface makes and that ``vinokur`` below
    excludes by clamping. Implementing an unreachable branch would be untested
    code in the mesh path.
    """
    xi = np.linspace(0.0, 1.0, n)
    a = np.sqrt(d1 / d0)
    b = 1.0 / ((n - 1) * np.sqrt(d0 * d1))
    if b <= 1.0 + 1e-12:
        u = xi
    else:
        delta = _inverse_sinh_over_x(b)
        u = 0.5 * (1.0 + np.tanh(delta * (xi - 0.5)) / np.tanh(0.5 * delta))
    s = u / (a + (1.0 - a) * u)
    s[0], s[-1] = 0.0, 1.0
    return s


# --------------------------------------------------------------- public -----
def vinokur(
    n: int, length: float, s_start: float, s_end: float, *, iterations: int = 40
) -> Array:
    """``n`` normalised positions on [0, 1] with prescribed end cell sizes.

    ``length`` is the physical extent of the interval; ``s_start``/``s_end``
    are the desired first/last cell sizes in the same units. Returns the
    parametric positions (0 ... 1), so the caller maps them onto arc length.

    Vinokur's closed form matches the *derivative* of the stretching function
    at the ends, so the realised first cell — a finite difference — comes out
    around 10 % larger than requested at typical resolutions. Since the entire
    point of this module is that a caller states a physical cell size and gets
    it, the closed form is used as the starting guess for a short fixed-point
    correction on the two end slopes. The realised end cells then match the
    request to better than 0.1 %.

    Falls back to a uniform distribution when the request is unrealisable
    (either end cell larger than the average), because silently producing a
    folded distribution is worse than producing a coarse one.
    """
    if n < 2:
        raise SpacingError("a distribution needs at least 2 points")
    if length <= 0:
        raise SpacingError("interval length must be positive")
    if n == 2:
        return np.linspace(0.0, 1.0, 2)

    average = 1.0 / (n - 1)
    # Cap each end cell at the uniform size: a requested end cell LARGER than
    # uniform is a de-clustering request, which this two-sided form cannot
    # represent and which no aerodynamic surface wants.
    target0 = min(max(float(s_start) / float(length), 1e-12), average)
    target1 = min(max(float(s_end) / float(length), 1e-12), average)

    d0, d1 = target0, target1
    best = _vinokur_raw(n, d0, d1)
    for _ in range(iterations):
        s = _vinokur_raw(n, d0, d1)
        got0 = s[1] - s[0]
        got1 = s[-1] - s[-2]
        if got0 <= 0 or got1 <= 0:
            break
        best = s
        if abs(got0 - target0) <= 1e-4 * target0 and abs(got1 - target1) <= 1e-4 * target1:
            break
        d0 = min(max(d0 * target0 / got0, 1e-14), average)
        d1 = min(max(d1 * target1 / got1, 1e-14), average)

    if np.any(np.diff(best) <= 0):
        return np.linspace(0.0, 1.0, n)
    return best


def one_sided(n: int, length: float, s_start: float) -> Array:
    """Cluster at the start only, with a prescribed first cell size."""
    return vinokur(n, length, s_start, length / (n - 1))


def resample_by_arclength(points: Array, positions: Array) -> Array:
    """Sample a polyline at normalised arc-length ``positions`` in [0, 1]."""
    points = np.asarray(points, dtype=float)
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    s = np.concatenate(([0.0], np.cumsum(seg)))
    if s[-1] <= 0:
        raise SpacingError("polyline has zero length")
    target = np.asarray(positions, dtype=float) * s[-1]
    return np.column_stack([np.interp(target, s, points[:, k]) for k in range(points.shape[1])])


def arclength(points: Array) -> float:
    points = np.asarray(points, dtype=float)
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))


# ----------------------------------------------------- geometry measures ----
def leading_edge_radius(coords: Array, *, window: float = 0.02) -> float:
    """Least-squares circle radius through the nose of a normalised airfoil.

    ``coords`` is the (N, 2) loop upper-TE -> LE -> lower-TE in chord-normalised
    units; the returned radius is in the same units. Only points within
    ``window`` chord of the leading edge are used, which is the region a
    surface mesh has to resolve.
    """
    coords = np.asarray(coords, dtype=float)
    le = coords[np.argmin(coords[:, 0])]
    near = coords[coords[:, 0] - le[0] <= window]
    if len(near) < 4:
        raise SpacingError("too few nose points to fit a leading-edge radius")
    x, y = near[:, 0], near[:, 1]
    # Algebraic circle fit: x^2 + y^2 + D x + E y + F = 0
    matrix = np.column_stack([x, y, np.ones_like(x)])
    rhs = -(x**2 + y**2)
    d, e, f = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    radius_sq = 0.25 * (d**2 + e**2) - f
    if radius_sq <= 0:
        raise SpacingError("degenerate leading-edge circle fit")
    return float(np.sqrt(radius_sq))


def curvature_polyline(points: Array) -> Array:
    """Discrete curvature magnitude at each vertex of a 2-D/3-D polyline.

    Uses the circumscribed-circle estimate on consecutive triples, which is
    exact for points sampled from a circle and does not require a
    parameterisation. Endpoints inherit their neighbour's value.
    """
    points = np.asarray(points, dtype=float)
    a = points[:-2]
    b = points[1:-1]
    c = points[2:]
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    if points.shape[1] == 2:
        area2 = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                       - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
    else:
        area2 = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    denom = ab * bc * ca
    kappa = np.divide(2.0 * area2, denom, out=np.zeros_like(denom), where=denom > 1e-300)
    return np.concatenate(([kappa[0]], kappa, [kappa[-1]]))


def grade(s: Array, h: Array, rate: float) -> Array:
    """Limit a size field so neighbouring target sizes cannot jump.

    Enforces the Lipschitz condition ``h(a) <= h(b) + rate*|a-b|`` by two
    sweeps, which is the standard mesh-gradation control: it is what Gmsh's
    ``MeshSizeFactor``/gradation and every commercial mesher's "growth rate"
    do to a size field before meshing.

    ``rate`` is the growth ratio minus one: 0.2 permits neighbouring cells to
    differ by about 20 %, i.e. a growth ratio of 1.2.

    Using a size field instead of a named distribution is what lets the
    structured and unstructured families be refined by the SAME rule, so a
    comparison between them is a comparison of discretisation type rather than
    of two independently tuned resolutions.

    The two sweeps are ``np.minimum.accumulate`` on ``h -/+ rate*s``: the
    recurrence ``h[k] = min(h[k], h[k-1] + rate*ds)`` is exactly a running
    minimum of ``h - rate*s``. One pass each way is sufficient and final,
    because after the forward pass the field is already Lipschitz in the
    increasing direction and the backward pass cannot break that.
    """
    s = np.asarray(s, float)
    h = np.asarray(h, float)
    forward = np.minimum.accumulate(h - rate * s) + rate * s
    backward = np.minimum.accumulate((forward + rate * s)[::-1])[::-1] - rate * s
    return backward


def place(s: Array, h: Array, n: int, rate: float | None = None) -> Array:
    """Place ``n`` nodes along arc coordinate ``s`` following size field ``h``.

    A structured block needs an exact node count, so the field is scaled by one
    global constant until it integrates to ``n-1`` cells. The SHAPE of the
    field — where cells are small relative to each other — is preserved; only
    the overall level moves.

    When ``rate`` is given the gradation limit is re-applied INSIDE the scaling
    loop. That is not a refinement, it is required for the bound to mean
    anything: the adjacent-cell ratio implied by a field is ``1 + dh/ds``, and
    scaling ``h -> lambda h`` scales ``dh/ds`` by the same lambda. Grading once
    before scaling therefore guarantees a growth bound on a field that is then
    thrown away — measured consequence on the first v3 prototype was a growth
    ratio of 264 from a field graded at 1.2.

    The field is internally REFINED before integration. This is not an
    optimisation: ``np.interp`` cannot resolve a cell smaller than the spacing
    of the field's own samples, so placing 0.8 mm cells from a field sampled
    every 50 mm silently returns whatever the linear interpolation happens to
    give. Measured on a spike test, a field graded to a growth bound of 1.2
    produced realised growth ratios of 2.0 (n=60) and 14.1 (n=200) purely from
    that under-sampling — which is the same failure that made the first v3
    prototype report growth ratios of 30-260 while its size field was correct.
    """
    s = np.asarray(s, float)
    h_raw = np.maximum(np.asarray(h, float), 1e-12)

    # Refine so the field is sampled several times per smallest target cell.
    span = float(s[-1] - s[0])
    if span <= 0:
        raise SpacingError("arc coordinate has zero extent")
    want = min(400_000, max(len(s), int(np.ceil(4.0 * span / max(h_raw.min(), 1e-12)))))
    if want > len(s):
        s_fine = np.linspace(s[0], s[-1], want)
        h_raw = np.interp(s_fine, s, h_raw)
        s = s_fine

    def integrate(field: Array) -> tuple[float, Array]:
        density = 1.0 / field
        weight = np.concatenate(
            ([0.0], np.cumsum(0.5 * (density[1:] + density[:-1]) * np.diff(s)))
        )
        return float(weight[-1]), weight

    def field_for(scale: float) -> Array:
        f = h_raw * scale
        return grade(s, f, rate) if rate is not None else f

    def field_for_cap(cap: float) -> Array:
        f = np.minimum(h_raw, cap)
        return grade(s, f, rate) if rate is not None else f

    target = float(n - 1)
    natural, _ = integrate(field_for(1.0))

    if natural <= target:
        # The field asks for FEWER cells than requested, so surplus nodes have
        # to go somewhere. Multiplying the field by lambda < 1 spreads them
        # proportionally, which refines the already-resolved leading edge along
        # with everything else — measured: a root LE cell of 0.138 mm where the
        # curvature law asked for 1.22 mm, and surface aspect ratio 171.
        # Capping the field from above instead (h -> min(h, C)) adds nodes ONLY
        # where cells are coarser than the cap, i.e. in the under-resolved
        # mid-chord run, and leaves every geometrically-sized cell untouched.
        lo, hi = float(h_raw.min()) * 0.5, float(h_raw.max()) * 2.0
        for _ in range(80):
            cap = 0.5 * (lo + hi)
            cells, _w = integrate(field_for_cap(cap))
            if cells > target:
                lo = cap
            else:
                hi = cap
            if abs(cells - target) <= 1e-9 * target:
                break
        cells, weight = integrate(field_for_cap(0.5 * (lo + hi)))
    else:
        lo, hi = 1e-6, 1e6
        for _ in range(80):
            mid = np.sqrt(lo * hi)
            cells, _w = integrate(field_for(mid))
            if cells > target:
                lo = mid
            else:
                hi = mid
            if abs(cells - target) <= 1e-9 * target:
                break
        cells, weight = integrate(field_for(np.sqrt(lo * hi)))
    if weight[-1] <= 0:
        raise SpacingError("size field integrates to zero cells")
    weight = weight / weight[-1]
    return np.interp(np.linspace(0.0, 1.0, n), weight, s)


def cells_for(s: Array, h: Array) -> float:
    """How many cells the size field asks for — the natural resolution."""
    s = np.asarray(s, float)
    density = 1.0 / np.maximum(np.asarray(h, float), 1e-12)
    return float(np.sum(0.5 * (density[1:] + density[:-1]) * np.diff(s)))


def curvature_spacing(points: Array, max_turn_deg: float) -> Array:
    """Target cell size at each vertex so the surface never turns more than
    ``max_turn_deg`` across one cell.

    For a locally circular arc of curvature k, a cell of length h subtends
    h * k radians. Requiring h * k <= theta gives h <= theta / k. This is the
    standard curvature-resolution criterion behind Gmsh's
    ``MeshSizeFromCurvature`` and every commercial mesher's "cells per 2*pi"
    control, stated as an angle so both mesh families can use one number.
    """
    kappa = curvature_polyline(points)
    theta = np.radians(float(max_turn_deg))
    with np.errstate(divide="ignore"):
        return np.where(kappa > 1e-12, theta / np.maximum(kappa, 1e-12), np.inf)
