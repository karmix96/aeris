"""
Airfoil domain data models.

AirfoilRecord is the canonical in-memory representation of one airfoil loaded
from the library.  All coordinate arrays are normalised (unit chord, LE at 0,
TE at 1) and stored as float64 numpy arrays.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class AirfoilGeometryStats:
    """Geometry statistics derived from the raw x/y coordinate arrays.

    These are used as ML features when CST coefficients are not yet available.
    All values are non-dimensional (fraction of chord).
    """
    t_c: float           # max thickness / chord
    t_c_x: float         # chordwise location of max thickness
    camber_max: float    # max camber / chord
    camber_max_x: float  # chordwise location of max camber
    le_radius: float     # approximate leading-edge radius (Moran formula)
    te_angle_deg: float  # trailing-edge angle in degrees


@dataclass(frozen=True)
class AirfoilRecord:
    """Single airfoil entry in the AERIS airfoil library.

    airfoil_id is a SHA-256 digest of the rounded coordinate array so that
    two airfoils with identical geometry (regardless of source filename) share
    the same ID.  This is the group key used for ML train/val/test splitting —
    the same rule as geometry_id in the 3D pipeline.
    """
    airfoil_id: str          # SHA-256 of normalised coords (hex, 16 chars)
    name: str                # human name (from filename, e.g. "NACA4412")
    family: str              # coarse family tag ("naca4", "custom", etc.)
    source_file: str         # original xlsx filename
    n_coords: int            # number of coordinate pairs
    x: np.ndarray            # shape (n,)  chordwise, LE=0 TE=1
    y: np.ndarray            # shape (n,)  ordinate
    stats: AirfoilGeometryStats

    def to_inventory_row(self) -> dict[str, Any]:
        """Flat dict for one row of airfoil_inventory.csv."""
        return {
            "airfoil_id":    self.airfoil_id,
            "name":          self.name,
            "family":        self.family,
            "source_file":   self.source_file,
            "n_coords":      self.n_coords,
            "t_c":           round(self.stats.t_c, 6),
            "t_c_x":         round(self.stats.t_c_x, 6),
            "camber_max":    round(self.stats.camber_max, 6),
            "camber_max_x":  round(self.stats.camber_max_x, 6),
            "le_radius":     round(self.stats.le_radius, 6),
            "te_angle_deg":  round(self.stats.te_angle_deg, 4),
        }


# ── Coordinate utilities ───────────────────────────────────────────────────────

def compute_airfoil_id(x: np.ndarray, y: np.ndarray) -> str:
    """Stable SHA-256 ID from the coordinate array (rounded to 6 dp)."""
    coords = np.stack([np.round(x, 6), np.round(y, 6)], axis=1)
    digest = hashlib.sha256(coords.tobytes()).hexdigest()
    return digest[:16]   # 16 hex chars — unique in practice for ~10k airfoils


def compute_geometry_stats(x: np.ndarray, y: np.ndarray) -> AirfoilGeometryStats:
    """Compute non-dimensional geometry statistics from raw (x, y) arrays.

    Assumes the airfoil is already in unit-chord, LE-at-0 form.
    The upper and lower surfaces are identified by sorting at mid-chord.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # Camber line: mean of upper and lower at matching x stations
    # Interpolate both surfaces onto a dense common x grid
    n = 200
    xi = np.linspace(0.0, 1.0, n)

    # Split upper (y > 0 at x~0.5) and lower (y < 0 at x~0.5)
    mid_mask = (x > 0.3) & (x < 0.7)
    if mid_mask.sum() >= 2:
        mid_y = y[mid_mask]
        upper_mask = y >= np.median(mid_y)
    else:
        upper_mask = y >= 0.0

    xu, yu = x[upper_mask], y[upper_mask]
    xl, yl = x[~upper_mask], y[~upper_mask]

    # Sort each surface by x (increasing)
    if len(xu) >= 2 and len(xl) >= 2:
        su = np.argsort(xu); xu, yu = xu[su], yu[su]
        sl = np.argsort(xl); xl, yl = xl[sl], yl[sl]
        yi_u = np.interp(xi, xu, yu)
        yi_l = np.interp(xi, xl, yl)
        thickness = np.abs(yi_u - yi_l)
        camber = 0.5 * (yi_u + yi_l)
    else:
        # Degenerate: treat whole array as upper surface
        xs = np.argsort(x); xs_arr, ys_arr = x[xs], y[xs]
        thickness = np.abs(np.interp(xi, xs_arr, ys_arr))
        camber = np.zeros_like(xi)

    t_c_idx = int(np.argmax(thickness))
    t_c = float(thickness[t_c_idx])
    t_c_x = float(xi[t_c_idx])

    cam_idx = int(np.argmax(np.abs(camber)))
    camber_max = float(camber[cam_idx])
    camber_max_x = float(xi[cam_idx])

    # LE radius: approximate from first few points (Moran 1984 formula)
    # r_LE ≈ 0.5 * (dy/dx at LE)^2 for thin airfoils, but we use a simpler
    # geometric estimate from the first upper-surface interval
    try:
        if len(xu) >= 3 and xu[0] < 0.02:
            dydx = (yu[1] - yu[0]) / max(xu[1] - xu[0], 1e-9)
            le_radius = float(0.5 * (yu[1] ** 2) / max(xu[1], 1e-9))
        else:
            le_radius = float(t_c * 0.05)   # fallback: ~5% of thickness
    except Exception:
        le_radius = float(t_c * 0.05)

    # TE angle: angle between upper and lower surfaces at the trailing edge
    try:
        if len(xu) >= 2 and len(xl) >= 2:
            slope_u = float((yu[-1] - yu[-2]) / max(xu[-1] - xu[-2], 1e-9))
            slope_l = float((yl[-1] - yl[-2]) / max(xl[-1] - xl[-2], 1e-9))
            te_angle_deg = float(np.degrees(np.arctan(abs(slope_u - slope_l))))
        else:
            te_angle_deg = 0.0
    except Exception:
        te_angle_deg = 0.0

    return AirfoilGeometryStats(
        t_c=t_c,
        t_c_x=t_c_x,
        camber_max=abs(camber_max),
        camber_max_x=camber_max_x,
        le_radius=max(le_radius, 0.0),
        te_angle_deg=te_angle_deg,
    )
