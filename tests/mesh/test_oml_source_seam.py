"""The OML geometry-source seam: dispatch + contract.

The seam lets a pyGeo-native source replace AeroSandbox without touching the
mesher's topology/QC back-end.  These tests pin the dispatch behaviour; the
end-to-end block production is covered by the topology-registry build tests.
"""

from __future__ import annotations

import dataclasses

import pytest

from aeris.mesh.surface import (
    AeroSandboxOmlSource,
    MeshBuildError,
    OmlTopologyParams,
    _oml_source_for,
)


class _FakeWing:
    """Minimal duck type matching the AeroSandbox Wing contract the seam checks."""

    xsecs: list = []

    def mesh_line(self, *args, **kwargs):  # pragma: no cover - never called here
        raise AssertionError("not exercised")


def test_wing_like_geometry_selects_aerosandbox_source():
    src = _oml_source_for(_FakeWing())
    assert isinstance(src, AeroSandboxOmlSource)


def test_non_wing_geometry_raises_clearly():
    with pytest.raises(MeshBuildError, match="AeroSandbox Wing.*or a pyGeo surface carrier"):
        _oml_source_for(object())


def test_geometry_missing_mesh_line_is_rejected():
    class NoLoft:
        xsecs: list = []

    with pytest.raises(MeshBuildError):
        _oml_source_for(NoLoft())


def test_topology_params_is_immutable():
    # The params object is passed through the seam and must not be mutated.
    assert dataclasses.is_dataclass(OmlTopologyParams)
    p = OmlTopologyParams(
        oml_topology="cap4", points_per_block_side=49, cap_wrap_points=21,
        cap_wrap_x=0.15, split_x_fore=0.20, dense_airfoil_points_per_surface=301,
        minimum_te_thickness=2.0e-3, te_thickness=0.005, te_thickness_abs_floor=0.0,
        te_base_points=0, chordwise_distribution="junction", chordwise_beta=2.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.te_thickness = 0.01  # type: ignore[misc]
