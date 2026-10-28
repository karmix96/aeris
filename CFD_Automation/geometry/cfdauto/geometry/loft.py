"""The loft: pyGeo surfaces through the station sections.

Built the way pyGeo's liftingSurface builds them (each section a cubic
B-spline, the sections are the rows of control points, order kSpan across the
span), with one difference: every section uses the same parameter,
s = sqrt(x/c). So all sections share one knot vector, the upper and lower
surfaces split exactly at the nose, and u in upper(u, v) / lower(u, v) is the
chord fraction x/c on every station. liftingSurface instead merges each
section's own knots and splits at a knot that is only near the nose (see
geometry/decisions/loft.md).

The mesher only asks the loft for points; it never interpolates between
stored sections.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .sections import Station


def section_points(st: Station) -> tuple[np.ndarray, np.ndarray]:
    """Upper and lower surface points of one station in 3-D, leading edge first.

    The section is vertical (in the plane y = st.y), twisted nose-up by
    twist_deg about a spanwise axis through its leading edge.
    """
    a = st.airfoil
    t = np.radians(st.twist_deg)
    c, s = np.cos(t), np.sin(t)

    def place(yc: np.ndarray) -> np.ndarray:
        xi, eta = a.x * st.chord, yc * st.chord
        return np.column_stack([
            st.x_le + xi * c + eta * s,
            np.full_like(xi, st.y),
            st.z_le - xi * s + eta * c,
        ])

    return place(a.yu), place(a.yl)


@dataclass
class Loft:
    geo: object              # pyGeo object holding [upper, lower, trailing-edge base]
    stations: list[Station]
    k_span: int
    station_v: np.ndarray    # span parameter v of each station

    @property
    def upper_surface(self):
        return self.geo.surfs[0]

    @property
    def lower_surface(self):
        return self.geo.surfs[1]

    def upper(self, u, v) -> np.ndarray:
        """Point on the upper surface at chord fraction u and span parameter v."""
        return _eval(self.geo.surfs[0], u, v)

    def lower(self, u, v) -> np.ndarray:
        return _eval(self.geo.surfs[1], u, v)

    def leading_edge(self, v) -> np.ndarray:
        return self.upper(0.0, v)

    def te_mid(self, v) -> np.ndarray:
        return 0.5 * (self.upper(1.0, v) + self.lower(1.0, v))

    def span_table(self, n: int = 401) -> np.ndarray:
        """Columns: v, y of the leading edge [m]."""
        v = np.linspace(0.0, 1.0, n)
        y = np.array([self.leading_edge(vi)[1] for vi in v])
        return np.column_stack([v, y])

    def v_at_y(self, y) -> np.ndarray:
        tab = self.span_table(2001)
        return np.interp(y, tab[:, 1], tab[:, 0])

    @property
    def backend(self) -> str:
        return getattr(self.geo, "backend", "pygeo")

    def write_iges(self, path: str | Path) -> None:
        if self.backend != "pygeo":
            raise RuntimeError("IGES export needs the pyGeo loft")
        with contextlib.redirect_stdout(io.StringIO()):
            self.geo.writeIGES(str(path))

    def surface_hash(self) -> str:
        """sha256 of every control point and knot, rounded to 1e-12 m."""
        h = hashlib.sha256(self.backend.encode())
        for surf in self.geo.surfs:
            for arr in (surf.coef, surf.tu, surf.tv):
                h.update(np.round(np.asarray(arr, dtype=float), 12).tobytes())
        return h.hexdigest()


def _eval(surf, u, v) -> np.ndarray:
    u = np.sqrt(np.clip(np.asarray(u, dtype=float), 0.0, 1.0))
    v = np.clip(np.asarray(v, dtype=float), 0.0, 1.0)
    u, v = np.broadcast_arrays(u, v)
    if u.ndim == 0:
        return np.asarray(surf(float(u), float(v)), dtype=float)
    return np.asarray(surf(np.ascontiguousarray(u), np.ascontiguousarray(v)), dtype=float)


def edge_error_pct(loft: Loft, exact: list[Station], n: int = 401) -> dict[str, float]:
    """Loft leading edge and trailing-edge midpoint against the exact straight
    lines through the given stations. Errors in % of the local chord."""
    y = np.array([st.y for st in exact])
    le_ex = np.array([[st.x_le, st.z_le] for st in exact])
    te_ex = np.array([0.5 * sum(p[-1] for p in section_points(st))[[0, 2]] for st in exact])
    chord = np.array([st.chord for st in exact])
    err_le, err_te = [], []
    for v in np.linspace(0.0, 1.0, n):
        le, te = loft.leading_edge(v), loft.te_mid(v)
        c = np.interp(le[1], y, chord)
        want_le = [np.interp(le[1], y, le_ex[:, k]) for k in (0, 1)]
        want_te = [np.interp(te[1], y, te_ex[:, k]) for k in (0, 1)]
        err_le.append(np.hypot(le[0] - want_le[0], le[2] - want_le[1]) / c * 100)
        err_te.append(np.hypot(te[0] - want_te[0], te[2] - want_te[1]) / c * 100)
    err_le, err_te = np.array(err_le), np.array(err_te)
    return {
        "le_max_pct": float(err_le.max()), "le_rms_pct": float(np.sqrt(np.mean(err_le ** 2))),
        "te_max_pct": float(err_te.max()), "te_rms_pct": float(np.sqrt(np.mean(err_te ** 2))),
    }


def pygeo_available() -> bool:
    try:
        import pygeo  # noqa: F401
        import pyspline  # noqa: F401
    except ImportError:
        return False
    return True


def build_loft(stations: list[Station], k_span: int = 2, backend: str | None = None) -> Loft:
    """Loft the stations. k_span = 2 gives straight (ruled) panels between sections.

    backend "pygeo" (the production loft) or "numpy" (the same construction with
    scipy splines: each section a cubic interpolating spline in s = sqrt(x/c),
    straight lines between sections). Default: pyGeo when installed, else numpy.
    The numpy loft is a second, independent implementation: the two must agree
    (tests/geometry/test_loft_backends.py), and it lets every check run where
    pyGeo is not installed. It cannot write IGES.
    """
    if backend is None:
        backend = "pygeo" if pygeo_available() else "numpy"
    if backend == "numpy":
        return _build_numpy(stations, k_span)
    if backend != "pygeo":
        raise ValueError("backend must be 'pygeo' or 'numpy'")
    from pygeo import pyGeo
    from pyspline import Curve, Surface

    n = len(stations)
    if not 2 <= k_span <= n:
        raise ValueError(f"k_span must be between 2 and the number of sections ({n})")
    x = stations[0].airfoil.x
    if any(not np.array_equal(st.airfoil.x, x) for st in stations):
        raise ValueError("all sections must share the same chordwise points")
    s = np.sqrt(x)

    tops, bots = [], []
    for st in stations:
        up, lo = section_points(st)
        tops.append(Curve(X=up, k=4, s=s))
        bots.append(Curve(X=lo, k=4, s=s))
    tu = tops[0].t
    if any(not np.array_equal(c.t, tu) for c in tops + bots):
        raise RuntimeError("section knot vectors differ; cannot build one surface")

    coef_top = np.stack([c.coef for c in tops], axis=1)   # (n_u, n_sections, 3)
    coef_bot = np.stack([c.coef for c in bots], axis=1)
    le = np.array([[st.x_le, st.y, st.z_le] for st in stations])
    span = Curve(X=le, k=k_span)

    top = Surface(coef=coef_top, ku=4, kv=k_span, tu=tu, tv=span.t)
    bot = Surface(coef=coef_bot, ku=4, kv=k_span, tu=tu, tv=span.t)
    base = np.stack([coef_top[-1], coef_bot[-1]], axis=1)  # (n_sections, 2, 3)
    te = Surface(coef=base, ku=k_span, kv=2, tu=span.t, tv=[0.0, 0.0, 1.0, 1.0])

    with contextlib.redirect_stdout(io.StringIO()):
        geo = pyGeo("create")
    geo.surfs = [top, bot, te]
    geo.nSurf = 3
    return Loft(geo=geo, stations=list(stations), k_span=k_span, station_v=np.asarray(span.s, dtype=float))


# --- numpy backend -------------------------------------------------------------------

class _RuledSurface:
    """Sections (cubic splines in s) joined by straight lines in v; called like a pySpline surface."""

    def __init__(self, curves, station_v: np.ndarray):
        self.curves = curves
        self.v = np.asarray(station_v, dtype=float)
        self.coef = np.concatenate([c.c for c in curves])
        self.tu = curves[0].t
        self.tv = self.v

    def __call__(self, s, v):
        s, v = np.broadcast_arrays(np.asarray(s, dtype=float), np.asarray(v, dtype=float))
        shape = s.shape
        s, v = s.ravel(), np.clip(v.ravel(), 0.0, 1.0)
        j = np.clip(np.searchsorted(self.v, v, side="right") - 1, 0, len(self.v) - 2)
        t = (v - self.v[j]) / (self.v[j + 1] - self.v[j])
        out = np.empty((len(s), 3))
        for k in np.unique(j):
            m = j == k
            a, b = self.curves[k](s[m]), self.curves[k + 1](s[m])
            out[m] = (1.0 - t[m, None]) * a + t[m, None] * b
        return out.reshape(*shape, 3) if shape else out[0]


class _RuledBase:
    """Trailing-edge base: straight lines between the upper and lower edge, called as base(v, w)."""

    def __init__(self, upper: _RuledSurface, lower: _RuledSurface):
        self.upper, self.lower = upper, lower
        self.coef = np.concatenate([upper.coef[-1:], lower.coef[-1:]])
        self.tu, self.tv = upper.v, np.array([0.0, 0.0, 1.0, 1.0])

    def __call__(self, v, w):
        a, b = self.upper(1.0, v), self.lower(1.0, v)
        w = np.asarray(w, dtype=float)
        return (1.0 - w)[..., None] * a + w[..., None] * b if w.ndim else (1.0 - w) * a + w * b


def _build_numpy(stations: list[Station], k_span: int) -> Loft:
    from types import SimpleNamespace

    from scipy.interpolate import make_interp_spline

    if k_span != 2:
        raise ValueError("the numpy loft supports k_span = 2 (straight panels) only")
    x = stations[0].airfoil.x
    if any(not np.array_equal(st.airfoil.x, x) for st in stations):
        raise ValueError("all sections must share the same chordwise points")
    s = np.sqrt(x)
    tops, bots = [], []
    for st in stations:
        up, lo = section_points(st)
        tops.append(make_interp_spline(s, up, k=3))
        bots.append(make_interp_spline(s, lo, k=3))
    le = np.array([[st.x_le, st.y, st.z_le] for st in stations])
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(le, axis=0), axis=1))])
    station_v = d / d[-1]                        # chord-length parameter, as pySpline uses
    top, bot = _RuledSurface(tops, station_v), _RuledSurface(bots, station_v)
    geo = SimpleNamespace(surfs=[top, bot, _RuledBase(top, bot)], nSurf=3, backend="numpy")
    return Loft(geo=geo, stations=list(stations), k_span=k_span, station_v=station_v)
