"""Focused tests for the standalone pyGeo/AVL bridge."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from standalone.pygeo_avl_study.geometry_bridge import (
    StationDefinition,
    build_pygeo,
    extract_sections,
    pygeo_frame_inputs,
)
from standalone.pygeo_avl_study.polar_bridge import (
    SectionAirfoilMap,
    cdcl_bucket_cd,
)
from aeris.airfoil.polar_store import CdclParams


ROOT = Path(__file__).resolve().parents[2]
NACA0012 = ROOT / "data/airfoil_database/naca0012.dat"


def _stations() -> list[StationDefinition]:
    return [
        StationDefinition(0, 0.00, 0.00, 0.000, 1.20, 0.0, 0.0, "naca0012", NACA0012),
        StationDefinition(1, 0.12, 0.35, 0.010, 0.92, -1.5, 2.0, "naca0012", NACA0012),
        StationDefinition(2, 0.42, 1.00, 0.070, 0.35, -4.0, 5.0, "naca0012", NACA0012),
    ]


def test_exact_asb_frame_euler_reconstruction() -> None:
    *_, error = pygeo_frame_inputs(_stations(), "asb_frame")
    assert error < 1.0e-12


def test_extracts_valid_sections_and_endpoint_chords() -> None:
    stations = _stations()
    build = build_pygeo(stations, k_span=2, frame_mode="asb_frame", tip="none")
    sections = extract_sections(
        build,
        np.array([0.0, 0.35, 1.0]),
        cst_order=8,
        chordwise_points=121,
    )
    assert len(sections) == 3
    assert all(section.cst_valid for section in sections)
    assert max(section.cst_rms_chord for section in sections) < 1.0e-3
    assert np.isclose(sections[0].chord_m, stations[0].chord_m, rtol=2.0e-4)
    assert np.isclose(sections[-1].chord_m, stations[-1].chord_m, rtol=2.0e-4)


def test_physical_span_inversion_is_respected() -> None:
    build = build_pygeo(_stations(), k_span=3, frame_mode="asb_frame", tip="none")
    fractions = np.linspace(0.0, 1.0, 7)
    sections = extract_sections(build, fractions, cst_order=8, chordwise_points=101)
    y = np.asarray([section.y_m for section in sections])
    realised = (y - y[0]) / (y[-1] - y[0])
    assert np.max(np.abs(realised - fractions)) < 2.0e-4


def test_section_map_uses_nearest_realised_section() -> None:
    coordinates = [
        np.array([[1.0, 0.0], [0.0, 0.0], [1.0, 0.0]]),
        np.array([[1.0, 0.1], [0.0, 0.0], [1.0, -0.1]]),
    ]
    mapping = SectionAirfoilMap([0.0, 1.0], ["root", "tip"], coordinates)
    assert mapping.get_airfoil_id(0.2) == "root"
    assert mapping.get_airfoil_id(0.8) == "tip"


def test_cdcl_bucket_passes_through_three_points() -> None:
    params = CdclParams(-0.5, 0.020, 0.2, 0.006, 1.1, 0.018)
    predicted = cdcl_bucket_cd(
        params,
        np.array([params.cl1, params.cl2, params.cl3]),
    )
    assert np.allclose(predicted, [params.cd1, params.cd2, params.cd3])
