"""The wall-normal distribution and the march in one station plane.

Distribution (laws 13, 14, 15, 18, 20). Along one grid line the cells grow from a first cell s0:
    inside the boundary layer (distance < delta)   growth <= g_bl (so that at least bl_cells cells cross delta)
    inside the fine zone (distance < fine)         growth <= g_fine (the level's wall growth)
    beyond                                         growth <= g_far
    inside a band (distance < cap_h)               cell <= cap_a + cap_b * distance (the wake band)
Every line of a station plane, and every station, has the same count n (one structured index). The fewest cells
that meet every limit are counted first; the lines that need fewer than n are filled by one factor lam in (0, 1]
that scales every growth (1 + lam (g - 1)) and every cap (lam * cap), found by bisection so that the n-th node
lands on the line's end. So a filled line meets every limit, and its first cell is exactly s0.

March (the plane method chosen in V0, decision 84). The layers are built one after another from the wall line:
each node steps along the smoothed normal of the layer just built, by its line's own step; from blend_from (one
local chord) out, the node is pulled toward its far-field node, with weight ((j - j0)/(n - j0))^2, so the last
layer is the far-field boundary exactly. The step length is never smoothed (s0 and the growth stay exact); the
direction is: a few passes of averaging with the neighbours, more far out, none at the first layer.
"""

from __future__ import annotations

import numpy as np

Array = np.ndarray


# --- distributions -------------------------------------------------------------------------------------------

RAMP = 0.25      # each zone change ramps over 25 % of its distance past the boundary (the limit holds up to it)


def _ramp(x, x0, a, b):
    """a up to x0, then linearly to b over RAMP * x0: continuous, so the count is continuous in lam."""
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        w = np.where(x0 > 0, np.clip((x - x0) / np.where(x0 > 0, RAMP * x0, 1.0), 0.0, 1.0), 1.0)
    return a + (b - a) * w


def _walk(s0, L, g_bl, delta, g_fine, fine, g_far, cap_a, cap_b, cap_h, lam, n_max, cap_m=None):
    """Greedy distances for many lines at once (arrays of shape (N,)). Returns d (n_max+1, N).
    Growth: g_bl up to delta, g_fine up to fine, g_far beyond, each change ramped (RAMP) past its boundary. Cap
    (the wake band envelope): cap_a + cap_b * max(0, x - cap_m) up to cap_h; past cap_h it goes on rising as the
    growth law itself does (slope g_fine - 1: a geometric line has dh/dx = g - 1), so the cells leave the band
    smoothly, at the same place at every level, wherever the last band node falls (check 13); every limit is
    continuous in x. lam (<= 1) scales the growth only: the cap is a rule (law 18) and stays the same on every line
    and at every level."""
    cap_m = np.zeros_like(s0) if cap_m is None else cap_m
    N = s0.shape[0]
    d = np.zeros((n_max + 1, N))
    step = s0.copy()
    d[1] = step
    has_cap = cap_h > 0
    for j in range(1, n_max):
        x = d[j]
        g = np.where(x <= fine, _ramp(x, delta, g_bl, g_fine), _ramp(x, fine, g_fine, g_far))
        g = 1.0 + lam * (g - 1.0)
        nxt = step * g
        cap = cap_a + cap_b * np.maximum(x - cap_m, 0.0) + (g_fine - 1.0) * np.maximum(x - cap_h, 0.0)
        nxt = np.where(has_cap, np.minimum(nxt, cap), nxt)
        step = nxt
        d[j + 1] = x + step
    return d


def _fractional_count(d: Array, L: Array) -> Array:
    """Cells needed to reach L (fractional): the index where d crosses L, plus the fraction of that cell."""
    above = d >= L[None, :]
    m = np.argmax(above, axis=0)                     # first index with d >= L
    m = np.where(above.any(axis=0), m, d.shape[0])   # not reached
    mm = np.clip(m, 1, d.shape[0] - 1)
    cols = np.arange(d.shape[1])
    lo, hi = d[mm - 1, cols], d[mm, cols]
    frac = np.where(hi > lo, (L - lo) / np.where(hi > lo, hi - lo, 1.0), 1.0)
    return np.where(m >= d.shape[0], np.inf, (mm - 1) + frac)


def min_cells(s0, L, g_bl, delta, g_fine, fine, g_far, cap_a=None, cap_b=None, cap_h=None, cap_m=None,
              n_max=4000) -> Array:
    """The fewest cells (fractional) each line needs to reach L with every limit met."""
    s0, L = np.atleast_1d(np.asarray(s0, float)), np.atleast_1d(np.asarray(L, float))
    z = np.zeros_like(s0)
    args = [np.broadcast_to(np.asarray(a, float), s0.shape).copy() for a in (g_bl, delta, g_fine, fine, g_far)]
    ca = z if cap_a is None else np.broadcast_to(np.asarray(cap_a, float), s0.shape).copy()
    cb = z if cap_b is None else np.broadcast_to(np.asarray(cap_b, float), s0.shape).copy()
    ch = z if cap_h is None else np.broadcast_to(np.asarray(cap_h, float), s0.shape).copy()
    cm = z if cap_m is None else np.broadcast_to(np.asarray(cap_m, float), s0.shape).copy()
    # count in chunks of n so long lines do not need a huge array
    n = 64
    while True:
        d = _walk(s0, L, *args, ca, cb, ch, np.ones_like(s0), n, cm)
        f = _fractional_count(d, L)
        if np.all(np.isfinite(f)) or n >= n_max:
            return f
        n *= 2


def fill(s0, L, n, g_bl, delta, g_fine, fine, g_far, cap_a=None, cap_b=None, cap_h=None, cap_m=None,
         iters=60) -> tuple[Array, Array]:
    """Distances d (n+1, N) from 0 to L in exactly n cells per line, first cell s0, every limit met.
    Returns (d, lam): lam = 1 where the line needed all n cells, < 1 where its growth was scaled down (the caps never
    are)."""
    s0, L = np.atleast_1d(np.asarray(s0, float)), np.atleast_1d(np.asarray(L, float))
    z = np.zeros_like(s0)
    b = lambda a: np.broadcast_to(np.asarray(a, float), s0.shape).copy()
    args = [b(a) for a in (g_bl, delta, g_fine, fine, g_far)]
    ca, cb, ch, cm = (z if a is None else b(a) for a in (cap_a, cap_b, cap_h, cap_m))
    lo, hi = np.zeros_like(s0), np.ones_like(s0)      # count(hi = 1) <= n is required; count(lam -> 0) = inf
    f1 = _fractional_count(_walk(s0, L, *args, ca, cb, ch, hi, n + 2, cm), L)
    if np.any(f1 > n + 1e-9):
        raise ValueError(f"fill: {int(np.sum(f1 > n + 1e-9))} lines need more than n = {n} cells "
                         f"(most: {np.max(f1):.2f})")
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        f = _fractional_count(_walk(s0, L, *args, ca, cb, ch, mid, n + 2, cm), L)
        ok = f <= n                                   # mid reaches L within n cells: lam may grow? no: smaller lam
        hi = np.where(ok, mid, hi)                    # = more cells; keep the smallest lam that still fits
        lo = np.where(ok, lo, mid)
    lam = hi
    d = _walk(s0, L, *args, ca, cb, ch, lam, n + 2, cm)[: n + 1].copy()
    # the n-th node lands on L to the bisection tolerance; place it exactly and spread the tiny rest over the outer
    # cells so the first cells stay exact
    err = L - d[n]
    w = (d / np.where(d[n] > 0, d[n], 1.0)) ** 8
    d = d + err[None, :] * w
    d[n] = L
    return d, lam


def bl_growth(s0: Array, delta: Array, cells: float, g_max: float, iters: int = 60) -> Array:
    """The largest growth g <= g_max with at least `cells` cells between the wall and delta (first cell s0):
    n(g) = ln(1 + (g - 1) delta / s0) / ln g is decreasing in g."""
    s0, delta = np.asarray(s0, float), np.asarray(delta, float)
    n_of = lambda g: np.log1p((g - 1.0) * delta / s0) / np.log(g)
    ok = n_of(np.full_like(s0, g_max)) >= cells
    lo, hi = np.full_like(s0, 1.0 + 1e-9), np.full_like(s0, g_max)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        good = n_of(mid) >= cells
        lo, hi = np.where(good, mid, lo), np.where(good, hi, mid)
    return np.where(ok, g_max, lo)


# --- the march -----------------------------------------------------------------------------------------------

def cw(v: Array) -> Array:
    """Rotate in-plane (x, z) vectors by -90 deg: the outward normal of a line walked in index order."""
    return np.stack([v[..., 1], -v[..., 0]], axis=-1)


def unit(v: Array) -> Array:
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def line_normals(X: Array, fixed_ends: tuple[Array | None, Array | None] = (None, None)) -> Array:
    """Unit normals of an open line: at each node the mean of the two adjacent segments' unit normals (the angle
    bisector); the ends take their one segment's normal unless a direction is given."""
    seg = np.diff(X, axis=0)
    ns = unit(cw(seg))
    n = np.empty_like(X)
    n[1:-1] = unit(ns[:-1] + ns[1:])
    n[0], n[-1] = ns[0], ns[-1]
    if fixed_ends[0] is not None:
        n[0] = fixed_ends[0]
    if fixed_ends[1] is not None:
        n[-1] = fixed_ends[1]
    return n


def smooth_normals(n: Array, passes: int, keep_ends: bool = True) -> Array:
    for _ in range(int(passes)):
        m = n.copy()
        m[1:-1] = 0.5 * n[1:-1] + 0.25 * (n[:-2] + n[2:])
        if not keep_ends:
            m[0] = 0.5 * (n[0] + n[1])
            m[-1] = 0.5 * (n[-1] + n[-2])
        n = unit(m)
    return n


def march(X0: Array, d: Array, Q: Array, m_out: Array, j0: Array, passes: int, power: float = 2.0,
          end_dirs: tuple[Array, Array] | None = None, ramp_layers: int = 4) -> Array:
    """March the open line X0 (N, 2) outward: layer j+1 = layer j + (d[j+1] - d[j]) * normal (smoothed), then
    pulled toward T = Q - (L - d) m_out with weight ((j - j0) / (n - j0))^power from j0 (per line) on.
    d (n+1, N) distances; Q (N, 2) far-field nodes; m_out (N, 2) the far field's outward unit normals.
    The first layer steps along the unsmoothed bisector normals; the smoothing passes ramp up over ramp_layers."""
    n = d.shape[0] - 1
    N = X0.shape[0]
    L = d[-1]
    G = np.empty((n + 1, N, 2))
    G[0] = X0
    X = X0.copy()
    jj = np.arange(n + 1)[:, None]
    span = np.maximum(n - j0, 1)[None, :]
    W = np.clip((jj - j0[None, :]) / span, 0.0, 1.0) ** power          # (n+1, N)
    ends = end_dirs or (None, None)
    for j in range(n):
        nrm = line_normals(X, ends)
        p = 0 if j == 0 else int(round(passes * min(1.0, j / max(ramp_layers, 1))))
        if p:
            nrm = smooth_normals(nrm, p)
            if ends[0] is not None:
                nrm[0] = ends[0]
            if ends[1] is not None:
                nrm[-1] = ends[1]
        Xn = X + (d[j + 1] - d[j])[:, None] * nrm
        T = Q - (L - d[j + 1])[:, None] * m_out
        w = W[j + 1][:, None]
        Xn = (1.0 - w) * Xn + w * T
        G[j + 1] = Xn
        X = Xn
    G[n] = Q
    return G


# --- paths: the line shapes from one common front ----------------------------------------------------------------
#
# The node distributions differ from line to line (the wall lines carry s0 and the boundary-layer zone, the wake
# lines relax), so marching the nodes themselves would tilt each layer across the trailing edge. The shapes of the
# lines are therefore traced first by one front that moves the same distance everywhere (an offset of the C line),
# smoothed along itself over a width kappa x its distance from the wall: at the wall no smoothing (the lines leave
# square to the wall), far out a smooth curve, and a concave corner is rounded at the scale of the distance, so the
# front never folds. From the distance `switch` on, every path runs straight along its last direction to the far
# field. The nodes of each line are then placed along its path at the line's own distances (place()).

def _smooth_implicit(n: Array, X: Array, sigma: float, fixed: tuple[bool, bool] = (True, True)) -> Array:
    """Diffuse the unit vectors n (N, 2) along the line X by arc length, Gaussian width sigma: solve
    (I - tau L) m = n, tau = sigma^2 / 2, L the arc-length Laplacian (tridiagonal); the ends held if fixed."""
    from scipy.linalg import solve_banded
    N = len(X)
    h = np.linalg.norm(np.diff(X, axis=0), axis=1)
    h = np.maximum(h, 1e-300)
    tau = 0.5 * sigma * sigma
    lo = np.zeros(N)
    up = np.zeros(N)
    di = np.ones(N)
    hm, hp = h[:-1], h[1:]
    a = tau / (0.5 * (hm + hp))
    cl, cr = a / hm, a / hp
    di[1:-1] = 1.0 + cl + cr
    lo[1:-1] = -cl                      # coefficient of n[i-1] in row i
    up[1:-1] = -cr                      # coefficient of n[i+1] in row i
    if not fixed[0]:
        di[0] = 1.0 + tau / h[0] ** 2
        up[0] = -tau / h[0] ** 2
    if not fixed[1]:
        di[-1] = 1.0 + tau / h[-1] ** 2
        lo[-1] = -tau / h[-1] ** 2
    ab = np.zeros((3, N))
    ab[0, 1:] = up[:-1]
    ab[1] = di
    ab[2, :-1] = lo[1:]
    m = solve_banded((1, 1), ab, n)
    return unit(m)


def outer_hit(X: Array, v: Array, dom) -> tuple[Array, Array]:
    """Where the rays X + t v (t > 0) leave the far-field boundary: the half circle (centre (x_b, z_m), radius R,
    x <= x_b) or the lines z = z_m +- R (x >= x_b). Returns the points and the boundary's outward normals."""
    cx, cz, R = dom.x_b, dom.z_m, dom.R
    px, pz = X[:, 0] - cx, X[:, 1] - cz
    b = px * v[:, 0] + pz * v[:, 1]
    c = px * px + pz * pz - R * R
    t_circ = -b + np.sqrt(np.maximum(b * b - c, 0.0))          # |v| = 1; X inside the circle
    with np.errstate(divide="ignore", invalid="ignore"):
        t_top = np.where(v[:, 1] > 1e-14, (R - pz) / v[:, 1], np.inf)
        t_bot = np.where(v[:, 1] < -1e-14, (-R - pz) / v[:, 1], np.inf)
    t_line = np.minimum(t_top, t_bot)
    P_line = X + t_line[:, None] * v
    P_circ = X + t_circ[:, None] * v
    use_line = (P_line[:, 0] >= cx) & np.isfinite(t_line)
    P = np.where(use_line[:, None], P_line, P_circ)
    nrm = np.where(use_line[:, None], np.stack([np.zeros(len(X)), np.sign(P[:, 1] - cz)], -1),
                   unit(np.stack([P_circ[:, 0] - cx, P_circ[:, 1] - cz], -1)))
    # exactly on the boundary
    P[use_line, 1] = cz + np.sign(P[use_line, 1] - cz) * R
    return P, nrm


def front(X0: Array, d_front: Array, kappa: float, end_dirs: tuple[Array, Array]) -> tuple[Array, Array]:
    """The front moved by the common distances d_front (d_front[0] = 0), smoothed over kappa x its distance.
    Returns the front positions (n_front, N, 2) and the smoothed normals of the last front (N, 2)."""
    N = len(X0)
    P = np.empty((len(d_front), N, 2))
    P[0] = X0
    X = X0.copy()
    for j in range(1, len(d_front)):
        n = line_normals(X, end_dirs)
        sig = kappa * d_front[j - 1]
        if sig > 0:
            n = _smooth_implicit(n, X, sig)
            n[0], n[-1] = end_dirs
        X = X + (d_front[j] - d_front[j - 1]) * n
        P[j] = X
    n = _smooth_implicit(line_normals(X, end_dirs), X, kappa * d_front[-1])
    n[0], n[-1] = end_dirs
    return P, n


def on_boundary(P: Array, dom) -> Array:
    """Project points onto the far-field boundary: vertically onto the lines (x >= x_b), radially onto the circle."""
    P = P.copy()
    line = P[:, 0] >= dom.x_b
    P[line, 1] = dom.z_m + np.sign(P[line, 1] - dom.z_m) * dom.R
    v = unit(P[~line] - np.array([dom.x_b, dom.z_m]))
    P[~line] = np.array([dom.x_b, dom.z_m]) + dom.R * v
    return P


def paths(F: Array, Q: Array, n_ray: int = 24) -> Array:
    """Close the fronts F (n_front, N, 2) with one straight piece from the last front to the far-field nodes Q,
    sampled at n_ray points (geometric, so the interpolation stays fine near the front)."""
    t = np.geomspace(1e-3, 1.0, n_ray)
    t = (t - t[0]) / (t[-1] - t[0])
    seg = F[-1][None] + t[1:, None, None] * (Q - F[-1])[None]
    return np.concatenate([F, seg], axis=0)


def path_length(P: Array) -> Array:
    """Cumulative arc length along every path (n_p, N)."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=2)
    return np.vstack([np.zeros((1, P.shape[1])), np.cumsum(seg, axis=0)])


def place(P: Array, S: Array, d: Array) -> Array:
    """Nodes at the distances d (n+1, N) along the paths P (n_p, N, 2) with arc lengths S (n_p, N)."""
    n1, N = d.shape
    G = np.empty((n1, N, 2))
    for i in range(N):
        G[:, i, 0] = np.interp(d[:, i], S[:, i], P[:, i, 0])
        G[:, i, 1] = np.interp(d[:, i], S[:, i], P[:, i, 1])
    G[-1] = P[-1]
    G[0] = P[0]
    return G
