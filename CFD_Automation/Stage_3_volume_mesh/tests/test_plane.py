import numpy as np
import pytest

from cfdauto.volume import plane as pl
from cfdauto.volume.laws import rules


def test_series_against_quadrature():
    from scipy.integrate import quad
    for x in (0.05, 0.4, 1.2):
        assert pl._si(np.array([x]))[0] == pytest.approx(quad(lambda t: np.sin(t) / t, 0, x)[0], rel=1e-12)
        assert pl._cin(np.array([x]))[0] == pytest.approx(quad(lambda t: (1 - np.cos(t)) / t, 0, x)[0], rel=1e-10)


def test_wake_line_leaves_the_corners():
    ring = np.array([[1.0, 0.002], [0.5, 0.06], [0.0, 0.0], [0.5, -0.04], [1.0, -0.001], [1.0, 0.0005]])
    w = pl.wake_of(ring, 3, 1.0, rules("VC"))
    c, up, lo = w.lines(np.array([0.0, 1e-6, 10.0]))
    assert np.allclose(up[0], ring[0], atol=1e-15)
    assert np.allclose(lo[0], ring[4], atol=1e-15)
    t = (c[1] - c[0]) / np.linalg.norm(c[1] - c[0])
    assert np.degrees(np.arccos(t @ np.array([np.cos(w.phi0), np.sin(w.phi0)]))) < 1e-3   # along the base normal
    assert abs(np.arctan2(*(c[2] - w.centre(np.array([9.99]))[0][0])[::-1])) < 1e-6         # +x far behind


def test_band_height_adds_the_downward_wake(surface_vc):
    """Decision 106: a wake that leaves the base pointing down raises the band's top above the wake line."""
    import copy
    import numpy as np
    from cfdauto.volume import plane as pl
    from cfdauto.volume.laws import rules
    from cfdauto.volume.volume import stations_of
    rl = rules("VC")
    st = stations_of(surface_vc, rl)[0]
    b = rl.band
    straight = float(b["margin_c"]) + float(b["length_local_c"]) * st.chord * np.tan(np.radians(b["alpha_hi_deg"]))
    level = copy.copy(st)
    level.wake = pl.WakeLine(st.wake.M, 0.0, st.wake.turn, st.wake.t_te, st.wake.gap_growth)
    down = copy.copy(st)
    down.wake = pl.WakeLine(st.wake.M, -abs(np.radians(6.0)), st.wake.turn, st.wake.t_te, st.wake.gap_growth)
    assert pl.band_height(level, rl) == pytest.approx(straight, rel=1e-12)
    assert pl.band_height(down, rl) > straight + 0.5 * st.wake.turn * np.radians(6.0) * 0.5



def test_band_envelope_holds_the_straight_fan_around_a_bent_cut_line(surface_vc):
    """Decision 108: the band is a fan of straight rays from the base mid-point; a cut line that leaves the base
    pointing down (or up) is farther from one band edge, and the cells stay <= the band cell up to that edge."""
    import copy
    from cfdauto.volume.volume import stations_of
    rl = rules("VC")
    st = stations_of(surface_vc, rl)[0]
    b = rl.band
    L = float(b["length_local_c"]) * st.chord
    t_hi, t_lo = np.tan(np.radians(b["alpha_hi_deg"])), np.tan(np.radians(-b["alpha_lo_deg"]))
    k = (t_hi + t_lo) / b["fan_cells"]
    for phi in (0.0, -np.radians(8.0), np.radians(8.0)):
        w = copy.copy(st)
        w.wake = pl.WakeLine(st.wake.M, phi, st.wake.turn, st.wake.t_te, st.wake.gap_growth)
        x, cap = pl.band_envelope(w, rl)
        assert np.all(np.diff(cap) >= -1e-12) and cap[0] == pytest.approx(b["spacing_c"])
        s = np.linspace(0.02 * L, L, 60)
        dz = w.wake.centre(s)[0][:, 1] - w.wake.M[1]
        for edge in (b["margin_c"] + s * t_hi - dz, b["margin_c"] + s * t_lo + dz):   # upper lines, lower lines
            inside = np.interp(np.clip(0.98 * edge, 0.0, x[-1]), x, cap)             # just inside the band at s
            assert np.all(inside <= (b["spacing_c"] + k * s) * 1.005)
    # a level cut line: the envelope is the linear law of the steeper edge
    w = copy.copy(st)
    w.wake = pl.WakeLine(st.wake.M, 0.0, st.wake.turn, st.wake.t_te, st.wake.gap_growth)
    x, cap = pl.band_envelope(w, rl)
    assert np.allclose(cap, b["spacing_c"] + k * np.maximum(x - b["margin_c"], 0.0) / max(t_hi, t_lo), rtol=1e-3)
