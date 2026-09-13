"""The ONERA M6 wing, in the shape the S8 mesher expects.

The mesher asks a geometry for exactly two things: an upper surface and a lower
surface it can evaluate at (u, v), u along the chord and v root to tip. That is
all `build_oml_ring` uses. So a wing that is not an AERIS design can be meshed
by our own mesher simply by presenting those two callables -- no pyGeo loft, no
CAD, and nothing about the section is approximated.

Why this exists: every external check so far validates the SOLVER. The ONERA M6
comparison runs on NASA's grid; the NACA 0012 verification runs on pyHyp grids.
Nothing has ever put OUR MESH in front of real measurements. This does: the same
O-H topology, the same marching, the same tip cap, on the one wing with public
wind-tunnel data.

Geometry, in semispan units, exactly as `onera_m6.py` records it from the WIND
archive: root chord 0.6737, tip chord 0.3789, leading-edge sweep 30 deg, no
twist, no dihedral, the ONERA D section, which is symmetric with a slightly
blunt trailing edge (half-thickness 0.0007 c) -- convenient, because the mesher
wants a base to put its trailing-edge points on.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SECTION_FILE = HERE.parents[1] / "05_s6_cfd_qualification/external/onera_m6/airfoil.txt"
#: from onera_m6.GEOMETRY, semispan-normalised
ROOT_CHORD, TIP_CHORD, SEMISPAN, LE_SWEEP_DEG = 0.6737, 0.3789, 1.0, 30.0


def section_coordinates() -> tuple[np.ndarray, np.ndarray]:
    """x/c and half-thickness y/c of the ONERA D section, nose to tail."""
    data = np.loadtxt(SECTION_FILE)
    x, y = data[:, 0], data[:, 1]
    order = np.argsort(x)
    return x[order], y[order]


class _Surface:
    """One side of the wing, evaluated the way `pygeo.surfs[i]` is.

    u is cosine-mapped onto x/c so that the nose, where the mesher measures
    turning, is densely represented in the parametrisation rather than crammed
    into the first per cent of a linear one.
    """

    def __init__(self, sign: float) -> None:
        self.sign = float(sign)
        self.x_c, self.y_c = section_coordinates()

    def __call__(self, u, v) -> np.ndarray:
        u = np.atleast_1d(np.asarray(u, dtype=float)).ravel()
        v = np.atleast_1d(np.asarray(v, dtype=float)).ravel()
        if v.size == 1 and u.size > 1:
            v = np.full_like(u, v[0])
        # u = 0 is the TRAILING edge and u = 1 the leading edge: that is the
        # convention `_frame_and_opened_curves` reads (`te` from index 0, `le`
        # from index -1). Nose-first parametrisation inverts every ring, and the
        # mesher reports it honestly -- 281,628 folded cells, unchanged at every
        # rung of the smoothing ladder, which is what a handedness error looks
        # like as opposed to a marching one.
        xc = 0.5 * (1.0 + np.cos(np.pi * np.clip(u, 0.0, 1.0)))
        yc = np.interp(xc, self.x_c, self.y_c)
        chord = ROOT_CHORD + (TIP_CHORD - ROOT_CHORD) * v
        x_le = v * SEMISPAN * np.tan(np.radians(LE_SWEEP_DEG))
        # AERIS convention: chord along +x, span along +y, thickness along +z
        return np.column_stack([x_le + xc * chord, v * SEMISPAN, self.sign * yc * chord])


class M6Loft:
    """What `build_oml_ring` calls `pygeo`: a pair of surfaces."""

    def __init__(self) -> None:
        self.surfs = [_Surface(+1.0), _Surface(-1.0)]

    @property
    def description(self) -> dict:
        return {"wing": "ONERA M6", "units": "semispan",
                "root_chord": ROOT_CHORD, "tip_chord": TIP_CHORD,
                "semispan": SEMISPAN, "le_sweep_deg": LE_SWEEP_DEG,
                "section": str(SECTION_FILE.name), "twist_deg": 0.0, "dihedral_deg": 0.0}
