"""Station sections: airfoils, twist, dihedral, vertical position."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

from .params import AIRFOIL_DIR, TypeSpec, resolve
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
    rows = []
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue
    pts = np.asarray(rows, dtype=float)
    if len(pts) < 10 or pts[0, 0] > 1.5:
        raise ValueError(f"{path}: expected a Selig-format airfoil (TE -> upper -> LE -> lower -> TE)")
    return pts


def load_airfoil(name: str, n_side: int = N_SIDE, folder: Path = AIRFOIL_DIR) -> Airfoil:
    """Read a .dat file, put it on unit chord, and resample both surfaces on cosine x."""
    pts = read_dat(folder / f"{name}.dat")
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
    keep = np.concatenate([[True], np.diff(xs) > 1e-12])
    xs, ys = xs[keep], side[keep, 1]
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
    stations = [
        Station(STATION_NAMES[i], float(pf.y[i]), float(pf.x_le[i]), float(z[i]),
                float(pf.chord[i]), float(twist[i]), load_airfoil(spec.airfoils[i]))
        for i in range(4)
    ]
    return pf, stations


def panel_dihedral_deg(y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Dihedral of the straight lines between consecutive points (+ tip up)."""
    return np.degrees(np.arctan2(np.diff(z), np.diff(y)))
