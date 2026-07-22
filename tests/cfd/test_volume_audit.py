"""Geometric audit of written pyHyp volume meshes."""

from __future__ import annotations

import numpy as np
import pytest

from aeris.cfd.meshing.volume_audit import (
    audit_volume_cgns,
    signed_cell_volumes,
    summarize_audit,
)


def _uniform_block(n_layers: int = 4, n_j: int = 5, n_i: int = 6) -> np.ndarray:
    """(K, J, I, 3) block of unit cells, marching along axis 0."""
    k, j, i = np.meshgrid(
        np.arange(n_layers, dtype=float),
        np.arange(n_j, dtype=float),
        np.arange(n_i, dtype=float),
        indexing="ij",
    )
    return np.stack([i, j, k], axis=-1)


def test_uniform_block_has_unit_positive_volumes():
    volumes = signed_cell_volumes(_uniform_block())
    assert volumes.shape == (3, 4, 5)
    assert np.allclose(volumes, 1.0)


def test_volume_is_scale_cubed():
    volumes = signed_cell_volumes(_uniform_block() * 2.0)
    assert np.allclose(volumes, 8.0)


def test_folded_layer_gives_negative_volume():
    """A marched face folding back behind the wall inverts its cell.

    The whole 2x2 node patch has to move: displacing a single corner only
    removes a quarter of the cell volume, which stays positive.
    """
    block = _uniform_block()
    block[1, 2:4, 3:5, 2] = -1.0
    volumes = signed_cell_volumes(block)
    assert volumes[0, 2, 3] == pytest.approx(-1.0)


def test_sign_flips_with_handedness():
    volumes = signed_cell_volumes(_uniform_block()[:, ::-1])
    assert np.allclose(volumes, -1.0)


def _write_cgns(path, blocks):
    h5py = pytest.importorskip("h5py")
    with h5py.File(str(path), "w") as handle:
        base = handle.create_group("BASE#1")
        base.attrs["label"] = np.bytes_("CGNSBase_t")
        for name, nodes in blocks.items():
            zone = base.create_group(name)
            zone.attrs["label"] = np.bytes_("Zone_t")
            coords = zone.create_group("GridCoordinates")
            for axis, index in zip("XYZ", range(3)):
                array = coords.create_group(f"Coordinate{axis}")
                array.create_dataset(" data", data=nodes[..., index])


def test_audit_reports_clean_mesh(tmp_path):
    path = tmp_path / "clean.cgns"
    _write_cgns(path, {"domain.00001": _uniform_block()})
    audit = audit_volume_cgns(path)
    assert audit["classification"] == "clean"
    assert audit["inverted_cells"] == 0
    assert audit["min_volume"] == pytest.approx(1.0)
    assert "clean" in summarize_audit(audit)


def test_audit_localizes_a_small_inverted_cluster(tmp_path):
    """The cap4 failure signature: a few cells folded on a spanwise edge."""
    block = _uniform_block(n_layers=6, n_j=100, n_i=100)
    block[1, 0:2, 3:5, 2] = -1.0  # fold against the j=0 spanwise edge
    path = tmp_path / "localized.cgns"
    _write_cgns(path, {"domain.00001": block})

    audit = audit_volume_cgns(path)
    assert audit["classification"] == "inverted_localized"
    assert audit["inverted_cells"] == 3
    cluster = audit["clusters"][0]
    assert cluster["block"] == "domain.00001"
    assert cluster["on_spanwise_edge"] is True
    assert cluster["wall_adjacent"] is True
    assert cluster["j_range"] == [0, 1]
    assert cluster["i_range"] == [3, 4]
    # Wall footprint is read off layer 0, so it locates the defect on the
    # geometry rather than in index space.
    assert cluster["wall_bbox"]["x"] == [3.0, 4.0]


def test_audit_flags_widespread_inversion(tmp_path):
    block = _uniform_block(n_layers=6, n_j=100, n_i=100)
    block[4, :, :, 2] = -5.0  # whole marching front collapses back
    path = tmp_path / "widespread.cgns"
    _write_cgns(path, {"domain.00001": block})

    audit = audit_volume_cgns(path)
    assert audit["classification"] == "inverted_widespread"
    assert audit["inverted_fraction"] > 1e-4


def test_localized_and_widespread_differ_only_by_extent(tmp_path):
    """Same fold depth, more of it — the classifier keys on extent, not depth."""
    small = _uniform_block(n_layers=6, n_j=100, n_i=100)
    small[1, 0:2, 3:5, 2] = -1.0
    large = _uniform_block(n_layers=6, n_j=100, n_i=100)
    large[1, 0:40, 3:40, 2] = -1.0
    for name, block, expected in (
        ("small", small, "inverted_localized"),
        ("large", large, "inverted_widespread"),
    ):
        path = tmp_path / f"{name}.cgns"
        _write_cgns(path, {"domain.00001": block})
        audit = audit_volume_cgns(path)
        assert audit["classification"] == expected
        assert audit["min_volume"] == pytest.approx(-1.0)


def test_audit_is_invariant_to_chunk_size(tmp_path):
    """Slab reads must not drop or double-count cells at chunk boundaries."""
    block = _uniform_block(n_layers=20, n_j=30, n_i=30)
    block[1, 0:2, 3:5, 2] = -1.0  # first slab
    block[9, 5:7, 8:10, 2] = 8.0  # straddles a boundary at chunk_layers=8
    block[17, 9:11, 2:4, 2] = 16.0  # last slab
    path = tmp_path / "chunked.cgns"
    _write_cgns(path, {"domain.00001": block})

    results = [
        audit_volume_cgns(path, chunk_layers=chunk) for chunk in (1, 3, 8, 19, 100)
    ]
    reference = results[0]
    assert reference["inverted_cells"] > 0
    for audit in results[1:]:
        assert audit["inverted_cells"] == reference["inverted_cells"]
        assert audit["total_cells"] == reference["total_cells"]
        assert audit["min_volume"] == pytest.approx(reference["min_volume"])
        assert audit["clusters"] == reference["clusters"]


def test_audit_aggregates_across_blocks(tmp_path):
    good = _uniform_block(n_layers=6, n_j=100, n_i=100)
    bad = _uniform_block(n_layers=6, n_j=100, n_i=100)
    bad[1, 0:2, 3:5, 2] = -1.0
    path = tmp_path / "multi.cgns"
    _write_cgns(path, {"domain.00001": good, "domain.00002": bad})

    audit = audit_volume_cgns(path)
    assert audit["block_count"] == 2
    assert len(audit["clusters"]) == 1
    assert audit["clusters"][0]["block"] == "domain.00002"
    assert audit["total_cells"] == 2 * 5 * 99 * 99
