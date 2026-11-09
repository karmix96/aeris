import numpy as np
import pytest

from cfdauto.volume import march as mr


def line(n=1):
    one = lambda v: np.full(n, float(v))
    return dict(g_bl=one(1.15), delta=one(0.02), g_fine=one(1.25), fine=one(2.0), g_far=one(1.25))


def test_fill_exact_count_first_cell_and_growth():
    s0, L = np.array([1e-5, 3e-5]), np.array([80.0, 85.0])
    a = line(2)
    f = mr.min_cells(s0, L, **a)
    n = int(np.ceil(f.max())) + 3
    d, lam = mr.fill(s0, L, n, **a)
    assert d.shape == (n + 1, 2)
    assert np.allclose(d[1], s0, rtol=1e-12)
    assert np.allclose(d[-1], L, rtol=0, atol=1e-12)
    h = np.diff(d, axis=0)
    assert np.all(h > 0)
    r = h[1:] / h[:-1]
    assert r.max() <= 1.25 * 1.001
    assert np.all(lam < 1.0)


def test_count_is_continuous_in_lam():
    """The fill must land on the count: the growth ramps at every zone boundary (no jump)."""
    s0, L = np.array([1e-4]), np.array([50.0])
    a = line(1)
    n = int(np.ceil(mr.min_cells(s0, L, **a)[0])) + 5
    d, _ = mr.fill(s0, L, n, **a)
    h = np.diff(d[:, 0])
    assert h[-1] / h[-2] == pytest.approx(h[-2] / h[-3], rel=0.05)    # the last cell is not cut short


def test_bl_growth_gives_the_cells():
    s0, delta = np.array([1e-4, 1e-5]), np.array([0.01, 0.01])
    g = mr.bl_growth(s0, delta, 30.0, 1.25)
    n = np.log1p((g - 1) * delta / s0) / np.log(g)
    assert np.all(n >= 30.0 - 1e-6)
    assert np.all(g <= 1.25)


def test_shrink_keeps_the_wall_and_only_lowers_growth():
    from cfdauto.volume.plane import shrink
    d = np.concatenate([[0.0], np.cumsum(1e-5 * 1.2 ** np.arange(80))])
    out = shrink(d, np.array([d[-1], 0.95 * d[-1]]))
    assert out[1, 1] == pytest.approx(d[1], rel=1e-12)
    g0 = np.diff(d)[1:] / np.diff(d)[:-1]
    g1 = np.diff(out[:, 1])[1:] / np.diff(out[:, 1])[:-1]
    assert np.all(g1 <= g0 * (1 + 1e-12))


def test_implicit_smoothing_of_a_straight_line_is_identity():
    X = np.stack([np.linspace(0, 1, 50) ** 2, np.zeros(50)], -1)
    n = mr.line_normals(X)
    m = mr._smooth_implicit(n, X, 0.3)
    assert np.allclose(m, n, atol=1e-12)
