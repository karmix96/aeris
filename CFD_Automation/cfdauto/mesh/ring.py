"""One closed ring of points around the section at one span station.

Ring order (as in S8): upper trailing-edge corner -> leading edge -> lower
trailing-edge corner -> across the blunt base. Unique nodes:
2 * n_side + n_base - 3.

Every node is asked from the loft at (u = x/c, v); nothing is interpolated
between stored sections. The dense curve is used only to turn arc length into u.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .laws import Rules
from .spacing import cells_needed, equidistribute, fill_to_count, flat_ends, limit_growth

Array = np.ndarray
NOSE_FLAT_CELLS = 4


@dataclass
class Section:
    """The dense description of one station: u against arc length on each side."""

    loft: object
    v: float
    u: Array          # dense chord fractions, 0 (nose) -> 1 (trailing edge)
    arc_up: Array     # arc length from the nose, upper surface [m]
    arc_lo: Array
    chord: float
    y: float

    @classmethod
    def at(cls, loft, v: float, n_dense: int) -> "Section":
        u = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n_dense)))   # dense at the nose and the trailing edge
        vv = np.full_like(u, float(v))
        up, lo = loft.upper(u, vv), loft.lower(u, vv)
        arc = lambda p: np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        le = up[0]
        te_mid = 0.5 * (up[-1] + lo[-1])
        return cls(loft, float(v), u, arc(up), arc(lo), float(np.linalg.norm(te_mid - le)), float(le[1]))

    def side(self, upper: bool) -> Array:
        return self.arc_up if upper else self.arc_lo

    def curvature_radius(self, upper: bool) -> Array:
        """Radius of curvature [m] of the dense section curve at every dense node (smoothed over
        5 steps); large where the curve is straight. Computed once per side."""
        cache = self.__dict__.setdefault("_radius", {})
        if upper not in cache:
            cache[upper] = self._curvature_radius(upper)
        return cache[upper]

    def _curvature_radius(self, upper: bool) -> Array:
        vv = np.full_like(self.u, self.v)
        p = self.loft.upper(self.u, vv) if upper else self.loft.lower(self.u, vv)
        d = np.diff(p, axis=0)
        L = np.linalg.norm(d, axis=1)
        t = d / np.maximum(L, 1e-300)[:, None]
        ang = np.arccos(np.clip((t[1:] * t[:-1]).sum(1), -1.0, 1.0))        # at nodes 1 .. n-2
        kappa = ang / np.maximum(0.5 * (L[1:] + L[:-1]), 1e-300)
        kappa = np.convolve(np.pad(kappa, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        kappa = np.concatenate([[kappa[0]], kappa, [kappa[-1]]])
        return 1.0 / np.maximum(kappa, 1e-300)

    def size_field(self, upper: bool, h_le: float, h_band: float, h_max: float, h_te: float,
                   band: tuple[float, float], growth: float, turning_deg: float | None = None) -> Array:
        """Target cell size [m] along one side (on the dense arc grid).

        The band is widened by one band cell at each edge, so a cell whose middle is inside
        the band is not stretched by the growth just outside it. With turning_deg, no cell away
        from the nose (x/c > 0.5 %) may turn the surface by more than that angle (law 1 applied
        along the whole ring: the start of the trailing-edge opening is a tight bend on very
        small chords); at the nose the turning is solved on the ring as built instead."""
        h = np.full_like(self.u, h_max)
        s = self.side(upper)
        a, b = np.interp(band, self.u, s)
        h[(s >= a - h_band) & (s <= b + h_band)] = min(h_band, h_max)
        if turning_deg is not None:
            aft = self.u > 0.005
            h[aft] = np.minimum(h[aft], np.radians(turning_deg) * self.curvature_radius(upper)[aft])
        # the nose size is held over the first few cells (NOSE_FLAT_CELLS), not only the first one:
        # the nose radius of the loft changes fast over the first 0.1 % c, and with cells growing
        # from the first one the largest turning sat on a growing cell and did not fall steadily as
        # the nose spacing was reduced
        return limit_growth(s, flat_ends(s, h, NOSE_FLAT_CELLS * h_le, h_te), growth)


@dataclass
class RingSpec:
    """The spacings asked at one station, in metres."""

    h_le: float
    h_band: float
    h_max: float
    h_te: float


def fields(sec: Section, spec: RingSpec, rules: Rules) -> Array:
    """One size field for both sides, on the upper arc: the stricter of the two sides at the
    same fraction of the side's arc length.

    Both sides get the same distribution in arc fraction s / L (nearly the same x/c at every ring
    index on a thin section). Then the tip cap's cross lines join upper and lower points at about
    the same x/c and stay upright; with a different distribution per side (upper band at the
    front, lower band at the back) they slanted across the thin trailing-edge region and the cap
    quads collapsed (scaled Jacobian 0.03 on the BWB reference wings at Re 3e6). Sharing x/c
    itself does not work: on a cambered nose the arc per x/c differs between the sides right
    at the leading edge (the lower first cell came out 2.5 x the upper one). The lower side is
    checked afterwards as built.
    """
    up = sec.size_field(True, spec.h_le, spec.h_band, spec.h_max, spec.h_te, rules.band_upper, rules.chord_growth,
                        rules.nose_turning_deg)
    lo = sec.size_field(False, spec.h_le, spec.h_band, spec.h_max, spec.h_te, rules.band_lower, rules.chord_growth,
                        rules.nose_turning_deg)
    l_up, l_lo = sec.arc_up[-1], sec.arc_lo[-1]
    lo_at = np.interp(sec.arc_up / l_up * l_lo, sec.arc_lo, lo)      # lower field at the same arc fraction
    h = np.minimum(up, lo_at * l_up / l_lo)                          # a lower cell measured on the upper arc
    return limit_growth(sec.arc_up, h, rules.chord_growth)


def cells_per_side(sec: Section, spec: RingSpec, rules: Rules) -> float:
    """Cells needed per side (both sides get the same count and distribution, as the tip cap needs)."""
    return cells_needed(sec.arc_up, fields(sec, spec, rules))


def build_ring(sec: Section, spec: RingSpec, rules: Rules, n_side: int) -> dict:
    """The ring with n_side points per side (nose and corners included) and the rules' base."""
    h = fill_to_count(sec.arc_up, fields(sec, spec, rules), n_side)   # extra points to the largest cells first
    s_up = equidistribute(sec.arc_up, h, n_side)
    frac = s_up / sec.arc_up[-1]
    u_up = np.interp(s_up, sec.arc_up, sec.u)
    u_lo = np.interp(frac * sec.arc_lo[-1], sec.arc_lo, sec.u)
    for u in (u_up, u_lo):
        u[0], u[-1] = 0.0, 1.0
    p_up = sec.loft.upper(u_up, np.full_like(u_up, sec.v))
    p_lo = sec.loft.lower(u_lo, np.full_like(u_lo, sec.v))
    n_base = rules.n_base
    t = np.linspace(0.0, 1.0, n_base)[1:-1]
    base = p_lo[-1][None, :] + t[:, None] * (p_up[-1] - p_lo[-1])[None, :]
    ring = np.vstack([p_up[::-1], p_lo[1:], base])
    return {"ring": ring, "u_upper": u_up, "u_lower": u_lo, "n_side": n_side, "n_base": n_base}


def turning(ring: Array) -> Array:
    """Turning angle [deg] of the closed ring at every node."""
    prev = ring - np.roll(ring, 1, axis=0)
    nxt = np.roll(ring, -1, axis=0) - ring
    a = prev / np.linalg.norm(prev, axis=1)[:, None]
    b = nxt / np.linalg.norm(nxt, axis=1)[:, None]
    return np.degrees(np.arccos(np.clip((a * b).sum(axis=1), -1.0, 1.0)))


KINK_DEG = 1.0     # a dense step turning more than this is a kink of the geometry, not curvature


def geometry_kinks(sec: Section) -> dict:
    """Where the loft section itself has a kink: dense nodes turning by more than KINK_DEG per step.

    A smooth section sampled at the dense count turns well under 1 deg per step everywhere (0.8 deg
    at the sharpest nose seen). The trailing-edge opening on very small chords (the thickness floor
    of 0.5 mm is 4 % of a 12 mm chord) makes a wedge with a kink of about 10 deg at its start.
    """
    out = {"upper": [], "lower": [], "max_deg": 0.0}
    vv = np.full_like(sec.u, sec.v)
    for name, p in (("upper", sec.loft.upper(sec.u, vv)), ("lower", sec.loft.lower(sec.u, vv))):
        d = np.diff(p, axis=0)
        t = d / np.maximum(np.linalg.norm(d, axis=1), 1e-300)[:, None]
        ang = np.degrees(np.arccos(np.clip((t[1:] * t[:-1]).sum(1), -1.0, 1.0)))
        ang[:3] = 0.0                                    # the first dense steps at the nose are polyline noise
        k = np.flatnonzero(ang > KINK_DEG)
        for i in k:
            out[name].append((float(sec.u[i + 1]), float(ang[i])))
        if len(k):
            out["max_deg"] = max(out["max_deg"], float(ang[k].max()))
    return out


def kink_mask(u_upper: Array, u_lower: Array, kinks: dict, n_side: int) -> Array:
    """Ring nodes to leave out of the turning check: the two nearest each geometry kink, per side."""
    mask = np.zeros(2 * n_side - 1, dtype=bool)
    for name, u, offset, rev in (("upper", u_upper, 0, True), ("lower", u_lower, n_side - 1, False)):
        for u_k, _ in kinks[name]:
            near = np.argsort(np.abs(u - u_k))[:2]
            idx = (n_side - 1 - near) if rev else (offset + near)
            mask[idx] = True
    return mask


def nose_turning(ring: Array, n_side: int, ignore: Array | None = None) -> float:
    """Largest turning of any ring node except the two trailing-edge corners (and the nodes at
    geometry kinks, which no cell size can reduce): the number law 1 controls.

    Not only the nodes next to the leading edge: on cambered sections the highest curvature sits a
    few cells onto the lower surface, and a window of +-3 nodes missed it (10.2 deg delivered for
    10 asked on the cranked reference wing)."""
    t = turning(ring)
    t[[0, 2 * n_side - 2]] = 0.0
    if ignore is not None:
        t[:2 * n_side - 1][ignore] = 0.0
    return float(t.max())


def solve_nose(sec: Section, h_band: float, h_max: float, h_te: float, rules: Rules) -> dict:
    """law 1: the nose spacing whose nose cells turn the surface by the target, by bisection.

    The ring is rebuilt and measured at every step, so the delivered turning is the asked
    turning on any airfoil (S8: a nose-radius estimate gave 20 deg when 6 was asked).
    The spacing is never coarser than the band spacing.
    """
    target, tol = rules.nose_turning_deg, rules.nose_turning_tol_deg
    kinks = geometry_kinks(sec)

    def measure(h_le: float) -> tuple[float, int]:
        spec = RingSpec(h_le, h_band, h_max, h_te)
        n = int(np.ceil(cells_per_side(sec, spec, rules))) + 1
        r = build_ring(sec, spec, rules, n)
        return nose_turning(r["ring"], n, kink_mask(r["u_upper"], r["u_lower"], kinks, n)), n

    hi = min(h_band, h_max)
    got, n = measure(hi)
    if got <= target:
        return {"h_le": hi, "turning_deg": got, "n_own": n, "capped_at_band": True, "iterations": 1,
                "solved": True, "kinks": kinks}
    lo = 1.0e-7 * sec.chord
    best = None                                    # largest spacing found that stays at or below the target
    it = 1
    for it in range(2, 120):
        mid = np.sqrt(lo * hi)                     # bisect in log: spacings span decades
        got, n = measure(mid)
        if got <= target:
            best = (mid, got, n)
        if abs(got - target) <= tol:
            break
        if got > target:
            hi = mid
        else:
            lo = mid
        # The point count is an integer, so the turning can jump by a little when the count
        # steps; then the target is bracketed but never hit. Keep the side below the target.
        if hi / lo - 1.0 < 1e-9:
            if best is None:        # not even the smallest spacing meets the target: refused by the check
                return {"h_le": mid, "turning_deg": got, "n_own": n, "capped_at_band": False, "iterations": it,
                        "solved": False, "kinks": kinks}
            mid, got, n = best
            break
    else:
        raise RuntimeError(f"nose solve did not converge at v={sec.v:.4f} (turning {got:.3f} deg)")
    # The turning is not quite monotone in the spacing on some noses (the loft's nose radius
    # changes within the first cells, Stage 1 finding). The answer must also hold when the
    # envelope tightens it by up to 1.15: walk down until every spacing in [0.77 h, h] passes.
    for _ in range(40):
        window = [measure(mid * 0.95 ** k) for k in range(1, 6)]
        if all(g <= target for g, _ in window):
            break
        mid *= 0.95
        got, n = measure(mid)
        it += 1
    return {"h_le": mid, "turning_deg": got, "n_own": n, "capped_at_band": False, "iterations": it,
            "solved": True, "kinks": kinks}


def envelope(h_le_c: Array, limit: float) -> Array:
    """law 2: nose spacing / chord may change by at most `limit` between stations; only tightening."""
    out = np.asarray(h_le_c, dtype=float).copy()
    for i in range(1, len(out)):
        out[i] = min(out[i], out[i - 1] * limit)
    for i in range(len(out) - 2, -1, -1):
        out[i] = min(out[i], out[i + 1] * limit)
    return np.minimum(out, h_le_c)
