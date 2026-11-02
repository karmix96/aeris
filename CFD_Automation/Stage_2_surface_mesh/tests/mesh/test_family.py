"""The family rule: every spacing of level M is the C spacing divided by r (law 23)."""

import numpy as np
import pytest

from cfdauto.mesh.laws import rules
from cfdauto.mesh.surface import build_surface


def spacings(m):
    y = np.array([r["y_m"] for r in m.stations])
    root, tip = m.stations[0], m.stations[-1]
    return {
        "nose_root": root["h_le_c"], "nose_tip": tip["h_le_c"],
        "te": root["h_te_c_delivered"], "band_root": root["band_max_c"], "band_tip": tip["band_max_c"],
        "tip_gap": float(np.diff(y)[-1]), "root_gap": float(np.diff(y)[0]),
        "base": float(np.linalg.norm(m.wing[-1, 0] - m.wing[0, 0])),   # one base cell at the root
        # a cell in the stretched part behind the upper band (85-100 % c) and a station gap in the
        # tip squeeze: both must refine by r too (a true scaled copy, not only the end spacings)
        "upper_aft_cell": _cell_at(m, 0, 0.92), "squeeze_gap": _gap_at(m, 0.5 * (y[-1] + m.info["loft_station_y_m"][-2])),
    }


def _cell_at(m, j, x_c):
    n = m.info["n_side"]
    pts, u = m.wing[:n, j][::-1], m.u[:n, j][::-1]
    d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return float(np.interp(x_c, 0.5 * (u[1:] + u[:-1]), d))


def _gap_at(m, y_at):
    y = np.array([r["y_m"] for r in m.stations])
    return float(np.interp(y_at, 0.5 * (y[1:] + y[:-1]), np.diff(y)))


@pytest.mark.slow
def test_level_m_is_level_c_divided_by_r(bwb, mesh_c):
    r = rules("C").ratio
    m = build_surface(bwb.loft, 3.0e5, "M")
    assert m.passed, [c.name for c in m.failed()]
    c_sp, m_sp = spacings(mesh_c), spacings(m)
    for k in c_sp:
        if k == "base":
            continue                       # integer cell count: 8 -> 10 cells (ratio 1.25), reported, not exact
        assert abs(c_sp[k] / m_sp[k] / r - 1.0) < 0.03, (k, c_sp[k] / m_sp[k])
    assert 1.2 <= c_sp["base"] / m_sp["base"] <= 1.5
    for k in ("n_ring", "n_span"):           # counts refine by r too (within the integer steps)
        assert abs(m.info[k] / mesh_c.info[k] / r - 1.0) < 0.05, (k, m.info[k], mesh_c.info[k])
