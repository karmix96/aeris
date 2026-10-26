import numpy as np
import pytest

from cfdauto.geometry import params
from cfdauto.geometry.sections import (
    build_stations, load_airfoil, panel_dihedral_deg, segment_z_integral, station_z,
)

AIRFOILS = ["mh91", "e374", "nlf1015", "naca4415", "naca4412"]


@pytest.mark.parametrize("name", AIRFOILS)
def test_airfoil_normalised(name):
    a = load_airfoil(name)
    assert a.x[0] == 0 and a.x[-1] == pytest.approx(1.0)
    assert a.yu[0] == pytest.approx(0.0, abs=1e-12) and a.yl[0] == pytest.approx(0.0, abs=1e-12)
    assert a.camber[-1] == pytest.approx(0.0, abs=1e-9)          # TE midpoint on the chord line
    assert np.all(a.thickness[1:-1] > 0)                           # surfaces never cross
    assert 0.08 < a.thickness.max() < 0.20


def test_airfoil_thickness_matches_name():
    assert load_airfoil("naca4415").thickness.max() == pytest.approx(0.15, abs=0.003)
    assert load_airfoil("naca4412").thickness.max() == pytest.approx(0.12, abs=0.003)


def test_z_integral_constant_and_linear():
    d = np.radians(5.0)
    assert segment_z_integral(0, 2, d, d) == pytest.approx(2 * np.tan(d))
    # linear dihedral: compare with a fine numerical integral
    d0, d1 = np.radians(0.0), np.radians(10.0)
    s = np.linspace(0, 1.5, 200001)
    num = np.trapezoid(np.tan(d0 + (d1 - d0) * s / 1.5), s)
    assert segment_z_integral(0, 1.5, d0, d1) == pytest.approx(num, rel=1e-9)


def test_z_independent_of_station_split():
    # adding a station on the linear dihedral line must not move the tip
    y = np.array([0.0, 1.0, 2.0])
    d = np.array([0.0, 4.0, 8.0])
    z2 = station_z(np.array([0.0, 2.0]), np.array([0.0, 8.0]))
    assert station_z(y, d)[-1] == pytest.approx(z2[-1], rel=1e-12)


def test_root_section_stays_in_symmetry_plane_with_root_dihedral():
    spec = params.load_config().types["conventional"]
    vec = params.mid_vector(spec) | {"dihedral0_deg": 6.0, "dihedral1_deg": 6.0}
    _, st = build_stations(spec, vec)
    assert st[0].y == 0.0 and st[0].z_le == 0.0
    # with constant 6 deg dihedral, the first panel rises at 6 deg
    y = np.array([s.y for s in st]); z = np.array([s.z_le for s in st])
    assert panel_dihedral_deg(y, z)[0] == pytest.approx(6.0)


def test_stations_carry_vector_twist_and_airfoils():
    spec = params.load_config().types["bwb"]
    vec = params.mid_vector(spec)
    _, st = build_stations(spec, vec)
    assert [s.twist_deg for s in st] == [vec[f"twist{i}_deg"] for i in range(4)]
    assert [s.airfoil.name for s in st] == list(spec.airfoils)
