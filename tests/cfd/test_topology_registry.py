"""Topology registry semantics, plugin loading, and quality metrics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aeris.cfd.meshing.base import MeshTopologyGenerator
from aeris.cfd.meshing.quality import block_quality_metrics
from aeris.cfd.meshing.registry import (
    clear_registry_for_tests,
    get_topology,
    list_topologies,
    register_topology,
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    clear_registry_for_tests()
    yield
    clear_registry_for_tests()


class _Toy(MeshTopologyGenerator):
    TOPOLOGY_ID = "toy_v1"
    DIMENSION = 2
    DESCRIPTION = "toy"

    def generate(self, geometry, output_dir: Path, params):
        return {"characteristic_length": 1.0}


def test_register_and_get():
    register_topology(_Toy)
    assert isinstance(get_topology("toy_v1"), _Toy)


def test_missing_id_rejected():
    class Bad(MeshTopologyGenerator):
        DIMENSION = 2

        def generate(self, geometry, output_dir, params):
            return {}

    with pytest.raises(ValueError, match="TOPOLOGY_ID"):
        register_topology(Bad)


def test_bad_dimension_rejected():
    class Bad(MeshTopologyGenerator):
        TOPOLOGY_ID = "bad_v1"
        DIMENSION = 4

        def generate(self, geometry, output_dir, params):
            return {}

    with pytest.raises(ValueError, match="DIMENSION"):
        register_topology(Bad)


def test_duplicate_id_rejected():
    register_topology(_Toy)

    class Clash(MeshTopologyGenerator):
        TOPOLOGY_ID = "toy_v1"
        DIMENSION = 2

        def generate(self, geometry, output_dir, params):
            return {}

    with pytest.raises(ValueError, match="Duplicate"):
        register_topology(Clash)


def test_unknown_id_lists_available():
    register_topology(_Toy)
    with pytest.raises(ValueError, match="Available"):
        get_topology("nope_v1")


def test_aeris_wing_plugins_register():
    """The AERIS plugin module provides the three validated wing topologies."""
    ids = {t.TOPOLOGY_ID for t in list_topologies()}
    assert {"wing_mid4_v1", "wing_split8_v1", "wing_cap4_v1"} <= ids


def test_wing_adapter_rejects_unknown_params():
    from aeris.mesh.topologies import WingCap4V1

    with pytest.raises(ValueError, match="unknown surface params"):
        WingCap4V1().generate(object(), Path("/tmp/x"), {"points_per_sside": 49})


# ── quality metrics ──────────────────────────────────────────────────────────


def _grid(ni: int, nj: int, shear: float = 0.0, stretch: float = 1.0) -> np.ndarray:
    x = np.arange(ni, dtype=float)
    y = np.arange(nj, dtype=float) * stretch
    nodes = np.zeros((ni, nj, 3))
    nodes[:, :, 0] = x[:, None] + shear * y[None, :]
    nodes[:, :, 1] = y[None, :]
    return nodes


def test_unit_grid_is_perfect():
    metrics = block_quality_metrics(_grid(5, 5))
    assert metrics["min_scaled_jacobian"] == pytest.approx(1.0)
    assert metrics["max_equiangle_skewness"] == pytest.approx(0.0, abs=1e-12)
    assert metrics["max_aspect_ratio"] == pytest.approx(1.0)
    assert metrics["max_growth_ratio"] == pytest.approx(1.0)


def test_sheared_grid_has_known_skew():
    # 45-degree shear: corner angles 45/135 -> skewness 0.5, jacobian sin(45)
    metrics = block_quality_metrics(_grid(4, 4, shear=1.0))
    assert metrics["max_equiangle_skewness"] == pytest.approx(0.5)
    assert metrics["min_scaled_jacobian"] == pytest.approx(np.sin(np.radians(45.0)))


def test_stretched_grid_aspect_ratio():
    metrics = block_quality_metrics(_grid(4, 4, stretch=4.0))
    assert metrics["max_aspect_ratio"] == pytest.approx(4.0)


def test_geometric_growth_detected():
    nodes = np.zeros((5, 2, 3))
    spacing = np.array([1.0, 1.2, 1.44, 1.728])
    nodes[:, :, 0] = np.concatenate([[0.0], np.cumsum(spacing)])[:, None]
    nodes[:, 1, 1] = 1.0
    metrics = block_quality_metrics(nodes)
    assert metrics["max_growth_ratio"] == pytest.approx(1.2)
