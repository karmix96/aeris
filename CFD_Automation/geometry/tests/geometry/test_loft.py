import numpy as np
import pytest

from cfdauto.geometry import params
from cfdauto.geometry.sections import build_wing_sections

pytestmark = pytest.mark.pygeo
pytest.importorskip("pygeo")
pytest.importorskip("pyspline")

from cfdauto.geometry.loft import build_loft, edge_error_pct, section_points  # noqa: E402

CFG = params.load_config()


def three_wings():
    bwb = CFG.types["bwb"]
    conv = CFG.types["conventional"]
    return {
        "bwb_mid": (bwb, params.mid_vector(bwb)),
        # biggest sweep change between panels the BWB ranges allow: 40 -> 15 -> 25 deg
        "sweep_change": (bwb, params.mid_vector(bwb) | {"sweep1_deg": 40.0, "sweep2_deg": 15.0, "sweep3_deg": 25.0}),
        # biggest panel-dihedral change: stations -3 / -3 / +6 / +6 deg -> panels -3, ~1.5, +6 deg
        "dihedral_change": (conv, params.mid_vector(conv) | {
            "dihedral0_deg": -3.0, "dihedral1_deg": -3.0, "dihedral2_deg": 6.0, "dihedral3_deg": 6.0}),
    }


@pytest.fixture(scope="module")
def lofts():
    out = {}
    for name, (spec, vec) in three_wings().items():
        _, st = build_wing_sections(spec, vec, CFG.te)
        out[name] = (st, build_loft(st, k_span=2))
    return out


@pytest.mark.parametrize("name", list(three_wings()))
def test_edges_match_exact_planform(lofts, name):
    st, loft = lofts[name]
    err = edge_error_pct(loft, st)
    assert err["le_max_pct"] < 0.01 and err["te_max_pct"] < 0.01


@pytest.mark.parametrize("name", list(three_wings()))
def test_loft_passes_through_every_section_point(lofts, name):
    st, loft = lofts[name]
    for s, v in zip(st, loft.station_v):
        up, lo = section_points(s)
        x = s.airfoil.x
        assert np.max(np.abs(loft.upper(x, np.full_like(x, v)) - up)) < 1e-12
        assert np.max(np.abs(loft.lower(x, np.full_like(x, v)) - lo)) < 1e-12


def test_upper_above_lower_and_nose_shared(lofts):
    st, loft = lofts["bwb_mid"]
    for v in np.linspace(0, 1, 21):
        assert np.allclose(loft.upper(0.0, v), loft.lower(0.0, v), atol=1e-12)
        assert loft.upper(0.3, v)[2] > loft.lower(0.3, v)[2]


def test_twist_is_nose_up(lofts):
    st, loft = lofts["bwb_mid"]
    root = st[0]
    tip_te = loft.te_mid(0.0)
    expect_z = root.z_le - root.chord * np.sin(np.radians(root.twist_deg))
    assert tip_te[2] == pytest.approx(expect_z, abs=1e-12)


def test_root_section_in_symmetry_plane(lofts):
    st, loft = lofts["dihedral_change"]
    u = np.linspace(0, 1, 101)
    assert np.max(np.abs(loft.upper(u, np.zeros_like(u))[:, 1])) < 1e-12
    assert np.max(np.abs(loft.lower(u, np.zeros_like(u))[:, 1])) < 1e-12


def test_trailing_edge_on_loft_equals_rule(lofts):
    for st, loft in lofts.values():
        for s, v in zip(st, loft.station_v):
            gap = np.linalg.norm(loft.upper(1.0, v) - loft.lower(1.0, v))
            assert abs(gap - CFG.te.thickness_m(s.chord)) < 1e-6


def test_span_table(lofts):
    st, loft = lofts["bwb_mid"]
    tab = loft.span_table()
    assert tab.shape == (401, 2)
    assert tab[0, 1] == pytest.approx(0.0, abs=1e-12) and tab[-1, 1] == pytest.approx(st[-1].y)
    assert np.all(np.diff(tab[:, 1]) > 0)


def test_iges_export(lofts, tmp_path):
    _, loft = lofts["bwb_mid"]
    p = tmp_path / "wing.igs"
    loft.write_iges(p)
    assert p.stat().st_size > 10_000


def test_kspan3_overshoots(lofts):
    st, _ = lofts["sweep_change"]
    err3 = edge_error_pct(build_loft(st, k_span=3), st)
    assert err3["le_max_pct"] > 0.01   # quadratic span splines leave the straight panels
