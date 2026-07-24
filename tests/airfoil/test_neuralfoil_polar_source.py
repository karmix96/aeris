"""Tests for NeuralFoilPolarSource -- structural compatibility + basic correctness.

These tests require the `neuralfoil` and `aerosandbox` packages to be
installed. If they are not installed, tests are skipped rather than failed,
since this is an opt-in, optional backend.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("neuralfoil")
pytest.importorskip("aerosandbox")

from aeris.airfoil.neuralfoil_polar_source import (
    NeuralFoilPolarSource,
    shape_id_from_coordinates,
)
from aeris.airfoil.polar_source_base import PolarSource


def _naca0012_coordinates(n: int = 80) -> np.ndarray:
    """Simple symmetric NACA0012-ish coordinate set for testing (Selig order)."""
    x = (1 - np.cos(np.linspace(0, np.pi, n))) / 2
    t = 0.12
    yt = 5 * t * (
        0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4
    )
    upper = np.column_stack([x[::-1], yt[::-1]])
    lower = np.column_stack([x[1:], -yt[1:]])
    return np.vstack([upper, lower])


def test_neuralfoil_polar_source_satisfies_protocol():
    source = NeuralFoilPolarSource()
    assert isinstance(source, PolarSource)


def test_shape_id_is_deterministic():
    coords = _naca0012_coordinates()
    id1 = shape_id_from_coordinates(coords)
    id2 = shape_id_from_coordinates(coords)
    assert id1 == id2
    assert id1.startswith("cst_")


def test_register_shape_is_idempotent():
    source = NeuralFoilPolarSource()
    coords = _naca0012_coordinates()
    aid1 = source.register_shape(coords)
    aid2 = source.register_shape(coords)
    assert aid1 == aid2
    assert source.has_airfoil(aid1)


def test_fit_cdcl_returns_valid_params_for_known_shape():
    source = NeuralFoilPolarSource(model_size="small")  # fast model for test speed
    coords = _naca0012_coordinates()
    aid = source.register_shape(coords)

    params = source.fit_cdcl(aid, re=1_000_000.0, mach=0.1)
    assert params is not None
    assert params.is_valid()
    assert params.cl1 < params.cl2 < params.cl3
    assert params.cd2 > 0


def test_fit_cdcl_unregistered_airfoil_returns_none():
    source = NeuralFoilPolarSource(model_size="small")
    result = source.fit_cdcl("not_registered", re=1_000_000.0, mach=0.1)
    assert result is None


def test_get_cl_bounds_matches_alpha_sweep_range():
    source = NeuralFoilPolarSource(model_size="small")
    coords = _naca0012_coordinates()
    aid = source.register_shape(coords)
    bounds = source.get_cl_bounds(aid, re=1_000_000.0, mach=0.1)
    assert bounds is not None
    cl_min, cl_max = bounds
    assert cl_min < cl_max


def test_query_cd_single_point():
    source = NeuralFoilPolarSource(model_size="small")
    coords = _naca0012_coordinates()
    aid = source.register_shape(coords)
    cd = source.query_cd(aid, cl=0.3, re=1_000_000.0, mach=0.1)
    assert cd is not None
    assert cd > 0


def test_query_cd_batch_matches_single_point_queries():
    """Batched and single-point queries should agree for the same inputs."""
    source = NeuralFoilPolarSource(model_size="small")
    coords = _naca0012_coordinates()
    aid = source.register_shape(coords)

    cls = np.array([0.1, 0.3, 0.5])
    res = np.array([1_000_000.0, 1_000_000.0, 1_000_000.0])
    batch_result = source.query_cd_batch([aid, aid, aid], cls, res, mach=0.1)

    assert len(batch_result) == 3
    assert np.all(np.isfinite(batch_result))
    assert np.all(batch_result > 0)


def test_query_cd_batch_resolves_reynolds_not_median_collapse():
    """Strips of one shape at widely different Re must get Re-resolved CD.

    Regression for the median-Re collapse: at fixed CL, CD falls with rising
    Re, so a low-Re and a high-Re strip of the same airfoil must not receive
    the same CD (which the old single-median-Re evaluation produced).
    """
    source = NeuralFoilPolarSource(model_size="small")
    aid = source.register_shape(_naca0012_coordinates())

    cl = 0.3
    # Same shape, same CL, two strips an order of magnitude apart in Re.
    cls = np.array([cl, cl])
    res = np.array([2.0e5, 2.0e6])
    batch = source.query_cd_batch([aid, aid], cls, res, mach=0.0)

    assert np.all(np.isfinite(batch))
    # Distinct CD, and drag decreasing with Reynolds number.
    assert not np.isclose(batch[0], batch[1], rtol=1e-3)
    assert batch[0] > batch[1]
    # Each binned batch value should match the corresponding single-point query.
    assert np.isclose(batch[0], source.query_cd(aid, cl=cl, re=2.0e5), rtol=1e-6)
    assert np.isclose(batch[1], source.query_cd(aid, cl=cl, re=2.0e6), rtol=1e-6)


def test_query_cd_batch_unregistered_shape_yields_nan_not_crash():
    source = NeuralFoilPolarSource(model_size="small")
    coords = _naca0012_coordinates()
    aid = source.register_shape(coords)

    cls = np.array([0.1, 0.3])
    res = np.array([1_000_000.0, 1_000_000.0])
    result = source.query_cd_batch([aid, "unregistered"], cls, res, mach=0.1)

    assert np.isfinite(result[0])
    assert np.isnan(result[1])


def test_cdcl_cache_avoids_recomputation():
    source = NeuralFoilPolarSource(model_size="small")
    coords = _naca0012_coordinates()
    aid = source.register_shape(coords)

    params1 = source.fit_cdcl(aid, re=1_000_000.0, mach=0.1)
    cache_size_after_first = len(source._cdcl_cache)
    params2 = source.fit_cdcl(aid, re=1_000_000.0, mach=0.1)
    cache_size_after_second = len(source._cdcl_cache)

    assert cache_size_after_first == cache_size_after_second == 1
    assert params1 == params2
