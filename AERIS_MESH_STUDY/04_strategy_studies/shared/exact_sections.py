"""EXPERIMENT — sections at arbitrary spanwise stations, exactly.

**This is a copy-based experiment.** Nothing under `src/aeris` is modified. If it
holds up it becomes a generator change and an ADR, because it alters
`configs/geometry/bwb.yaml`'s meaning and therefore the sha256 that identifies all
three locked geometry sets.

--------------------------------------------------------------------------------
WHY
--------------------------------------------------------------------------------

Every strategy so far invents spanwise mesh columns by blending linearly between
the generator's realised sections, and the fidelity gate (0.01% of local chord)
cannot be verified for those columns. Measured on `lhs100_seed42_000`: the wing
deviates from a straight line between stations by a median of 0.447% of chord and
up to 7.25% at the inboard/outboard spline junction — 45x to 700x the gate.

Refining the station count does not fix it. Measured 17 -> 35 -> 71 -> 143
stations: 7.25% -> 3.08% -> 1.42% -> 0.68%, a ratio of about 2 per doubling. That
is FIRST-order convergence, which is what linear interpolation gives across a
slope discontinuity, not the second-order O(h^2) a smooth surface would give.
Reaching 0.01% that way needs of order 12,000 stations.

**The requirement is zero deviation on every geometry the mesher will ever see, so
interpolation has to go, not shrink.** The planform is closed-form — a CubicSpline
inboard blended toward a straight line, purely linear outboard — so a section at
ANY spanwise station is exactly computable. If the mesher asks the generator for
sections at exactly the stations it wants, every mesh column is a real section and
the deviation is identically zero by construction, on every geometry.

--------------------------------------------------------------------------------
THE ONE SUBTLETY: z
--------------------------------------------------------------------------------

`sections._cumulative_z` integrates `tan(dihedral)` by the TRAPEZOID rule along
whatever station array it is handed. Dihedral is piecewise linear in y, so
`tan(dihedral)` is not, and the trapezoid result therefore depends on the
discretisation: change the stations and `z(y)` moves. That alone would stop the
"exact section at arbitrary y" claim being true.

Over a segment where dihedral runs linearly from d0 to d1 across [y0, y1]:

    m = (d1 - d0) / (y1 - y0)                       [rad per metre]
    m == 0 :  integral = tan(d0) * (y1 - y0)
    m != 0 :  integral = (ln|cos d0| - ln|cos d1|) / m

which is exact and station-independent. That is what :func:`exact_z_at` uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def exact_z_at(y_query, boundary_y, boundary_dihedral_deg):
    """LE z at arbitrary y, by exact integration of a piecewise-linear dihedral.

    Replaces the trapezoid rule in `sections._cumulative_z`, whose answer depends
    on the station array it happens to be given.
    """
    y_query = np.atleast_1d(np.asarray(y_query, dtype=float))
    by = np.asarray(boundary_y, dtype=float)
    bd = np.radians(np.asarray(boundary_dihedral_deg, dtype=float))

    def _segment_integral(y0: float, y1: float, d0: float, d1: float) -> float:
        if y1 <= y0:
            return 0.0
        m = (d1 - d0) / (y1 - y0)
        if abs(m) < 1e-14:
            return float(np.tan(d0) * (y1 - y0))
        return float((np.log(abs(np.cos(d0))) - np.log(abs(np.cos(d1)))) / m)

    # Cumulative integral at each boundary, then the partial segment to y.
    cum = np.zeros(len(by))
    for k in range(1, len(by)):
        cum[k] = cum[k - 1] + _segment_integral(by[k - 1], by[k], bd[k - 1], bd[k])

    out = np.empty_like(y_query)
    for i, y in enumerate(y_query):
        k = int(np.clip(np.searchsorted(by, y, side="right") - 1, 0, len(by) - 2))
        d_at_y = float(np.interp(y, by, bd))
        out[i] = cum[k] + _segment_integral(by[k], float(y), bd[k], d_at_y)
    return out


def planform_curves(planform, config):
    """Closed-form LE and TE x(y), reconstructed from the planform control points.

    Mirrors `planform.generate_spline_linear` exactly: a clamped CubicSpline over
    the control points inboard, blended toward the straight-line baseline by
    ``curvature_strength``, and purely linear outboard of the split.
    """
    y_ctrl = np.asarray(planform.y_le, dtype=float)
    x_le_ctrl = np.asarray(planform.x_le, dtype=float)
    x_te_ctrl = np.asarray(planform.x_te, dtype=float)
    split_idx = int(planform.split_idx)
    strength = float(config.controls.curvature_strength)

    def _curve(x_ctrl):
        spline = CubicSpline(y_ctrl, x_ctrl, bc_type="clamped")
        y_split = float(y_ctrl[split_idx])
        y_tip = float(y_ctrl[-1])

        def f(y):
            y = np.atleast_1d(np.asarray(y, dtype=float))
            out = np.empty_like(y)
            inb = y <= y_split
            if inb.any():
                base = np.interp(
                    y[inb], [float(y_ctrl[0]), y_split], [float(x_ctrl[0]), float(x_ctrl[split_idx])]
                )
                out[inb] = base + strength * (spline(y[inb]) - base)
            if (~inb).any():
                out[~inb] = np.interp(
                    y[~inb], [y_split, y_tip], [float(x_ctrl[split_idx]), float(x_ctrl[-1])]
                )
            return out

        return f

    return _curve(x_le_ctrl), _curve(x_te_ctrl)
