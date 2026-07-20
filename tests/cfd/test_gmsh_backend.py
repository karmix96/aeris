"""Gmsh unstructured airfoil backend: mesh generation and case integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("gmsh")

from aeris.cfd.meshing.gmsh_backend import AirfoilGmshTriV1  # noqa: E402
from aeris.cfd.solvers.su2.adapter import markers_from_su2_mesh  # noqa: E402


@pytest.fixture(scope="module")
def coarse_mesh(tmp_path_factory) -> Path:
    """One coarse generation shared by the module (gmsh runs take seconds)."""
    output = tmp_path_factory.mktemp("gmsh") / "surface"
    AirfoilGmshTriV1().generate(
        "naca0012",
        output,
        {
            "n_per_surface": 41,
            "farfield_radius": 20.0,
            "wall_size": 0.05,
            "farfield_size": 5.0,
            "bl_hwall": 1.0e-4,
            "bl_thickness": 0.02,
        },
    )
    return output


def test_generates_true_2d_su2_mesh(coarse_mesh: Path):
    su2 = coarse_mesh / "mesh.su2"
    assert su2.is_file()
    text = su2.read_text()
    assert "NDIME= 2" in text
    assert "MARKER_TAG= wall" in text
    assert "MARKER_TAG= farfield" in text


def test_surface_report_declares_final_mesh(coarse_mesh: Path):
    report = json.loads((coarse_mesh / "surface_report.json").read_text())
    assert report["topology"] == "airfoil_gmsh_tri_v1"
    assert report["final_mesh"] is True
    assert report["true_2d"] is True
    assert report["solver_compatibility"] == ["su2"]
    assert report["n_nodes"] > 100
    assert report["n_elements_2d"] > 100
    assert report["characteristic_length"] == pytest.approx(1.0, abs=0.01)


def test_su2_markers_scanned_from_mesh(coarse_mesh: Path):
    markers = markers_from_su2_mesh(coarse_mesh / "mesh.su2")
    assert markers["marker_wall"] == "( wall, 0.0 )"
    assert markers["marker_far"] == "( farfield )"
    assert "marker_sym" not in markers  # no symmetry marker in a true 2D mesh
    assert markers["marker_monitoring"] == "( wall )"


def test_registered_in_topology_registry():
    from aeris.cfd.meshing.registry import get_topology

    assert get_topology("airfoil_gmsh_tri_v1").DIMENSION == 2


def test_unknown_params_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown params"):
        AirfoilGmshTriV1().generate("naca0012", tmp_path, {"n_points": 10})
