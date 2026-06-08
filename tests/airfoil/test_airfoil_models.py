"""Unit tests for airfoil domain models and geometry statistics."""
from __future__ import annotations

import numpy as np
import pytest

from aeris.airfoil.models import (
    compute_airfoil_id,
    compute_geometry_stats,
    AirfoilGeometryStats,
)


def _naca4_coords(m_pct: float, p_pct: float, t_pct: float, n: int = 100):
    """Generate NACA 4-digit airfoil coordinates."""
    m, p, t = m_pct / 100, p_pct / 100, t_pct / 100
    x = np.linspace(0, 1, n)
    yt = 5 * t * (0.2969*np.sqrt(x) - 0.1260*x - 0.3516*x**2 + 0.2843*x**3 - 0.1015*x**4)
    if m == 0.0 or p == 0.0:
        yc  = np.zeros_like(x)
        dyc = np.zeros_like(x)
    else:
        yc = np.where(x < p,
                      m/p**2 * (2*p*x - x**2),
                      m/(1-p)**2 * ((1-2*p) + 2*p*x - x**2))
        dyc = np.where(x < p,
                       2*m/p**2 * (p - x),
                       2*m/(1-p)**2 * (p - x))
    theta = np.arctan(dyc)
    xu = x - yt * np.sin(theta)
    yu = yc + yt * np.cos(theta)
    xl = x + yt * np.sin(theta)
    yl = yc - yt * np.cos(theta)
    x_all = np.concatenate([xu[::-1], xl[1:]])
    y_all = np.concatenate([yu[::-1], yl[1:]])
    return x_all, y_all


def test_airfoil_id_is_16_chars():
    x, y = _naca4_coords(0, 0, 12)
    aid = compute_airfoil_id(x, y)
    assert len(aid) == 16
    assert aid.isalnum()


def test_airfoil_id_deterministic():
    x, y = _naca4_coords(4, 4, 12)
    id1 = compute_airfoil_id(x, y)
    id2 = compute_airfoil_id(x, y)
    assert id1 == id2


def test_airfoil_id_differs_for_different_airfoils():
    x1, y1 = _naca4_coords(0, 0, 12)
    x2, y2 = _naca4_coords(4, 4, 12)
    assert compute_airfoil_id(x1, y1) != compute_airfoil_id(x2, y2)


def test_geometry_stats_naca0012():
    x, y = _naca4_coords(0, 0, 12)
    stats = compute_geometry_stats(x, y)
    # NACA 0012: 12% thickness, 0% camber
    assert isinstance(stats, AirfoilGeometryStats)
    assert 0.10 <= stats.t_c <= 0.14, f"t/c = {stats.t_c}"
    assert stats.camber_max < 0.01, f"camber = {stats.camber_max}"
    assert stats.le_radius >= 0.0
    assert stats.te_angle_deg >= 0.0


def test_geometry_stats_naca4412():
    x, y = _naca4_coords(4, 4, 12)
    stats = compute_geometry_stats(x, y)
    # NACA 4412: 12% thickness, 4% camber
    assert 0.10 <= stats.t_c <= 0.14
    assert stats.camber_max > 0.01   # cambered
