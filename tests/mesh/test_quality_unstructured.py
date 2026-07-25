"""Unstructured cell-quality metrics, checked against cells whose quality is
known by construction rather than against a previous run of the same code."""

from __future__ import annotations

import numpy as np
import pytest

from aeris.cfd.meshing.quality_unstructured import assess_cells, quality_gates

S3 = np.sqrt(3.0) / 2.0
TRI = np.array([[0, 0, 0], [1, 0, 0], [0.5, S3, 0]], float)
SQUARE = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
REG_TET = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
ONE = np.array([[0, 1, 2, 3]])


def test_ideal_cells_score_one():
    assert assess_cells(TRI, np.array([[0, 1, 2]]), "tri").scaled_jacobian_min == pytest.approx(1.0)
    assert assess_cells(SQUARE, ONE, "quad").scaled_jacobian_min == pytest.approx(1.0)
    assert assess_cells(REG_TET, ONE, "tet").scaled_jacobian_min == pytest.approx(1.0)


def test_ideal_cells_have_zero_skewness():
    assert assess_cells(TRI, np.array([[0, 1, 2]]), "tri").skewness_max == pytest.approx(0.0, abs=1e-9)
    assert assess_cells(SQUARE, ONE, "quad").skewness_max == pytest.approx(0.0, abs=1e-9)


def test_regular_tet_dihedral_matches_the_analytic_value():
    """arccos(1/3) = 70.5288 deg — a value the code cannot fudge."""
    b = assess_cells(REG_TET, ONE, "tet")
    assert b.min_dihedral_deg == pytest.approx(np.degrees(np.arccos(1 / 3)), abs=1e-6)


def test_node_winding_is_normalised_but_mixed_winding_fails():
    """A block using the opposite convention is not a broken mesh; a block with
    BOTH conventions is."""
    pos = REG_TET[[0, 2, 1, 3]]
    assert assess_cells(pos, ONE, "tet").scaled_jacobian_min == pytest.approx(1.0)
    neg = assess_cells(REG_TET, ONE, "tet")
    assert neg.scaled_jacobian_min == pytest.approx(1.0)
    assert neg.orientation_flipped is True

    mixed = assess_cells(np.vstack([REG_TET, pos]),
                         np.array([[0, 1, 2, 3], [4, 5, 6, 7]]), "tet")
    assert mixed.n_inverted == 1
    assert quality_gates([mixed]).passed is False


def test_inverted_cell_fails_the_gate():
    inv = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    rep = quality_gates([assess_cells(inv, ONE, "quad")])
    assert rep.passed is False
    assert any("inverted" in f for f in rep.failures)


def test_boundary_layer_anisotropy_is_reported_not_failed():
    """A viscous mesh is SUPPOSED to have high aspect ratio. Gating on it would
    reject every RANS mesh ever built."""
    bl = np.array([[0, 0, 0], [1, 0, 0], [1, 1e-3, 0], [0, 1e-3, 0]], float)
    b = assess_cells(bl, ONE, "quad")
    assert b.aspect_ratio_max == pytest.approx(1000.0, rel=1e-6)
    assert b.scaled_jacobian_min == pytest.approx(1.0)
    assert quality_gates([b]).passed is True


def test_sliver_tet_is_detected():
    sliver = np.array([[0, 0, 0], [1, 0, 0], [0.5, S3, 0], [0.5, 0.29, 1e-3]], float)
    b = assess_cells(sliver, ONE, "tet")
    assert b.min_dihedral_deg < 1.0
    assert quality_gates([b]).warnings


def test_skewed_cell_crosses_the_documented_thresholds():
    skew = np.array([[0, 0, 0], [1, 0, 0], [1.9, 0.12, 0], [0.9, 0.12, 0]], float)
    b = assess_cells(skew, ONE, "quad")
    assert b.skewness_max > 0.85
    rep = quality_gates([b])
    assert rep.warnings or rep.failures


def test_report_round_trips_to_dict_and_summary():
    rep = quality_gates([assess_cells(SQUARE, ONE, "quad")])
    d = rep.to_dict()
    assert d["passed"] is True and d["n_cells"] == 1
    assert "PASS" in rep.summary()


def test_unknown_cell_type_is_refused():
    with pytest.raises(ValueError):
        assess_cells(SQUARE, ONE, "dodecahedron")
