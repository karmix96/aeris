import numpy as np
import pytest

from cfdauto.mesh.spacing import cells_needed, equidistribute, fill_to_count, flat_ends, limit_growth, spacing_stats


def test_limit_growth_delivers_the_ratio():
    s = np.linspace(0.0, 1.0, 20001)
    h = np.full_like(s, 0.05)
    h = flat_ends(s, h, 1e-4, None)
    g = limit_growth(s, h, 1.2)
    assert np.all(g <= h + 1e-15)
    n = int(np.ceil(cells_needed(s, g))) + 1
    x = equidistribute(s, g, n)
    st = spacing_stats(x)
    assert st["max_ratio"] <= 1.2 * 1.01
    assert st["min"] <= 1e-4 * 1.01


def test_equidistribute_never_coarser_than_target():
    s = np.linspace(0.0, 2.0, 5001)
    h = 0.01 + 0.05 * s
    n = int(np.ceil(cells_needed(s, h))) + 1
    x = equidistribute(s, h, n)
    mid = 0.5 * (x[1:] + x[:-1])
    assert np.all(np.diff(x) <= np.interp(mid, s, h) * 1.02)


def test_fill_to_count_shrinks_largest_cells_only():
    s = np.linspace(0.0, 1.0, 5001)
    h = np.where(s < 0.2, 0.002, 0.02)
    n = int(np.ceil(cells_needed(s, h))) + 1
    h2 = fill_to_count(s, h, n + 30)
    assert np.allclose(h2[s < 0.2], 0.002)
    assert np.all(h2[s >= 0.2] < 0.02)
    assert abs(cells_needed(s, h2) - (n + 29)) < 1e-6
    with pytest.raises(ValueError):
        fill_to_count(s, h, n - 5)
