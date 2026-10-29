import numpy as np
import pytest

from cfdauto.geometry import params
from cfdauto.geometry.sections import build_stations, load_airfoil, panel_dihedral_deg, panel_z

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


def test_panel_z_gives_the_panel_dihedral_exactly():
    y = np.array([0.0, 0.4, 1.1, 1.5])
    d = np.array([2.0, -3.0, 7.5])
    z = panel_z(y, d)
    assert z[0] == 0.0
    assert panel_dihedral_deg(y, z) == pytest.approx(d, abs=1e-12)


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_dihedral_is_three_panel_values_and_each_matters(wing_type):
    spec = params.load_config().types[wing_type]
    vec = params.mid_vector(spec)
    assert [k for k in params.VARIABLES if k.startswith("dihedral")] == \
        ["dihedral_p1_deg", "dihedral_p2_deg", "dihedral_p3_deg"]
    _, st0 = build_stations(spec, vec)
    for k in ("dihedral_p1_deg", "dihedral_p2_deg", "dihedral_p3_deg"):
        _, st1 = build_stations(spec, vec | {k: vec[k] + 1.0})
        assert st1[-1].z_le != pytest.approx(st0[-1].z_le)      # no input is without effect


def test_root_section_stays_in_symmetry_plane_with_root_dihedral():
    spec = params.load_config().types["conventional"]
    vec = params.mid_vector(spec) | {"dihedral_p1_deg": 6.0}
    _, st = build_stations(spec, vec)
    assert st[0].y == 0.0 and st[0].z_le == 0.0
    y = np.array([s.y for s in st]); z = np.array([s.z_le for s in st])
    assert panel_dihedral_deg(y, z)[0] == pytest.approx(6.0)
    # sections are vertical: every point of the root section lies in y = 0
    from cfdauto.geometry.loft import section_points
    up, lo = section_points(st[0])
    assert np.max(np.abs(np.concatenate([up, lo])[:, 1])) == 0.0


def test_stations_carry_vector_twist_and_airfoils():
    spec = params.load_config().types["bwb"]
    vec = params.mid_vector(spec)
    _, st = build_stations(spec, vec)
    assert [s.twist_deg for s in st] == [vec[f"twist{i}_deg"] for i in range(4)]
    assert [s.airfoil.name for s in st] == list(spec.airfoils)
