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
