"""Where airfoils come from: local files, the AERIS database, or a NACA formula.

A name is looked up in this order:

1. ``geometry/airfoils/<name>.dat``  (sections made for this project, e.g. the
   ONERA M6 and RIBES sections);
2. the AERIS airfoil database, ``data/airfoil_database/<name>.dat`` in the aeris
   repository (about 2,180 sections; override with the environment variable
   ``CFDAUTO_AIRFOIL_DB``);
3. a NACA 4-digit (``naca2412``) or 5-digit (``naca25118``) name not found as a
   file is made from the NACA formula.

A name may also be a path to a ``.dat`` file. Selig files (trailing edge, upper
surface, nose, lower surface, trailing edge) and Lednicer files (two point
counts, then the upper and the lower surface from the nose) are both read.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import numpy as np

GEOMETRY_ROOT = Path(__file__).resolve().parents[2]
LOCAL_DIR = GEOMETRY_ROOT / "airfoils"
AERIS_DB = Path(os.environ.get("CFDAUTO_AIRFOIL_DB", GEOMETRY_ROOT.parents[1] / "data" / "airfoil_database"))

_NACA4 = re.compile(r"^naca(\d)(\d)(\d{2})$")
_NACA5 = re.compile(r"^naca([1-9])([1-5])([01])(\d{2})$")


def search_dirs() -> list[Path]:
    return [d for d in (LOCAL_DIR, AERIS_DB) if d.is_dir()]


def find_file(name: str) -> Path | None:
    """The .dat file for a name, or None if no file has it."""
    p = Path(name)
    if p.suffix == ".dat" and p.is_file():
        return p
    for d in search_dirs():
        f = d / f"{name}.dat"
        if f.is_file():
            return f
    return None


def exists(name: str) -> bool:
    return find_file(name) is not None or naca_code(name) is not None


def available(pattern: str = "") -> list[str]:
    """Names of every airfoil file on the search path (optionally filtered)."""
    names = set()
    for d in search_dirs():
        names.update(f.stem for f in d.glob("*.dat"))
    return sorted(n for n in names if pattern.lower() in n.lower())


def naca_code(name: str) -> str | None:
    """'2412' or '25118' when name is a NACA 4/5-digit name that no file provides."""
    n = name.lower()
    if find_file(name) is not None:
        return None
    if _NACA4.match(n) or _NACA5.match(n):
        return n[4:]
    return None


def source(name: str) -> str:
    """Where a name is read from, for the record."""
    f = find_file(name)
    if f is not None:
        return str(f)
    if naca_code(name):
        return f"NACA formula ({name})"
    raise ValueError(f"airfoil {name!r} not found in {[str(d) for d in search_dirs()]} "
                     f"and not a NACA 4- or 5-digit name")


def raw_points(name: str) -> np.ndarray:
    """Points in Selig order (TE -> upper -> nose -> lower -> TE), as given."""
    f = find_file(name)
    if f is not None:
        return read_dat(f)
    code = naca_code(name)
    if code is not None:
        return naca_points(code)
    source(name)  # raises with the search path
    raise AssertionError


def digest(name: str) -> str:
    """sha256 of the points a name resolves to (works for files and formulas)."""
    return hashlib.sha256(np.round(raw_points(name), 12).tobytes()).hexdigest()


# --- reading files -------------------------------------------------------------

def _numeric_rows(text: str) -> list[list[float]]:
    rows = []
    for line in text.splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue
    return rows


def read_dat(path: Path) -> np.ndarray:
    """Read a Selig or Lednicer file and return Selig-ordered points."""
    rows = _numeric_rows(Path(path).read_text(errors="replace"))
    if len(rows) < 10:
        raise ValueError(f"{path}: fewer than 10 coordinate rows")
    first = rows[0]
    if first[0] > 1.5 and first[1] > 1.5:           # Lednicer: counts, then two blocks
        n_up, n_lo = int(round(first[0])), int(round(first[1]))
        pts = np.asarray(rows[1:], dtype=float)
        if len(pts) < n_up + n_lo:
            raise ValueError(f"{path}: Lednicer header promises {n_up}+{n_lo} points, file has {len(pts)}")
        upper, lower = pts[:n_up], pts[n_up:n_up + n_lo]   # both nose -> TE
        return np.vstack([upper[::-1], lower[1:]])
    pts = np.asarray(rows, dtype=float)
    if np.any(np.abs(pts[:, 0]) > 1.5):
        raise ValueError(f"{path}: x outside [0, 1.5]; not a unit-chord section")
    return pts


# --- NACA formulas -------------------------------------------------------------
# Thickness: the standard 4/5-digit distribution with the classic open trailing
# edge (last coefficient -0.1015), applied normal to the camber line.
# 5-digit camber constants for design CL 0.3 (k1, k2/k1 scale with CL / 0.3),
# from Abbott & von Doenhoff, "Theory of Wing Sections" (1959); reflexed values
# as tabulated in the Wikipedia article "NACA airfoil".
_NACA5_STD = {1: (0.0580, 361.400), 2: (0.1260, 51.640), 3: (0.2025, 15.957),
              4: (0.2900, 6.643), 5: (0.3910, 3.230)}
_NACA5_REFLEX = {2: (0.1300, 51.990, 0.000764), 3: (0.2170, 15.793, 0.00677),
                 4: (0.3180, 6.520, 0.0303), 5: (0.4410, 3.191, 0.1355)}


def naca_thickness(x: np.ndarray, t: float) -> np.ndarray:
    return 5.0 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1015 * x ** 4)


def naca_camber(code: str, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Camber line yc and slope dyc/dx for a 4- or 5-digit code."""
    if len(code) == 4:
        m, p = int(code[0]) / 100.0, int(code[1]) / 10.0
        if m == 0 or p == 0:
            return np.zeros_like(x), np.zeros_like(x)
        front = x < p
        yc = np.where(front, m / p ** 2 * (2 * p * x - x ** 2), m / (1 - p) ** 2 * (1 - 2 * p + 2 * p * x - x ** 2))
        dy = np.where(front, 2 * m / p ** 2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
        return yc, dy
    cl = 0.15 * int(code[0])
    pos, reflex = int(code[1]), int(code[2]) == 1
    scale = cl / 0.3
    if not reflex:
        r, k1 = _NACA5_STD[pos]
        k1 *= scale
        front = x < r
        yc = np.where(front, k1 / 6 * (x ** 3 - 3 * r * x ** 2 + r ** 2 * (3 - r) * x), k1 * r ** 3 / 6 * (1 - x))
        dy = np.where(front, k1 / 6 * (3 * x ** 2 - 6 * r * x + r ** 2 * (3 - r)), -k1 * r ** 3 / 6)
        return yc, dy
    if pos not in _NACA5_REFLEX:
        raise ValueError(f"NACA {code}: no reflexed camber line for position digit {pos}")
    r, k1, k21 = _NACA5_REFLEX[pos]
    k1 *= scale
    front = x < r
    yc = np.where(front,
                  k1 / 6 * ((x - r) ** 3 - k21 * (1 - r) ** 3 * x - r ** 3 * x + r ** 3),
                  k1 / 6 * (k21 * (x - r) ** 3 - k21 * (1 - r) ** 3 * x - r ** 3 * x + r ** 3))
    dy = np.where(front,
                  k1 / 6 * (3 * (x - r) ** 2 - k21 * (1 - r) ** 3 - r ** 3),
                  k1 / 6 * (3 * k21 * (x - r) ** 2 - k21 * (1 - r) ** 3 - r ** 3))
    return yc, dy


def naca_points(code: str, n_side: int = 200) -> np.ndarray:
    """Selig-ordered points of a NACA 4- or 5-digit section."""
    x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n_side + 1)))
    t = int(code[-2:]) / 100.0
    yt = naca_thickness(x, t)
    yc, dy = naca_camber(code, x)
    th = np.arctan(dy)
    xu, yu = x - yt * np.sin(th), yc + yt * np.cos(th)
    xl, yl = x + yt * np.sin(th), yc - yt * np.cos(th)
    upper = np.column_stack([xu, yu])[::-1]
    lower = np.column_stack([xl, yl])[1:]
    return np.vstack([upper, lower])
