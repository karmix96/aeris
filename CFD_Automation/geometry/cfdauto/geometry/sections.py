"""Station sections: airfoils, twist, dihedral, vertical position, trailing edge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

from . import airfoils as _airfoils
from .params import TERule, TypeSpec, resolve, station_airfoils
from .planform import Planform, build_planform

N_SIDE = 100  # points per surface; a section has 2 * N_SIDE + 1 points
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
    """Selig-ordered points -> unit-chord Airfoil on cosine x."""
    te_mid = 0.5 * (pts[0] + pts[-1])
    i_le = int(np.argmax(np.linalg.norm(pts - te_mid, axis=1)))
    le = pts[i_le]
    d = te_mid - le
    scale = np.linalg.norm(d)
    ang = np.arctan2(d[1], d[0])
    rot = np.array([[np.cos(ang), np.sin(ang)], [-np.sin(ang), np.cos(ang)]])
    p = (pts - le) @ rot.T / scale

    upper = p[: i_le + 1][::-1]
    lower = p[i_le:]
    if np.mean(upper[:, 1]) < np.mean(lower[:, 1]):
        upper, lower = lower, upper

    x = cosine_x(n_side)
    return Airfoil(name, x, _resample(upper, x), _resample(lower, x))


def _resample(side: np.ndarray, x: np.ndarray) -> np.ndarray:
    """y on the given x points, from one surface running LE -> TE.

    Interpolates in sqrt(x), where the round nose becomes smooth.
    """
    xs = np.clip(side[:, 0], 0.0, None)
    ys = side[:, 1]
    # Some files repeat or step back a point near an edge: keep x increasing.
    keep = np.concatenate([[True], xs[1:] > np.maximum.accumulate(xs)[:-1] + 1e-12])
    xs, ys = xs[keep], ys[keep]
    # A single point off a smooth line is a typo in the file (e.g. sc20412, lower
    # surface at x/c 0.73): drop it rather than build a bump into the wing.
    bad = _airfoils.suspect_points(np.column_stack([xs, ys]))
    if len(bad):
        xs, ys = np.delete(xs, bad), np.delete(ys, bad)
    xs[0], ys[0] = 0.0, 0.0
    xs[-1] = 1.0
    return PchipInterpolator(np.sqrt(xs), ys)(np.sqrt(x))


# --- vertical position -------------------------------------------------------
# Copied from AERIS (sections.py, _segment_z_integral): exact for dihedral
# varying linearly in y, independent of how the span is cut.

def segment_z_integral(y0: float, y1: float, d0: float, d1: float) -> float:
    """Integral of tan(dihedral) over one segment; d0, d1 in radians."""
    if y1 <= y0:
        return 0.0
    m = (d1 - d0) / (y1 - y0)
    if abs(m) < 1e-14:
        return float(np.tan(d0) * (y1 - y0))
    return float((np.log(abs(np.cos(d0))) - np.log(abs(np.cos(d1)))) / m)


def station_z(y: np.ndarray, dihedral_deg: np.ndarray) -> np.ndarray:
    d = np.radians(dihedral_deg)
    z = np.zeros(len(y))
    for i in range(1, len(y)):
        z[i] = z[i - 1] + segment_z_integral(y[i - 1], y[i], d[i - 1], d[i])
    return z


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
    dihedral = np.array([vec[f"dihedral{i}_deg"] for i in range(4)])
    if np.any(np.abs(dihedral) >= 89.0):
        raise ValueError("dihedral must be within +/-89 deg")
    z = station_z(pf.y, dihedral)
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
            s = (c_sw - a.chord) / (b.chord - a.chord)
            out.append(Station(
                f"te_switch_p{i}",
                a.y + s * (b.y - a.y),
                a.x_le + s * (b.x_le - a.x_le),
                a.z_le + s * (b.z_le - a.z_le),
                c_sw,
                a.twist_deg + s * (b.twist_deg - a.twist_deg),
                a.airfoil.blend(b.airfoil, s),
            ))
        out.append(b)
    opened = [
        Station(st.name, st.y, st.x_le, st.z_le, st.chord, st.twist_deg,
                open_te(st.airfoil, te.target_m(st.chord, st.airfoil.te_thickness) / st.chord, te.open_from_xc))
        for st in out
    ]
    return pf, opened


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
