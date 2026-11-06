import numpy as np
import pytest

from cfdauto.geometry import params
from cfdauto.geometry.sections import build_stations, build_wing_sections, load_airfoil, open_te

CFG = params.load_config()


def _vectors(wing_type, n=100, seed=1):
    spec = CFG.types[wing_type]
    rng = np.random.default_rng(seed)
    for _ in range(n):
        yield spec, params.from_unit(spec, dict(zip(spec.free_variables, rng.random(len(spec.free_variables)))))


@pytest.mark.parametrize("wing_type", ["bwb", "cranked"])
def test_te_thickness_equals_rule_at_every_station(wing_type):
    for spec, vec in _vectors(wing_type):
        _, st = build_wing_sections(spec, vec, CFG.te)
        for s in st:
            built = s.airfoil.te_thickness * s.chord
            assert abs(built - CFG.te.thickness_m(s.chord)) < 1e-6   # 1e-6 mean chords


@pytest.mark.parametrize("wing_type", ["bwb", "cranked"])
def test_camber_line_does_not_move(wing_type):
    for spec, vec in _vectors(wing_type, n=20):
        _, closed = build_stations(spec, vec)
        _, opened = build_wing_sections(spec, vec, CFG.te)
        for a, b in zip(closed, opened):
            assert np.max(np.abs(a.airfoil.camber - b.airfoil.camber)) < 1e-6


def test_nose_untouched_and_ramp_linear():
    a = load_airfoil("mh91")
    b = open_te(a, 0.004, 0.9)
    ahead = a.x <= 0.9
    aft = ~ahead
    # pyGeo's ramp: the added thickness is linear in x from 0.9 to the edge
    added = (b.thickness - a.thickness)[aft]
    want = (0.004 - a.te_thickness) * (a.x[aft] - 0.9) / 0.1
    assert np.allclose(added, want, atol=1e-15)
    assert np.array_equal(a.yu[ahead], b.yu[ahead]) and np.array_equal(a.yl[ahead], b.yl[ahead])
    assert b.te_thickness == pytest.approx(0.004)
    assert np.all(b.thickness[1:] > 0)


def test_already_thick_edge_is_thinned_to_rule():
    a = load_airfoil("naca4415")          # file has a 0.3 % chord blunt edge
    assert a.te_thickness > 0.002
    assert open_te(a, 0.002, 0.9).te_thickness == pytest.approx(0.002)


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_edge_is_the_chord_fraction_all_along_the_span(wing_type):
    """Decision 70: 0.2 % of the local chord everywhere, so no section is added (the first rule's mm floor
    needed a switch section), and between the stations the ruled loft keeps the fraction, twist or not."""
    from cfdauto.geometry.measure import table_from_stations
    spec = CFG.types[wing_type]
    for vec in (params.mid_vector(spec), params.from_unit(spec, {v: 1.0 for v in spec.free_variables})):
        _, st = build_wing_sections(spec, vec, CFG.te)
        assert [s.name for s in st] == ["b0", "b1", "b2", "b3"]
        tab = table_from_stations(st)
        assert np.max(np.abs(tab["te_thickness"] / tab["chord"] - CFG.te.chord_fraction)) < 1e-12
