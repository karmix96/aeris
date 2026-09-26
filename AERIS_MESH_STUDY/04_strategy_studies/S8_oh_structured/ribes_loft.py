"""The RIBES wind-tunnel wing, in the shape the S8 mesher expects.

Same contract as `m6_loft`: the mesher asks a geometry for an upper and a lower
surface it can evaluate at (u, v), u along the chord and v root to tip. Nothing
else is needed and nothing about the section is approximated.

WHY THIS ONE MATTERS. Every external check in this project so far tests the
SOLVER against someone else's grid, or tests OUR grid in the wrong regime
(ONERA M6 is transonic). RIBES is the first case that puts our own mesh, at our
own operating point, in front of real measurements:

    RIBES T40   40 m/s, Re 1.43e6, boundary layer tripped at 1.4 % chord
    AERIS S8    Ma 0.0837, Re 1.53e6, fully turbulent by assumption

7 % apart in Reynolds number, and tripped -- which is the only fair comparison
for a solver that assumes the boundary layer is turbulent everywhere. The
experiment publishes 3,814 pressure coefficients over three spanwise sections.

GEOMETRY PROVENANCE. Not the analytic definition. The design report says the
section is "Goettingen 398 scaled to t/c = 11 % AND REDESIGNING THE LEADING
EDGE", and a redesigned nose is exactly the part a scaled library section would
get wrong -- and exactly where this mesher solves for its 10-degree turning
target. So the section is taken from the project's own laser scan of the
manufactured model, MeasuredCADmodel.stp, imported through gmsh OCC, sliced at
17 spanwise stations, each slab rotated onto its own chord line, and the 17
normalised sections reduced by median to beat down scan noise.

That section is checked three ways before use:

    thickness            11.40 % of chord, against the design's 11 %
    planform fit         chord 599.8 - 0.1124 y mm, so root 599.8 and tip 419.9
                         against the design's 600 and 420, taper 0.7000
    quarter-chord sweep  -0.325 deg against the design's "in the order of -0.3"
    against the taps     median 0.064 % of chord over 30 pressure taps whose
                         positions the experiment reports independently

The trailing edge measures 0.38 to 0.66 % of chord across the span, mean 0.517 %.
That is worth recording: it is what a real riveted aluminium wing gives, and it
sits on top of the 0.500 % this project uses by default.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SECTION_FILE = HERE / "external/ribes/ribes_section.dat"

#: Fitted to the 17 scanned sections; residuals 0.72 mm on the leading edge and
#: 0.78 mm on chord, against a 600 mm root chord.
SPAN_M = 1.600
ROOT_CHORD_M = 0.5998
TIP_CHORD_M = 0.4199
LE_SWEEP_DEG = 1.286
DIHEDRAL_DEG = -0.138


def section_coordinates() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """x/c, upper z/c and lower z/c of the measured RIBES section, nose to tail."""
    d = np.loadtxt(SECTION_FILE)
    order = np.argsort(d[:, 0])
    return d[order, 0], d[order, 1], d[order, 2]


class _Surface:
    """One side of the wing, evaluated the way `pygeo.surfs[i]` is."""

    def __init__(self, upper: bool) -> None:
        self.upper = bool(upper)
        self.x_c, self.z_up, self.z_lo = section_coordinates()

    def __call__(self, u, v) -> np.ndarray:
        u = np.atleast_1d(np.asarray(u, dtype=float)).ravel()
        v = np.atleast_1d(np.asarray(v, dtype=float)).ravel()
        if v.size == 1 and u.size > 1:
            v = np.full_like(u, v[0])
        # u = 0 is the TRAILING edge and u = 1 the leading edge: the convention
        # `_frame_and_opened_curves` reads, taking `te` from index 0 and `le`
        # from index -1. Nose-first inverts every ring and the mesher reports it
        # as a wall of folded cells that no smoothing rung clears.
        xc = 0.5 * (1.0 + np.cos(np.pi * np.clip(u, 0.0, 1.0)))
        zc = np.interp(xc, self.x_c, self.z_up if self.upper else self.z_lo)
        chord = ROOT_CHORD_M + (TIP_CHORD_M - ROOT_CHORD_M) * v
        y = v * SPAN_M
        x_le = y * np.tan(np.radians(LE_SWEEP_DEG))
        z_le = y * np.tan(np.radians(DIHEDRAL_DEG))
        # AERIS convention: chord along +x, span along +y, thickness along +z
        return np.column_stack([x_le + xc * chord, y, z_le + zc * chord])


class RibesLoft:
    """What `build_oml_ring` calls `pygeo`: a pair of surfaces."""

    def __init__(self) -> None:
        self.surfs = [_Surface(True), _Surface(False)]

    @property
    def description(self) -> dict:
        return {"wing": "RIBES wind-tunnel model", "units": "metres",
                "root_chord_m": ROOT_CHORD_M, "tip_chord_m": TIP_CHORD_M,
                "span_m": SPAN_M, "taper_ratio": round(TIP_CHORD_M / ROOT_CHORD_M, 4),
                "le_sweep_deg": LE_SWEEP_DEG, "dihedral_deg": DIHEDRAL_DEG,
                "twist_deg": 0.0,
                "section": "measured, median of 17 scanned sections",
                "section_source": "MeasuredCADmodel.stp via gmsh OCC",
                "reference_area_m2": 0.816,
                "experiment": "RIBES test report, Clean Sky JTI grant 632556"}
