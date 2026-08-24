"""The AeroSandbox-free pyGeo OML source: split + frame map + TE floor.

Uses synthetic sections (no pyGeo dependency) so it runs in the normal env.
The real pyGeo end-to-end build is exercised by scripts/pygeo_provider_eval.py
under .venv.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from aeris.mesh.surface import (
    OmlTopologyParams,
    PyGeoSectionOmlSource,
    PyGeoSurfaceGeometry,
    _build_tip_airfoil_face_cap4,
    _oml_source_for,
    build_surface_mesh,
    select_wing,
)


@dataclass
class _FakeSection:
    direct_coordinates: np.ndarray
    chord_m: float
    le_xyz_m: np.ndarray
    chord_axis: np.ndarray
    thickness_axis: np.ndarray


def _airfoil_loop(te: float, n: int = 120) -> np.ndarray:
    """Thin symmetric airfoil, upper-TE -> LE -> lower-TE, with blunt TE gap `te`."""
    beta = np.linspace(0.0, np.pi, n)
    x = 0.5 * (1.0 - np.cos(beta))
    z = 0.1 * np.sqrt(x) * (1.0 - x) + 0.5 * te * x  # z(0)=0, z(1)=te/2
    upper = np.column_stack([x[::-1], z[::-1]])  # TE -> LE
    lower = np.column_stack([x[1:], -z[1:]])  # LE -> TE
    return np.vstack([upper, lower])


def _params(**over) -> OmlTopologyParams:
    base = dict(
        oml_topology="cap4",
        points_per_block_side=25,
        cap_wrap_points=11,
        cap_wrap_x=0.15,
        split_x_fore=0.20,
        dense_airfoil_points_per_surface=201,
        minimum_te_thickness=2.0e-3,
        te_thickness=0.005,
        te_thickness_abs_floor=0.0,
        te_base_points=0,
        chordwise_distribution="junction",
        chordwise_beta=2.0,
    )
    base.update(over)
    return OmlTopologyParams(**base)


def _sections(te: float, chord: float, le=(1.0, 2.0, 3.0)) -> list[_FakeSection]:
    loop = _airfoil_loop(te)
    return [
        _FakeSection(
            loop.copy(),
            chord,
            np.array([le[0], y, le[2]]),
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )
        for y in (2.0, 3.0, 4.0)
    ]


def test_dispatch_and_select_accept_the_carrier():
    geom = PyGeoSurfaceGeometry(sections=tuple(_sections(0.01, 1.0)))
    assert isinstance(_oml_source_for(geom), PyGeoSectionOmlSource)
    assert select_wing(geom, 0) is geom


def test_cap4_blocks_have_consistent_structure():
    src = PyGeoSectionOmlSource(_sections(0.01, 1.0))
    blocks = src.raw_oml_blocks(_params())
    assert len(blocks) == 4  # cap4: LE-wrap, lower chord, TE-wrap, upper chord
    n_stations = 3
    for b in blocks:
        assert b.ndim == 3 and b.shape[1] == n_stations and b.shape[2] == 3


def test_frame_mapping_is_exact_at_le_and_te():
    # chord_axis=+x, thickness_axis=+z, chord=2, le=(1,y,3):
    #   (x,z) -> (1+2x, y, 3+2z).  LE (0,0) -> le; TE base midpoint z=0 -> 3.
    chord, te = 2.0, 0.01
    src = PyGeoSectionOmlSource(_sections(te, chord))
    blocks = src.raw_oml_blocks(_params())
    pts = np.concatenate([b.reshape(-1, 3) for b in blocks], axis=0)
    # every point lies in its station's y-plane (span component untouched)
    assert set(np.round(pts[:, 1], 6)).issubset({2.0, 3.0, 4.0})
    # leading edge (min chordwise x) maps to x = le_x = 1.0
    assert pytest.approx(pts[:, 0].min(), abs=1e-6) == 1.0
    # trailing edge (max) maps to le_x + chord = 3.0
    assert pytest.approx(pts[:, 0].max(), abs=1e-6) == 1.0 + chord


def test_te_floor_thickens_a_small_chord_section():
    # The floor is baked into the source: with te_thickness=0, a 4 mm absolute
    # floor on a thin 0.2 m-chord section opens the TE (te_frac = 4mm/0.2m = 2%c
    # >> its 0.3%c native gap), so the TE-wrap block gets measurably thicker.
    secs = _sections(te=0.003, chord=0.2)

    def te_wrap_zext(floor: float) -> float:
        blocks = PyGeoSectionOmlSource(secs).raw_oml_blocks(
            _params(te_thickness=0.0, te_thickness_abs_floor=floor)
        )
        return float(np.ptp(blocks[2][:, 0, 2]))  # z-extent of the TE-wrap block

    assert te_wrap_zext(0.004) > 1.2 * te_wrap_zext(0.0)


def test_airfoil_face_tip_has_camber_line_grid_row():
    src = PyGeoSectionOmlSource(_sections(0.01, 1.0))
    raw_oml = src.raw_oml_blocks(_params(cap_wrap_points=11))

    _ring, center_patches, _groups = _build_tip_airfoil_face_cap4(
        raw_oml,
        collar_points=5,
        width_frac=0.5,
    )
    assert _ring == []
    assert len(center_patches) == 1
    center = center_patches[0]

    # The full-face cap is not a collar/ribbon.  It is one structured block;
    # the middle row is the physical camber-line path from LE to TE.
    mid = center.shape[1] // 2

    e_nose = raw_oml[0][:, -1, :]
    lower = raw_oml[1][:, -1, :]
    e_te = raw_oml[2][:, -1, :]
    upper = raw_oml[3][:, -1, :][::-1]

    v_mid = mid / (center.shape[1] - 1)
    ruled_camber = (1.0 - v_mid) * lower + v_mid * upper
    nose_ruled = (1.0 - v_mid) * lower[0] + v_mid * upper[0]
    te_ruled = (1.0 - v_mid) * lower[-1] + v_mid * upper[-1]
    chord_s = np.linspace(0.0, 1.0, len(lower))[:, None]
    expected_camber = (
        ruled_camber
        + (1.0 - chord_s) ** 8.0 * (e_nose[mid] - nose_ruled)
        + chord_s**8.0 * (e_te[mid] - te_ruled)
    )
    expected_camber[0] = e_nose[mid]
    expected_camber[-1] = e_te[mid]

    np.testing.assert_allclose(center[:, mid, :], expected_camber, atol=1.0e-12)


def test_surface_qc_rejects_negative_scaled_jacobian(monkeypatch):
    # Mocked regression for Stage 01 Variant B: folded tip cells must not pass QC.
    # The synthetic cap4 fixture does not reproduce the real BWB folding path,
    # so this test covers acceptance enforcement, not end-to-end geometry folding.
    import aeris.mesh.surface as surface_module

    original_block_qc = surface_module._block_qc

    def folded_tip_qc(block):
        metrics = dict(original_block_qc(block))
        if block.name == "tip_center_0":
            metrics["min_scaled_jacobian"] = -0.41913557355801423
        return metrics

    monkeypatch.setattr(surface_module, "_block_qc", folded_tip_qc)

    _blocks, report = build_surface_mesh(
        PyGeoSurfaceGeometry(sections=tuple(_sections(0.01, 1.0))),
        oml_topology="cap4",
        tip_topology="airfoil_face",
        points_per_block_side=25,
        cap_wrap_points=11,
        tip_radial_points=5,
        minimum_shape_metric=1.0e-8,
        spanwise_panels_per_section=1,
    )

    assert not report["accepted_pre_pyhyp"]
    assert report["global"]["min_scaled_jacobian"] < 0.0
    assert any(
        reason["check"] == "positive_scaled_jacobian" and reason["block"] == "tip_center_0"
        for reason in report["failure_reasons"]
    )


def test_build_surface_mesh_accepts_airfoil_face_tip_topology():
    geom = PyGeoSurfaceGeometry(sections=tuple(_sections(0.01, 1.0)))

    _blocks, report = build_surface_mesh(
        geom,
        oml_topology="cap4",
        tip_topology="airfoil_face",
        points_per_block_side=25,
        cap_wrap_points=11,
        tip_radial_points=5,
        minimum_shape_metric=1.0e-8,
        spanwise_panels_per_section=1,
    )

    assert report["accepted_pre_pyhyp"]
    assert report["tip_topology"] == "airfoil_face"
    assert report["tip_cap"]["topology"] == "single_block_full_airfoil_face_camber_row"
    assert not report["tip_cap"]["collar_ring"]
    assert report["tip_cap"]["center_block_count"] == 1
    assert report["tip_cap"]["camber_line_grid_row"]


def test_cap4_tip_topology_alias_resolves_to_airfoil_face():
    geom = PyGeoSurfaceGeometry(sections=tuple(_sections(0.01, 1.0)))

    _blocks, report = build_surface_mesh(
        geom,
        oml_topology="cap4",
        tip_topology="cap4",
        points_per_block_side=25,
        cap_wrap_points=11,
        tip_radial_points=5,
        minimum_shape_metric=1.0e-8,
        spanwise_panels_per_section=1,
    )

    assert report["accepted_pre_pyhyp"]
    assert report["tip_topology_requested"] == "cap4"
    assert report["tip_topology"] == "airfoil_face"
    assert "airfoil-face" in report["tip_topology_description"]
