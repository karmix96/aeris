"""Station sections: airfoils, twist, dihedral, vertical position, trailing edge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

from . import airfoils as _airfoils
from .params import TERule, TypeSpec, resolve, station_airfoils
from .planform import Planform, build_planform

N_SIDE = 200  # points per surface; a section has 2 * N_SIDE + 1 points (201 per side: decision 64)
STATION_NAMES = ("b0", "b1", "b2", "b3")


@dataclass(frozen=True)
class Airfoil:
    """Unit-chord section: leading edge at (0, 0), trailing-edge midpoint at (1, 0).

    Upper and lower surfaces share the same x points, so the camber line is
    (yu + yl) / 2 at each x.
    """

    name: str
    x: np.ndarray
    yu: np.ndarray
    yl: np.ndarray

    @property
    def te_thickness(self) -> float:
        return float(self.yu[-1] - self.yl[-1])

    @property
    def camber(self) -> np.ndarray:
        return 0.5 * (self.yu + self.yl)

    @property
    def thickness(self) -> np.ndarray:
        return self.yu - self.yl

    def blend(self, other: "Airfoil", s: float) -> "Airfoil":
        """Linear blend (1 - s) * self + s * other, as a ruled loft would give."""
        return Airfoil(
            f"{self.name}|{other.name}@{s:.6f}",
            self.x,
            (1.0 - s) * self.yu + s * other.yu,
            (1.0 - s) * self.yl + s * other.yl,
        )

    def selig(self) -> np.ndarray:
        """Points from the upper trailing edge, round the nose, to the lower trailing edge."""
        upper = np.column_stack([self.x[::-1], self.yu[::-1]])
        lower = np.column_stack([self.x[1:], self.yl[1:]])
        return np.vstack([upper, lower])


def cosine_x(n_side: int = N_SIDE) -> np.ndarray:
    return 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n_side + 1)))


def read_dat(path: Path) -> np.ndarray:
    """Selig-ordered points from a Selig or Lednicer file."""
    return _airfoils.read_dat(path)


def load_airfoil(name: str, n_side: int = N_SIDE, folder: Path | None = None) -> Airfoil:
    """Load a section by name, put it on unit chord, and resample both surfaces on cosine x.

    The name is looked up locally, then in the AERIS airfoil database, then as a
    NACA 4/5-digit formula (see airfoils.py). With folder, only that folder is read.
    """
    pts = read_dat(Path(folder) / f"{name}.dat") if folder is not None else _airfoils.raw_points(name)
    return airfoil_from_points(name, pts, n_side)


def airfoil_from_points(name: str, pts: np.ndarray, n_side: int = N_SIDE) -> Airfoil:
    """Selig-ordered points -> unit-chord Airfoil on cosine x (rule D25).

    One cubic spline runs through the raw points (chord-length parameter). The leading edge is
    the point of that spline farthest from the trailing-edge midpoint: its apex, where the tangent
    is square to the chord, as the sqrt(x) loft needs. Both sides are sampled from that one spline.
    Decision 64: the farthest raw point, used before, is not the apex (up to 0.21 % c of arc away on
    the ten study sections), and the tangent there is turned (up to 19 deg); forcing it square bent
    the built nose (up to 5.5 x the true turning per cell). See Stage_1_geometry/decisions/nose_curvature.md.
    """
    te_mid = 0.5 * (pts[0] + pts[-1])
    p = _clean(pts, te_mid)
    t = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    spl = CubicSpline(t, p, bc_type="natural")   # the ends are the trailing edge: no overshoot at a closed one
    t_le = _apex(spl, t, int(np.argmax(np.linalg.norm(p - te_mid, axis=1))), te_mid)
    le = spl(t_le)
    d = te_mid - le
    scale = np.linalg.norm(d)
    ang = np.arctan2(d[1], d[0])
    rot = np.array([[np.cos(ang), np.sin(ang)], [-np.sin(ang), np.cos(ang)]])
    frame = lambda q: (spl(q) - le) @ rot.T / scale  # noqa: E731  spline points in the unit-chord frame

    x = cosine_x(n_side)
    upper = _resample(frame, t_le, t[0], t[1], x)       # Selig order: the upper side comes first
    lower = _resample(frame, t_le, t[-1], t[-2], x)
    if np.mean(upper) < np.mean(lower):
        upper, lower = lower, upper
    return Airfoil(name, x, upper, lower)


def _clean(pts: np.ndarray, te_mid: np.ndarray) -> np.ndarray:
    """The raw points without the ones a side must not use, judged in the frame of the farthest
    raw point. Some files repeat or step back a point near an edge: keep x increasing. A single
    point off a smooth line is a typo in the file (e.g. sc20412, lower surface at x/c 0.73): drop
    it rather than build a bump into the wing."""
    i_le = int(np.argmax(np.linalg.norm(pts - te_mid, axis=1)))
    d = te_mid - pts[i_le]
    ang = np.arctan2(d[1], d[0])
    rot = np.array([[np.cos(ang), np.sin(ang)], [-np.sin(ang), np.cos(ang)]])
    p = (pts - pts[i_le]) @ rot.T / np.linalg.norm(d)
    drop = []
    for idx in (np.arange(i_le, -1, -1), np.arange(i_le, len(p))):      # each side, LE -> TE
        xs = np.clip(p[idx, 0], 0.0, None)
        keep = np.concatenate([[True], xs[1:] > np.maximum.accumulate(xs)[:-1] + 1e-12])
        bad = _airfoils.suspect_points(np.column_stack([xs[keep], p[idx[keep], 1]]))
        drop += list(idx[~keep]) + list(idx[keep][bad])
    return np.delete(pts, drop, axis=0)


def _apex(spl: CubicSpline, t: np.ndarray, i: int, te_mid: np.ndarray) -> float:
    """Parameter of the spline point farthest from te_mid, between raw point i's neighbours."""
    q = np.linspace(t[max(i - 1, 0)], t[min(i + 1, len(t) - 1)], 201)
    k = int(np.argmax(np.linalg.norm(spl(q) - te_mid, axis=1)))
    g = lambda s: float(np.dot(spl(s) - te_mid, spl(s, 1)))  # noqa: E731  zero at the apex
    a, b = q[max(k - 1, 0)], q[min(k + 1, len(q) - 1)]
    return brentq(g, a, b, xtol=1e-15) if g(a) * g(b) < 0 else float(q[k])


def _resample(frame, t_le: float, t_end: float, t_last: float, x: np.ndarray) -> np.ndarray:
    """y on the given x points of one side, sampled from the spline between the apex (t_le) and
    the side's trailing-edge end (t_end). As before, the side's last raw interval (from t_last) is
    stretched in x so that its end lands on x = 1."""
    stretch = 1.0 - frame(np.array([t_end]))[0, 0]
    xt = lambda q: frame(q)[:, 0] + stretch * np.clip((q - t_last) / (t_end - t_last), 0.0, 1.0)  # noqa: E731
    dense = t_le + (t_end - t_le) * np.linspace(0.0, 1.0, 2001) ** 2      # dense at the nose
    j = np.clip(np.searchsorted(np.maximum.accumulate(xt(dense)), x), 1, len(dense) - 1)
    a, b = dense[j - 1], dense[j]                                         # x(a) < x_i <= x(b)
    for _ in range(60):                                                   # bisection to round-off
        m = 0.5 * (a + b)
        right = xt(m) >= x
        a, b = np.where(right, a, m), np.where(right, m, b)
    y = frame(0.5 * (a + b))[:, 1]
    y[0] = 0.0
    return y


# --- vertical position -------------------------------------------------------
# One dihedral per straight panel. The height of station i is the sum of
# tan(panel dihedral) x panel span over the panels inboard of it. Sections stay
# vertical (parallel to the symmetry plane), so the root section lies exactly in
# y = 0 whatever the dihedral, and the two mirrored halves meet there without
# crossing. (AERIS rolled the root section with the first panel, which made the
# halves cross; that is why it had to pin the root dihedral at zero.)

def panel_z(y: np.ndarray, panel_dihedral_deg: np.ndarray) -> np.ndarray:
    """Station heights from the panel dihedrals (len(y) - 1 values)."""
    dz = np.tan(np.radians(panel_dihedral_deg)) * np.diff(y)
    return np.concatenate([[0.0], np.cumsum(dz)])


@dataclass(frozen=True)
class Station:
    """One section of the loft. Sections are vertical (parallel to the symmetry
    plane), so the root section lies in y = 0 whatever the dihedral."""

    name: str
    y: float
    x_le: float
    z_le: float
    chord: float
    twist_deg: float
    airfoil: Airfoil


def build_stations(spec: TypeSpec, vec: dict[str, float]) -> tuple[Planform, list[Station]]:
    """The four station sections b0..b3 (closed or as read; no trailing-edge rule)."""
    vec = resolve(spec, vec)
    pf = build_planform(spec, vec)
    twist = np.array([vec[f"twist{i}_deg"] for i in range(4)])
    dihedral = np.array([vec[f"dihedral_p{i}_deg"] for i in (1, 2, 3)])
    if np.any(np.abs(dihedral) >= 89.0):
        raise ValueError("dihedral must be within +/-89 deg")
    z = panel_z(pf.y, dihedral)
    names = station_airfoils(spec, vec)
    stations = [
        Station(STATION_NAMES[i], float(pf.y[i]), float(pf.x_le[i]), float(z[i]),
                float(pf.chord[i]), float(twist[i]), load_airfoil(names[i]))
        for i in range(4)
    ]
    return pf, stations


# --- trailing edge ------------------------------------------------------------

def open_te(airfoil: Airfoil, te_over_c: float, x_start: float) -> Airfoil:
    """Set the trailing-edge thickness to te_over_c (of chord), the pyGeo way.

    Same method as pyGeo's readAirfoilFile(bluntTe=True, bluntThickness,
    bluntTaperRange) (MDO Lab, MACH-Aero): the change grows linearly from zero
    at x_start to the full amount at the edge, half on the upper side, half on
    the lower. So the camber line does not move and the section ahead of
    x_start is untouched. pyGeo's default range is the last 10 % of chord
    (x_start = 0.9).
    """
    x = airfoil.x
    r = np.where(x > x_start, (x - x_start) / (1.0 - x_start), 0.0)
    half = 0.5 * (te_over_c - airfoil.te_thickness) * r
    return Airfoil(airfoil.name, x, airfoil.yu + half, airfoil.yl - half)


def build_wing_sections(spec: TypeSpec, vec: dict[str, float], te: TERule) -> tuple[Planform, list[Station]]:
    """Station sections with the trailing-edge rule built in.

    The loft interpolates thickness linearly between sections. Where the rule
    switches from the floor to the chord fraction inside a panel, a section is
    added at the switch point, so the rule holds there too. The added section
    lies on the straight panel (position, chord, twist and shape interpolated).
    """
    pf, stations = build_stations(spec, vec)
    if te.mode == "as_is":
        for st in stations:
            if st.airfoil.te_thickness <= 1e-6:
                raise ValueError(f"{st.name}: section {st.airfoil.name!r} has a closed trailing edge; "
                                 f"trailing_edge mode 'as_is' needs a blunt one")
        return pf, stations
    c_sw = te.switch_chord_m()
    out = [stations[0]]
    for i, (a, b) in enumerate(zip(stations[:-1], stations[1:]), start=1):
        lo, hi = sorted((a.chord, b.chord))
        if lo < c_sw < hi:
            out.append(switch_station(a, b, c_sw, f"te_switch_p{i}"))
        out.append(b)
    opened = [
        Station(st.name, st.y, st.x_le, st.z_le, st.chord, st.twist_deg,
                open_te(st.airfoil, te.target_m(st.chord, st.airfoil.te_thickness) / st.chord, te.open_from_xc))
        for st in out
    ]
    return pf, opened


def chord_vector(st: Station) -> np.ndarray:
    """Leading edge to trailing edge in the x-z plane (sections are vertical, twisted about the LE)."""
    t = np.radians(st.twist_deg)
    return st.chord * np.array([np.cos(t), -np.sin(t)])


def switch_station(a: Station, b: Station, c_sw: float, name: str) -> Station:
    """The section where the true chord equals c_sw, ON the straight (ruled) panel a-b.

    Inside a ruled panel the chord vector is linear in the panel parameter s, so the true chord
    |(1 - s) ca + s cb| is shorter than the linear chord where the twist changes. The section is put
    where that true chord equals c_sw, with the twist of the chord vector there. Then its leading
    and trailing edges lie on the panel's straight edges, and the aspect ratio stays exact."""
    from scipy.optimize import brentq

    va, vb = chord_vector(a), chord_vector(b)
    f = lambda t: float(np.linalg.norm((1 - t) * va + t * vb)) - c_sw  # noqa: E731
    s = brentq(f, 0.0, 1.0, xtol=1e-15, rtol=4 * np.finfo(float).eps)
    v = (1 - s) * va + s * vb
    return Station(name, a.y + s * (b.y - a.y), a.x_le + s * (b.x_le - a.x_le), a.z_le + s * (b.z_le - a.z_le),
                   float(np.linalg.norm(v)), float(np.degrees(np.arctan2(-v[1], v[0]))), a.airfoil.blend(b.airfoil, s))


def insert_sections(stations: list[Station], per_panel: int, te: TERule) -> list[Station]:
    """Add per_panel evenly spaced sections inside each panel, on the straight
    panel (used to test the loft, not in normal builds)."""
    out = [stations[0]]
    for a, b in zip(stations[:-1], stations[1:]):
        for k in range(1, per_panel + 1):
            s = k / (per_panel + 1)
            chord = a.chord + s * (b.chord - a.chord)
            shape = a.airfoil.blend(b.airfoil, s)
            out.append(Station(
                f"{a.name}+{k}", a.y + s * (b.y - a.y), a.x_le + s * (b.x_le - a.x_le),
                a.z_le + s * (b.z_le - a.z_le), chord, a.twist_deg + s * (b.twist_deg - a.twist_deg),
                open_te(shape, te.target_m(chord, shape.te_thickness) / chord, te.open_from_xc)))
        out.append(b)
    return out


def panel_dihedral_deg(y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Dihedral of the straight lines between consecutive points (+ tip up)."""
    return np.degrees(np.arctan2(np.diff(z), np.diff(y)))
