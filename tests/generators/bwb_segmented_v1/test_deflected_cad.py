from types import SimpleNamespace

import numpy as np
import pytest

from aeris.generators.bwb_segmented_v1.deflected_cad import (
    PhysicalDeflectionSpec,
    build_piecewise_abrupt_sections,
    deflect_control_airfoil_coordinates,
    split_airfoil_at_hinge,
)


def test_physical_deflection_right_left_mapping():
    spec = PhysicalDeflectionSpec(delta_e_sym_deg=2.0, delta_a_diff_deg=15.0)
    assert spec.right_deflection_deg == pytest.approx(17.0)
    assert spec.left_deflection_deg == pytest.approx(-13.0)


def test_deflect_control_coordinates_rotates_aft_piece():
    coords = np.array([[0.75, 0.0], [1.0, 0.0], [1.0, -0.02], [0.75, 0.0]])
    out = deflect_control_airfoil_coordinates(coords, hinge_point=0.75, deflection_deg=10.0)
    assert out.shape == coords.shape
    assert out[1, 1] < coords[1, 1]  # positive TE-down => negative local y


def test_split_airfoil_at_hinge_returns_two_closed_like_loops():
    class AF:
        name = "toy"
        coordinates = np.array([
            [1.0, 0.0],
            [0.5, 0.08],
            [0.0, 0.0],
            [0.5, -0.04],
            [1.0, 0.0],
        ])

    fixed, ctrl = split_airfoil_at_hinge(AF(), hinge_point=0.75, gap_fraction=0.02)
    assert fixed.shape[1] == 2
    assert ctrl.shape[1] == 2
    assert fixed[:, 0].max() < ctrl[:, 0].min()


def test_piecewise_abrupt_sections_insert_boundary_stations():
    sections = [
        SimpleNamespace(index=i, x_le_m=0.1 * i, y_m=0.1 * i, z_le_m=0.0, chord_m=1.0 - 0.02 * i, twist_deg=0.0, dihedral_deg=0.0, airfoil_name="naca4412")
        for i in range(11)
    ]
    spec = PhysicalDeflectionSpec(start_frac=0.60, end_frac=0.90, boundary_epsilon_fraction=1e-3)
    piecewise, report = build_piecewise_abrupt_sections(sections, spec)
    ys = [abs(s.y_m) for s in piecewise]
    assert len(piecewise) > len(sections)
    assert report["n_piecewise_sections"] == len(piecewise)
    y_start = report["y_start_m"]
    eps = report["boundary_epsilon_m"]
    assert any(abs(y - (y_start - eps)) < eps * 0.1 for y in ys)
    assert any(abs(y - (y_start + eps)) < eps * 0.1 for y in ys)
