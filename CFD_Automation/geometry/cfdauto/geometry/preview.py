"""The wing surface without pyGeo, for pictures and quick checks.

With k_span = 2 the loft is a ruled surface: between two sections, a point at
the same chord fraction moves on a straight line. So the surface here, built by
straight lines between the section points, is the loft (up to the cubic fit of
each section). Use the real loft (loft.py) for anything that is measured.
"""

from __future__ import annotations

import numpy as np

from .loft import section_points
from .sections import Station


def ruled_surface(stations: list[Station], per_panel: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Upper and lower surface grids, shape (n_span, n_chord, 3), root to tip."""
    secs = [section_points(s) for s in stations]
    ups, los = [], []
    for k in range(len(stations) - 1):
        (ua, la), (ub, lb) = secs[k], secs[k + 1]
        last = k == len(stations) - 2
        for t in np.linspace(0.0, 1.0, per_panel + 1)[: None if last else -1]:
            ups.append((1 - t) * ua + t * ub)
            los.append((1 - t) * la + t * lb)
    return np.array(ups), np.array(los)


def outline(stations: list[Station]) -> tuple[np.ndarray, np.ndarray]:
    """Leading edge and trailing-edge midpoint polylines (x, y, z), root to tip."""
    le, te = [], []
    for s in stations:
        u, l = section_points(s)
        le.append(u[0])
        te.append(0.5 * (u[-1] + l[-1]))
    return np.array(le), np.array(te)
