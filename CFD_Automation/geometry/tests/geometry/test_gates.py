import copy

import numpy as np
import pytest

from cfdauto.geometry import gates, params
from cfdauto.geometry.measure import measure, table_from_stations
from cfdauto.geometry.planform import build_planform
from cfdauto.geometry.sections import Airfoil, Station, build_wing_sections

CFG = params.load_config()


def _wing(wing_type="bwb"):
    spec = CFG.types[wing_type]
    vec = params.mid_vector(spec)
    pf, st = build_wing_sections(spec, vec, CFG.te)
    return pf, st, measure(table_from_stations(st), st)


def test_exact_wing_passes_vector_and_te_gates():
    for t in params.WING_TYPES:
        pf, st, m = _wing(t)
        assert gates.vector_to_loft(m, pf, st).passed
        assert gates.vector_to_loft(m, pf, st, params.resolve(CFG.types[t], params.mid_vector(CFG.types[t]))).passed
        assert gates.trailing_edge(m, st, CFG.te).passed


@pytest.mark.parametrize("key,where,delta,word", [
    ("chord_m", "stations", 0.002, "chord"),
    ("twist_deg", "stations", 0.3, "twist"),
    ("sweep_le_deg", "panels", 0.2, "sweep"),
    ("dihedral_deg", "panels", 0.3, "dihedral"),
])
def test_vector_gate_refuses_drift(key, where, delta, word):
    pf, st, m = _wing()
    bad = copy.deepcopy(m)
    vals = bad[where][key]
    vals[1] = vals[1] * (1 + delta) if key == "chord_m" else vals[1] + delta
    g = gates.vector_to_loft(bad, pf, st)
    assert not g.passed and word in g.reason


def test_te_gate_refuses_wrong_thickness():
    _, st, m = _wing()
    bad = copy.deepcopy(m)
    bad["sections"][2]["te_thickness_m"] += 2e-6
    g = gates.trailing_edge(bad, st, CFG.te)
    assert not g.passed and "rule" in g.reason


def test_repeatability_gate():
    assert gates.repeatability("a", "a").passed
    assert not gates.repeatability("a", "b").passed


@pytest.mark.pygeo
def test_validity_gate():
    pytest.importorskip("pygeo")
    from cfdauto.geometry.loft import build_loft
    _, st, _ = _wing()
    assert gates.validity(build_loft(st), st).passed

    # swap upper and lower of the tip section: the surfaces cross
    tip = st[-1]
    flipped = Airfoil(tip.airfoil.name, tip.airfoil.x, tip.airfoil.yl, tip.airfoil.yu)
    bad = st[:-1] + [Station(tip.name, tip.y, tip.x_le, tip.z_le, tip.chord, tip.twist_deg, flipped)]
    g = gates.validity(build_loft(bad), bad)
    assert not g.passed and "cross" in g.reason

    # move the root off the symmetry plane
    r = st[0]
    off = [Station(r.name, 1e-6, r.x_le, r.z_le, r.chord, r.twist_deg, r.airfoil)] + st[1:]
    g = gates.validity(build_loft(off), off)
    assert not g.passed and "root" in g.reason


def test_vector_gate_refuses_wrong_aspect_ratio():
    spec = CFG.types["tapered"]
    vec = params.mid_vector(spec)
    pf, st = build_wing_sections(spec, vec, CFG.te)
    m = measure(table_from_stations(st), st)
    g = gates.vector_to_loft(m, pf, st, vec | {"aspect_ratio": vec["aspect_ratio"] * 1.01})
    assert not g.passed and "aspect ratio" in g.reason
