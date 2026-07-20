"""Structured CGNS -> .su2 conversion: node merge, hexas, markers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

from aeris.cfd.solvers.su2.mesh_convert import (  # noqa: E402
    convert_structured_cgns_to_su2,
    read_structured_cgns,
)


def _write_cgns(path: Path, ni: int = 5, nj: int = 2, nk: int = 3, o_seam: bool = True):
    """Minimal CGNS/HDF5 with one structured zone + wall/Far BCs.

    With ``o_seam`` the i=1 and i=ni node planes are coincident (an O-grid
    seam closed by 1-to-1 connectivity, as pyHyp writes it).
    """
    theta = np.linspace(0.0, 2 * np.pi, ni)  # endpoint duplicated = seam
    radius = 1.0 + np.arange(nk)
    x = np.zeros((ni, nj, nk))
    y = np.zeros((ni, nj, nk))
    z = np.zeros((ni, nj, nk))
    for k in range(nk):
        x[:, :, k] = (radius[k] * np.cos(theta))[:, None]
        y[:, :, k] = (radius[k] * np.sin(theta))[:, None]
    z[:, 1, :] = 1.0
    if not o_seam:
        x[-1, :, :] += 0.5  # break the coincidence

    def _string_node(group, name, label, text):
        node = group.create_group(name)
        node.attrs["label"] = np.bytes_(label)
        node.create_dataset(" data", data=np.frombuffer(text.encode(), dtype=np.uint8))
        return node

    with h5py.File(path, "w") as handle:
        base = handle.create_group("BASE#1")
        base.attrs["label"] = np.bytes_("CGNSBase_t")
        zone = base.create_group("dom.1")
        zone.attrs["label"] = np.bytes_("Zone_t")
        coords = zone.create_group("GridCoordinates")
        coords.attrs["label"] = np.bytes_("GridCoordinates_t")
        for name, arr in (("CoordinateX", x), ("CoordinateY", y), ("CoordinateZ", z)):
            data_group = coords.create_group(name)
            data_group.attrs["label"] = np.bytes_("DataArray_t")
            # CGNS/HDF5 stores dims reversed (C order)
            data_group.create_dataset(" data", data=arr.transpose(2, 1, 0))
        zone_bc = zone.create_group("ZoneBC")
        zone_bc.attrs["label"] = np.bytes_("ZoneBC_t")
        for name, family, prange in (
            ("BC1", "wall", [[1, 1, 1], [ni, nj, 1]]),
            ("BC2", "Far", [[1, 1, nk], [ni, nj, nk]]),
        ):
            bc = _string_node(zone_bc, name, "BC_t", "BCWallViscous")
            pr = bc.create_group("PointRange")
            pr.attrs["label"] = np.bytes_("IndexRange_t")
            pr.create_dataset(" data", data=np.array(prange))
            _string_node(bc, "FamilyName", "FamilyName_t", family)
    return path


def test_read_structured_cgns(tmp_path: Path):
    path = _write_cgns(tmp_path / "grid.cgns")
    zones = read_structured_cgns(path)
    assert len(zones) == 1
    assert zones[0].x.shape == (5, 2, 3)
    assert {bc["family"] for bc in zones[0].bcs} == {"wall", "Far"}


def test_convert_merges_seam_and_counts(tmp_path: Path):
    path = _write_cgns(tmp_path / "grid.cgns")
    report = convert_structured_cgns_to_su2(path, tmp_path / "mesh.su2")
    ni, nj, nk = 5, 2, 3
    assert report["n_points_structured"] == ni * nj * nk
    assert report["n_merged_duplicates"] == nj * nk  # the O-seam plane
    assert report["n_hexa"] == (ni - 1) * (nj - 1) * (nk - 1)
    assert report["markers"] == {"wall": 4, "Far": 4}

    # one-cell strip: y/z swapped so lift lands on SU2's z convention
    assert report["swapped_yz"] is True

    text = (tmp_path / "mesh.su2").read_text().splitlines()
    assert text[0] == "NDIME= 3"
    assert text[1] == f"NELEM= {report['n_hexa']}"
    # every hexa node id must be < merged point count
    for line in text[2 : 2 + report["n_hexa"]]:
        ids = list(map(int, line.split()))[1:-1]
        assert all(0 <= node < report["n_points_merged"] for node in ids)
    assert (tmp_path / "mesh.convert.json").is_file()


def test_convert_without_seam_merges_nothing(tmp_path: Path):
    path = _write_cgns(tmp_path / "grid.cgns", o_seam=False)
    report = convert_structured_cgns_to_su2(path, tmp_path / "mesh.su2")
    assert report["n_merged_duplicates"] == 0
