"""The grid in one station plane (y = const): a C around the ring and the wake, out to the far field.

In the plane (x, z) of station k the Stage 2 ring is fixed (wall nodes are never moved). Ring order: upper
trailing-edge corner (0) -> leading edge (n_side - 1) -> lower trailing-edge corner (2 n_side - 2) -> across the
base. The plane is built from:

    the wake lines   from the two trailing-edge corners to the outflow. Their centre line leaves the base along the
                     base normal and turns to +x over wake.turn_local_c local chords; the two lines sit a half gap
                     above and below it, the gap = the base height + wake.gap_growth x the distance.
    the C line       upper wake line (outflow -> corner), the ring from the upper to the lower corner, the lower wake
                     line (corner -> outflow): one open line, marched outward (march.py) to the far field.
    the far field    a half circle in front (centre at the most aft trailing edge, radius so that every wing point is
                     at least far.distance_c away), straight lines above and below, the outflow far.distance_c behind
                     the most aft trailing edge. It is the same for every station, so the far field is a pure
                     extrusion along the semi-span.
    the base block   between the two wake lines, from the base (a wall) to the outflow, by transfinite interpolation.

Splitting the C at the trailing-edge corners and at the ends of the tip cap's nose arc gives the six blocks of a
station: WU (upper wake), CU, CN, CL (the C around the upper side, the nose arc, the lower side), WL (lower wake)
and B (base). Index orientation: (i, j) with j outward and i such that e_i x e_j points along +y, so a stack of
stations along +y is right-handed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import march as mr
from .laws import VolumeRules

Array = np.ndarray
EULER = 0.5772156649015329


# --- the wake centre line ---------------------------------------------------------------------------------------

def _cin(x: Array) -> Array:
    """Cin(x) = int_0^x (1 - cos t) / t dt (entire; series, |x| <= 3)."""
    x = np.asarray(x, float)
    out = np.zeros_like(x)
    term_num = np.ones_like(x)
    fact = 1.0
    for k in range(1, 16):
        fact *= (2 * k - 1) * (2 * k)
        term_num = term_num * x * x
        out += (-1) ** (k + 1) * term_num / (2 * k * fact)
    return out


def _si(x: Array) -> Array:
    """Si(x) = int_0^x sin t / t dt (series, |x| <= 3)."""
    x = np.asarray(x, float)
    out = np.zeros_like(x)
    p = x.copy()
    fact = 1.0
    for k in range(0, 16):
        if k:
            fact *= (2 * k) * (2 * k + 1)
            p = p * x * x
        out += (-1) ** k * p / ((2 * k + 1) * fact)
    return out


@dataclass
class WakeLine:
    """The wake of one station: a centre line by arc length s, angle phi(s) = phi0 exp(-s / turn)."""
    M: Array            # base mid-point (x, z)
    phi0: float         # initial angle of the base normal from +x [rad]
    turn: float         # turn length [c]
    t_te: float         # base height [c]
    gap_growth: float

    def centre(self, s: Array) -> tuple[Array, Array]:
        s = np.asarray(s, float)
        a = abs(self.phi0)
        if a < 1e-12:
            return np.stack([self.M[0] + s, np.full_like(s, self.M[1])], -1), np.zeros_like(s)
        u = np.exp(-s / self.turn)
        x = s - self.turn * (_cin(a) - _cin(a * u))
        z = np.sign(self.phi0) * self.turn * (_si(a) - _si(a * u))
        return np.stack([self.M[0] + x, self.M[1] + z], -1), self.phi0 * u

    def lines(self, s: Array) -> tuple[Array, Array, Array]:
        """(centre, upper, lower), each (len(s), 2)."""
        c, phi = self.centre(s)
        N = np.stack([-np.sin(phi), np.cos(phi)], -1)
        h = 0.5 * (self.t_te + self.gap_growth * np.asarray(s, float))
        return c, c + h[:, None] * N, c - h[:, None] * N

    def s_at_x(self, x_out: float) -> float:
        lo, hi = 0.0, 2.0 * (x_out - self.M[0]) + 4.0 * self.turn + 1.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if self.centre(np.array([mid]))[0][0, 0] < x_out:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)


def wake_of(ring: Array, n_side: int, chord: float, rl: VolumeRules) -> WakeLine:
    up, lo = ring[0], ring[2 * n_side - 2]
    t = float(np.linalg.norm(up - lo))
    ub = (up - lo) / t
    nb = np.array([ub[1], -ub[0]])                     # the base normal, pointing aft
    w = rl.wake
    return WakeLine(0.5 * (up + lo), float(np.arctan2(nb[1], nb[0])), float(w["turn_local_c"]) * chord, t,
                    float(w["gap_growth"]))


# --- one station ---------------------------------------------------------------------------------------------

@dataclass
class Station:
    """The inputs of one station plane."""
    k: int
    y: float
    ring: Array          # (n_ring, 2): x, z
    chord: float
    re_local: float
    s0: float            # law 13 [c]
    delta: float         # boundary-layer thickness for the 30-cell rule [c]
    g_bl: float          # growth inside delta that gives the level's bl_cells
    wake: WakeLine = None
    s_end: float = 0.0   # arc length of the wake centre line to the outflow
    te_cell: float = 0.0  # the wing's last chordwise cell (the smaller of the two trailing-edge corners) [c]


@dataclass
class Domain:
    """The far field, the same for every station."""
    x_b: float           # centre of the half circle: the most aft trailing edge
    z_m: float
    R: float             # radius (top and bottom lines at z_m +- R)
    x_out: float         # outflow
    x_min: float
    z_min: float
    z_max: float


def domain(rings: list[Array], n_side: int, rl: VolumeRules) -> Domain:
    xs = np.concatenate([r[:, 0] for r in rings])
    zs = np.concatenate([r[:, 1] for r in rings])
    x_te = max(float(max(r[0, 0], r[2 * n_side - 2, 0])) for r in rings)
    z_m = 0.5 * (zs.min() + zs.max())
    far = rl.far_distance
    # every wall point at least `far` inside: the circle reaches x_b - R, the wing starts at xs.min()
    R = far + max(x_te - xs.min(), zs.max() - z_m, z_m - zs.min()) + 1.0
    return Domain(x_te, float(z_m), float(R), x_te + far + 1.0, float(xs.min()), float(zs.min()), float(zs.max()))


def wake_lengths(st: Station, dom: Domain, rl: VolumeRules) -> tuple[dict, float]:
    """The arguments of the streamwise distribution along the wake (from the base to the outflow) and its length."""
    b = rl.band
    L = st.wake.s_at_x(dom.x_out)
    L_band = float(b["length_local_c"]) * st.chord
    k_cell = (np.tan(np.radians(b["alpha_hi_deg"])) - np.tan(np.radians(b["alpha_lo_deg"]))) / b["fan_cells"]
    a = float(b["max_aspect"])
    args = dict(g_bl=rl.wall_growth, delta=0.0, g_fine=rl.wall_growth, fine=L_band, g_far=rl.far_growth_built,
                cap_a=a * b["spacing_c"], cap_b=a * k_cell, cap_h=L_band)
    return args, L


def first_wake_cell(s: Array, st: Station, n_base: int, rl: VolumeRules) -> Array:
    """First cell off the wake line at arc length s: s0 at the corner, then the base block's own cell (the gap / its
    cell count), so the cells match across the wake line."""
    gap = st.wake.t_te + st.wake.gap_growth * np.asarray(s, float)
    target = gap / (n_base - 1)
    return st.s0 + (target - st.s0) * (1.0 - np.exp(-np.asarray(s, float) / max(st.wake.t_te, 1e-12)))


@dataclass
class PlaneLayout:
    """Index layout of the combined C line of one station."""
    n_side: int
    n_base: int
    n_w: int             # nodes along each wake line, corner included

    @property
    def half(self) -> int:
        return (self.n_base - 1) // 2

    @property
    def le(self) -> int:
        return self.n_side - 1

    @property
    def n_air(self) -> int:
        return 2 * self.n_side - 1

    @property
    def n_c(self) -> int:
        return 2 * (self.n_w - 1) + self.n_air

    @property
    def i_te_up(self) -> int:
        return self.n_w - 1

    @property
    def i_te_lo(self) -> int:
        return self.n_w - 1 + 2 * self.n_side - 2

    def blocks(self) -> dict[str, tuple[int, int]]:
        """Combined-C index range (first, last) of each C-type block."""
        u, le, h = self.i_te_up, self.le, self.half
        return {"WU": (0, u), "CU": (u, u + le - h), "CN": (u + le - h, u + le + h),
                "CL": (u + le + h, self.i_te_lo), "WL": (self.i_te_lo, self.n_c - 1)}


def far_nodes(lay: PlaneLayout, dom: Domain, air_frac: Array, even_share: float, wake_x: Array | None = None
              ) -> tuple[Array, Array]:
    """The far-field nodes of the combined C (n_c, 2) and their outward normals. air_frac (n_air,): the mean arc
    fraction of the airfoil nodes over the stations (0 at the upper corner, 1 at the lower corner). wake_x (n_w,):
    the far-field nodes above and below the wake, as distances behind the arc's end (0 first); None = geometric
    from the arc's end cell. Following the wake's own spacing keeps the wake lines straight up and down."""
    n_air, n_w = lay.n_air, lay.n_w
    phi = even_share * np.linspace(0.0, 1.0, n_air) + (1.0 - even_share) * air_frac
    th = np.pi / 2 + np.pi * phi
    arc = np.stack([dom.x_b + dom.R * np.cos(th), dom.z_m + dom.R * np.sin(th)], -1)
    arc_n = np.stack([np.cos(th), np.sin(th)], -1)
    Lx = dom.x_out - dom.x_b
    if wake_x is None:
        h0 = 0.5 * (np.linalg.norm(arc[1] - arc[0]) + np.linalg.norm(arc[-1] - arc[-2]))
        xs = dom.x_b + geometric(h0, Lx, n_w - 1)
    else:
        xs = dom.x_b + np.asarray(wake_x, float) * (Lx / float(wake_x[-1]))
    top = np.stack([xs[::-1], np.full(n_w, dom.z_m + dom.R)], -1)          # outflow -> arc top
    bot = np.stack([xs, np.full(n_w, dom.z_m - dom.R)], -1)                # arc bottom -> outflow
    Q = np.vstack([top[:-1], arc, bot[1:]])
    m = np.vstack([np.tile([0.0, 1.0], (n_w - 1, 1)), arc_n, np.tile([0.0, -1.0], (n_w - 1, 1))])
    Q[n_w - 1] = [dom.x_b, dom.z_m + dom.R]
    Q[n_w - 1 + n_air - 1] = [dom.x_b, dom.z_m - dom.R]
    return Q, m


def geometric(h0: float, L: float, n: int) -> Array:
    """n + 1 distances 0 .. L with first cell h0 and a constant ratio (found by bisection); uniform if h0 * n >= L."""
    if h0 * n >= L:
        return np.linspace(0.0, L, n + 1)
    lo, hi = 1.0 + 1e-12, 10.0
    for _ in range(200):
        r = 0.5 * (lo + hi)
        if h0 * (r ** n - 1.0) / (r - 1.0) < L:
            lo = r
        else:
            hi = r
    r = 0.5 * (lo + hi)
    d = np.concatenate([[0.0], h0 * np.cumsum(r ** np.arange(n))])
    return d * (L / d[-1])


def c_line(st: Station, lay: PlaneLayout, s_q: Array) -> tuple[Array, dict]:
    """The combined C line of one station (n_c, 2) and its wake pieces."""
    c, upw, low = st.wake.lines(s_q)
    upw[0] = st.ring[0]
    low[0] = st.ring[2 * lay.n_side - 2]
    air = st.ring[: lay.n_air]
    X = np.vstack([upw[:0:-1], air, low[1:]])
    return X, {"centre": c, "upper": upw, "lower": low}


def band_height(st: Station, rl: VolumeRules) -> float:
    """The top of the wake band above the wake line, where the envelope ends (laws 17, 18): margin + band length x
    tan(the steeper band edge), plus how far the wake centre line drops below a straight line within the band length
    (decision 106: a wake that leaves the base pointing down puts the band's upper edge that much higher above the
    wake line; V6 refused 20 full-space wings before this term)."""
    b = rl.band
    L_band = float(b["length_local_c"]) * st.chord
    t = max(np.tan(np.radians(b["alpha_hi_deg"])), np.tan(np.radians(-b["alpha_lo_deg"])))
    drop = 0.0
    if st.wake is not None:
        c, _ = st.wake.centre(np.linspace(0.0, L_band, 33))
        drop = max(0.0, float(-(c[:, 1] - st.wake.M[1]).min()))
    return float(b["margin_c"]) + L_band * t + drop


def station_spec(st: Station, L: float, rl: VolumeRules) -> dict:
    """The one wall-normal distribution of a station (decision 84): every line of the station plane, wall and wake
    alike, takes it and shortens only its outer part to its own length (shrink), so neighbouring lines have the same
    layers near the wall and the cells stay square where the lines bunch (behind the trailing edge). It carries:
    first cell s0 (law 13), at least bl_cells across delta (law 14), the level's wall growth out to the fine zone
    (law 20), the wake band as an envelope in height (law 18: cells <= the band cell of the farthest point of the
    band at that height, so every line of the band holds the band), then far.growth (law 15).
    The wake lines keep the wall spacing along the cut (as classic C meshes do)."""
    b = rl.band
    L_band = float(b["length_local_c"]) * st.chord
    t_hi = np.tan(np.radians(b["alpha_hi_deg"]))
    t_lo = np.tan(np.radians(-b["alpha_lo_deg"]))
    k = (np.tan(np.radians(b["alpha_hi_deg"])) - np.tan(np.radians(b["alpha_lo_deg"]))) / b["fan_cells"]
    H = band_height(st, rl)
    return dict(s0=st.s0, L=float(L), g_bl=st.g_bl, delta=st.delta, g_fine=rl.wall_growth,
                fine=rl.fine_zone_local_c * st.chord, g_far=rl.far_growth_built,
                cap_a=float(b["spacing_c"]), cap_b=k / max(t_hi, t_lo), cap_m=float(b["margin_c"]), cap_h=H)


def shrink(d_ref: Array, L: Array, power: float = 8.0) -> Array:
    """d_ref (n+1,) from 0 to L_ref -> (n+1, len(L)) ending at L <= L_ref; the outer cells shrink, the first cells
    stay exact, and every growth ratio can only fall."""
    L_ref = d_ref[-1]
    w = (d_ref / L_ref) ** power
    eps = L / L_ref - 1.0
    out = d_ref[:, None] * (1.0 + eps[None, :] * w[:, None])
    out[-1] = L
    return out


def base_block(st: Station, lay: PlaneLayout, wake: dict, n_side: int) -> Array:
    """The base block (n_base, n_w, 2): i across the base (lower -> upper wake line), j along the wake."""
    nb, nw = lay.n_base, lay.n_w
    ring = st.ring
    base = np.vstack([ring[2 * n_side - 2: 2 * n_side - 1], ring[2 * n_side - 1:], ring[:1]])   # lower -> upper
    if len(base) != nb:
        raise AssertionError("base nodes")
    lo, up = wake["lower"], wake["upper"]
    v = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(base, axis=0), axis=1))])
    v /= v[-1]
    out = lo[-1][None, :] + v[:, None] * (up[-1] - lo[-1])[None, :]
    ul = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(lo, axis=0), axis=1))])
    uu = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(up, axis=0), axis=1))])
    ul /= ul[-1]
    uu /= uu[-1]
    V = v[:, None, None]
    U = ((1 - v)[:, None] * ul[None, :] + v[:, None] * uu[None, :])[:, :, None]
    G = ((1 - V) * lo[None] + V * up[None]
         + (1 - U) * base[:, None] + U * out[:, None]
         - ((1 - U) * (1 - V) * base[0] + (1 - U) * V * base[-1] + U * (1 - V) * out[0] + U * V * out[-1]))
    G[0], G[-1] = lo, up
    G[:, 0], G[:, -1] = base, out
    return G


@dataclass
class PlaneGrid:
    """The 2-D blocks of one station: name -> (ni, nj, 2) in (x, z)."""
    blocks: dict
    info: dict = field(default_factory=dict)
