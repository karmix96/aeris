"""CAD (STEP) -> tet fluid mesh: roundtrip test with a generated solid."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("gmsh")

from aeris.cfd.meshing.gmsh_cad import CadGmshTetV1  # noqa: E402


@pytest.fixture(scope="module")
def step_solid(tmp_path_factory) -> Path:
    """Generate a STEP file (wing-box-like solid) with gmsh itself."""
    import gmsh

    path = tmp_path_factory.mktemp("cad") / "wingbox.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("wingbox")
        # slender box: chord 1 x span 4 x thickness 0.12 (wing-ish proportions)
        gmsh.model.occ.addBox(0, 0, 0, 1.0, 4.0, 0.12)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


@pytest.fixture(scope="module")
def meshed(step_solid: Path, tmp_path_factory) -> Path:
    output = tmp_path_factory.mktemp("cad_mesh") / "surface"
    CadGmshTetV1().generate(
        step_solid,
        output,
        {"farfield_factor": 5.0, "wall_size_rel": 0.2, "farfield_size_rel": 0.5},
    )
    return output


def test_step_roundtrip_produces_3d_su2(meshed: Path):
    text = (meshed / "mesh.su2").read_text()
    assert "NDIME= 3" in text
    assert "MARKER_TAG= wall" in text
    assert "MARKER_TAG= farfield" in text


def test_report_contents(meshed: Path):
    report = json.loads((meshed / "surface_report.json").read_text())
    assert report["topology"] == "cad_gmsh_tet_v1"
    assert report["final_mesh"] is True
    assert report["solver_compatibility"] == ["su2"]
    assert report["n_volume_elements"] > 500
    assert report["n_wall_surfaces"] == 6  # the box faces
    assert report["farfield_radius"] > report["characteristic_length"]


def test_registered():
    from aeris.cfd.meshing.registry import get_topology

    assert get_topology("cad_gmsh_tet_v1").DIMENSION == 3


def test_non_cad_suffix_rejected(tmp_path: Path):
    bad = tmp_path / "geom.txt"
    bad.write_text("x")
    with pytest.raises(ValueError, match="CAD file"):
        CadGmshTetV1().generate(bad, tmp_path / "out", {})


def test_missing_file_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        CadGmshTetV1().generate(tmp_path / "nope.step", tmp_path / "out", {})
