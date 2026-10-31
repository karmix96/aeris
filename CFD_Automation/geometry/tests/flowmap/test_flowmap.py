import shutil

import pytest

from cfdauto.flowmap.core import band, flow_map, rho_over_mu, strips
from cfdauto.geometry import params
from cfdauto.geometry.sections import build_stations

CFG = params.load_config()


def test_air_and_bands():
    assert rho_over_mu(0) == 68500 and rho_over_mu(3048) == 53500
    assert band(5e4)[0] == "below 10⁵" and band(2e6)[0] == "5 × 10⁵ – 3 × 10⁶"


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_strips_cover_root_breaks_and_tip(wing_type):
    spec = CFG.types[wing_type]
    pf, st = build_stations(spec, params.mid_vector(spec))
    ys = [s["y"] for s in strips(pf, st)]
    assert ys[0] == 0.0 and ys[-1] == pytest.approx(0.97 * pf.semi_span)
    for b in pf.y[1:3]:
        assert min(abs(y - b) for y in ys) < 1e-9


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_family_and_type_without_xfoil(wing_type):
    spec = CFG.types[wing_type]
    fm = flow_map(spec, params.mid_vector(spec), wing_type in params.TAILLESS_TYPES, 25.0, 1000.0, 3.0, run_xfoil=False)
    assert fm["family"] == params.FAMILY_OF[wing_type]
    assert fm["type"] in params.FAMILIES[fm["family"]]
    re_ = [r["re"] for r in fm["strips"]]
    assert re_[0] == pytest.approx(rho_over_mu(1000.0) * 25.0 * fm["geometry"]["root_chord_m"])
    assert fm["model"]["model"]


@pytest.mark.skipif(shutil.which("xfoil") is None, reason="xfoil not installed")
def test_xfoil_strip_gives_transition():
    spec = CFG.types["tapered"]
    fm = flow_map(spec, params.mid_vector(spec), False, 20.0, 0.0, 3.0)
    assert any(r.get("xtr_upper") for r in fm["strips"])
