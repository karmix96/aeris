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
    _oml_source_for,
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
    upper = np.column_stack([x[::-1], z[::-1]])       # TE -> LE
    lower = np.column_stack([x[1:], -z[1:]])          # LE -> TE
    return np.vstack([upper, lower])


def _params(**over) -> OmlTopologyParams:
    base = dict(oml_topology="cap4", points_per_block_side=25, cap_wrap_points=11,
                cap_wrap_x=0.15, split_x_fore=0.20, dense_airfoil_points_per_surface=201,
                minimum_te_thickness=2.0e-3, te_thickness=0.005, te_thickness_abs_floor=0.0,
                te_base_points=0, chordwise_distribution="junction", chordwise_beta=2.0)
    base.update(over)
    return OmlTopologyParams(**base)


def _sections(te: float, chord: float, le=(1.0, 2.0, 3.0)) -> list[_FakeSection]:
    loop = _airfoil_loop(te)
    return [
        _FakeSection(loop.copy(), chord, np.array([le[0], y, le[2]]),
                    np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]))
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
            _params(te_thickness=0.0, te_thickness_abs_floor=floor))
        return float(np.ptp(blocks[2][:, 0, 2]))  # z-extent of the TE-wrap block

    assert te_wrap_zext(0.004) > 1.2 * te_wrap_zext(0.0)
