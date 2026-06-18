"""Unit tests for AirfoilPolarStore and the CDCL fitting algorithm."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aeris.airfoil.polar_store import (
    AirfoilPolarStore,
    CdclParams,
    _bracket,
    _fit_cdcl_from_arrays,
    _interpolate_cdcl,
    _nearest,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_parabolic_polar(
    cl_min: float = 0.2,
    cd_min: float = 0.008,
    stall_neg: float = -0.6,
    stall_pos: float = 1.2,
    n_points: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic parabolic polar with clear stall boundaries."""
    cls = np.linspace(stall_neg, stall_pos, n_points)
    # Parabolic bucket
    cds = cd_min + 0.015 * (cls - cl_min) ** 2
    # Add stall rise at extremes
    cds[cls < -0.3] += 0.02 * (cls[cls < -0.3] + 0.3) ** 2 * 20
    cds[cls > 1.0] += 0.03 * (cls[cls > 1.0] - 1.0) ** 2 * 20
    return cls, cds


def _write_polar_csv(root: Path, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)
    path = root / "curated_airfoil_dataset.csv"
    df.to_csv(path, index=False)
    return path


def _basic_rows(airfoil_id: str = "abc123", re: float = 1e6, mach: float = 0.0):
    rows = []
    for alpha_i, cl, cd in [
        (0.0, 0.20, 0.009),
        (2.0, 0.40, 0.010),
        (4.0, 0.60, 0.012),
        (6.0, 0.80, 0.016),
        (8.0, 0.95, 0.025),
        (-2.0, 0.00, 0.012),
        (-4.0, -0.20, 0.020),
    ]:
        rows.append({
            "airfoil_id": airfoil_id,
            "airfoil_name": "Test",
            "alpha_deg": alpha_i,
            "reynolds": re,
            "mach": mach,
            "ncrit": 9.0,
            "cl": cl,
            "cd": cd,
            "cm": -0.05,
            "converged": True,
            "solver_id": "xfoil_python",
        })
    return rows


# ---------------------------------------------------------------------------
# CdclParams tests
# ---------------------------------------------------------------------------

def test_cdcl_params_as_avl_line_format():
    p = CdclParams(cl1=-0.5, cd1=0.02, cl2=0.2, cd2=0.008, cl3=1.0, cd3=0.03)
    line = p.as_avl_line()
    parts = line.split()
    assert len(parts) == 6
    assert float(parts[0]) == pytest.approx(-0.5, abs=1e-4)
    assert float(parts[2]) == pytest.approx(0.2, abs=1e-4)


def test_cdcl_params_is_valid():
    good = CdclParams(cl1=-0.5, cd1=0.02, cl2=0.2, cd2=0.008, cl3=1.0, cd3=0.03)
    assert good.is_valid()

    # cd2 = 0 (invalid)
    bad = CdclParams(cl1=-0.5, cd1=0.02, cl2=0.2, cd2=0.0, cl3=1.0, cd3=0.03)
    assert not bad.is_valid()

    # cl ordering violated
    bad2 = CdclParams(cl1=0.5, cd1=0.02, cl2=0.2, cd2=0.008, cl3=1.0, cd3=0.03)
    assert not bad2.is_valid()


# ---------------------------------------------------------------------------
# Core fitting algorithm
# ---------------------------------------------------------------------------

def test_fit_cdcl_from_arrays_basic():
    cls, cds = _make_parabolic_polar(cl_min=0.2, cd_min=0.008)
    params = _fit_cdcl_from_arrays(cls, cds)
    assert params.is_valid()
    assert params.cl1 < params.cl2 < params.cl3
    assert params.cd2 == pytest.approx(0.008, rel=0.05)
    assert params.cl2 == pytest.approx(0.2, abs=0.2)   # within ±0.2 of true minimum


def test_fit_cdcl_too_few_points_raises():
    with pytest.raises(ValueError, match="Need"):
        _fit_cdcl_from_arrays(np.array([0.0, 0.2]), np.array([0.01, 0.009]))


def test_fit_cdcl_monotone_increasing_cd():
    """Polar with no clear bucket — should still produce valid params."""
    cls = np.linspace(-0.5, 1.5, 15)
    cds = 0.01 + 0.01 * np.abs(cls)   # V-shape
    params = _fit_cdcl_from_arrays(cls, cds)
    assert params.is_valid()


def test_fit_cdcl_single_minimum():
    """Perfect parabola with a single sharp minimum."""
    cls = np.linspace(-1.0, 1.5, 25)
    cl_min, cd_min = 0.3, 0.007
    cds = cd_min + 0.02 * (cls - cl_min) ** 2
    params = _fit_cdcl_from_arrays(cls, cds)
    assert params.is_valid()
    assert params.cd2 == pytest.approx(cd_min, rel=0.05)


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------

def test_bracket_within_range():
    bins = np.array([1e5, 5e5, 1e6, 2e6])
    lo, hi = _bracket(bins, 7e5)
    assert lo == 5e5
    assert hi == 1e6


def test_bracket_below_range_clamps():
    bins = np.array([1e5, 1e6])
    lo, hi = _bracket(bins, 5e4)
    assert lo == 1e5
    assert hi == 1e5  # clamped — same bin


def test_bracket_single_bin():
    bins = np.array([1e6])
    lo, hi = _bracket(bins, 5e5)
    assert lo == hi == 1e6


def test_nearest_exact_match():
    bins = np.array([0.0, 0.1, 0.2, 0.3])
    assert _nearest(bins, 0.2) == pytest.approx(0.2)


def test_nearest_midpoint_picks_closer():
    bins = np.array([0.0, 0.1])
    assert _nearest(bins, 0.04) == pytest.approx(0.0)
    assert _nearest(bins, 0.06) == pytest.approx(0.1)


def test_interpolate_cdcl_midpoint():
    lo = CdclParams(cl1=-0.5, cd1=0.02, cl2=0.0, cd2=0.008, cl3=1.0, cd3=0.025)
    hi = CdclParams(cl1=-0.4, cd1=0.018, cl2=0.1, cd2=0.007, cl3=1.1, cd3=0.022)
    mid = _interpolate_cdcl(lo, hi, 0.5)
    assert mid.cl2 == pytest.approx(0.05, abs=1e-6)
    assert mid.cd2 == pytest.approx(0.0075, abs=1e-6)
    assert mid.is_valid()


# ---------------------------------------------------------------------------
# AirfoilPolarStore tests
# ---------------------------------------------------------------------------

def test_polar_store_loads_and_has_airfoil(tmp_path):
    _write_polar_csv(tmp_path, _basic_rows())
    store = AirfoilPolarStore(tmp_path / "curated_airfoil_dataset.csv")
    assert store.has_airfoil("abc123")
    assert not store.has_airfoil("unknown_id")


def test_polar_store_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        AirfoilPolarStore(tmp_path / "nonexistent.csv")


def test_polar_store_missing_column_raises(tmp_path):
    df = pd.DataFrame({"airfoil_id": ["abc"], "cl": [0.1]})
    bad_csv = tmp_path / "bad.csv"
    df.to_csv(bad_csv, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        AirfoilPolarStore(bad_csv)


def test_polar_store_fit_cdcl_returns_valid(tmp_path):
    _write_polar_csv(tmp_path, _basic_rows())
    store = AirfoilPolarStore(tmp_path / "curated_airfoil_dataset.csv")
    params = store.fit_cdcl("abc123", re=1e6)
    assert params is not None
    assert params.is_valid()


def test_polar_store_fit_cdcl_unknown_airfoil_returns_none(tmp_path):
    _write_polar_csv(tmp_path, _basic_rows())
    store = AirfoilPolarStore(tmp_path / "curated_airfoil_dataset.csv")
    assert store.fit_cdcl("unknown", re=1e6) is None


def test_polar_store_query_cd_returns_finite(tmp_path):
    _write_polar_csv(tmp_path, _basic_rows())
    store = AirfoilPolarStore(tmp_path / "curated_airfoil_dataset.csv")
    cd = store.query_cd("abc123", cl=0.4, re=1e6)
    assert cd is not None
    assert math.isfinite(cd)
    assert cd > 0


def test_polar_store_query_cd_unknown_returns_none(tmp_path):
    _write_polar_csv(tmp_path, _basic_rows())
    store = AirfoilPolarStore(tmp_path / "curated_airfoil_dataset.csv")
    assert store.query_cd("unknown", cl=0.4, re=1e6) is None


def test_polar_store_re_interpolation(tmp_path):
    """Fit at intermediate Re should produce cd2 between the two bin values."""
    rows = _basic_rows("foil_a", re=5e5) + _basic_rows("foil_a", re=2e6)
    # Adjust cd slightly per Re to make them distinguishable
    for r in rows:
        if r["reynolds"] == 2e6:
            r["cd"] *= 0.9  # lower cd at higher Re
    _write_polar_csv(tmp_path, rows)
    store = AirfoilPolarStore(tmp_path / "curated_airfoil_dataset.csv")

    params_lo = store.fit_cdcl("foil_a", re=5e5)
    params_hi = store.fit_cdcl("foil_a", re=2e6)
    params_mid = store.fit_cdcl("foil_a", re=1e6)

    assert params_lo is not None
    assert params_hi is not None
    assert params_mid is not None
    # Intermediate cd2 should be between lo and hi
    assert params_hi.cd2 <= params_mid.cd2 <= params_lo.cd2 + 1e-8


def test_polar_store_unconverged_rows_excluded(tmp_path):
    rows = _basic_rows()
    # Add unconverged rows that would skew the polar
    for cl_bad in [2.0, 3.0]:
        rows.append({
            "airfoil_id": "abc123", "airfoil_name": "Test",
            "alpha_deg": 30.0, "reynolds": 1e6, "mach": 0.0, "ncrit": 9.0,
            "cl": cl_bad, "cd": 0.5, "cm": 0.0,
            "converged": False, "solver_id": "xfoil_python",
        })
    _write_polar_csv(tmp_path, rows)
    store = AirfoilPolarStore(tmp_path / "curated_airfoil_dataset.csv")
    params = store.fit_cdcl("abc123", re=1e6)
    assert params is not None
    # cd_min should not be polluted by unconverged rows
    assert params.cd2 < 0.1
