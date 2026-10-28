import numpy as np
import pytest
import yaml

from cfdauto.geometry import params
from cfdauto.geometry.sections import build_stations, build_wing_sections, load_airfoil, open_te

CFG = params.load_config()


def _vectors(wing_type, n=100, seed=1):
    spec = CFG.types[wing_type]
    rng = np.random.default_rng(seed)
    for _ in range(n):
        yield spec, params.from_unit(spec, dict(zip(spec.free_variables, rng.random(18))))


@pytest.mark.parametrize("wing_type", ["bwb", "conventional"])
def test_te_thickness_equals_rule_at_every_station(wing_type):
    for spec, vec in _vectors(wing_type):
        _, st = build_wing_sections(spec, vec, CFG.te)
        for s in st:
            built = s.airfoil.te_thickness * s.chord
            assert abs(built - CFG.te.thickness_m(s.chord)) < 1e-6   # 1 micron


@pytest.mark.parametrize("wing_type", ["bwb", "conventional"])
def test_camber_line_does_not_move(wing_type):
    for spec, vec in _vectors(wing_type, n=20):
        _, closed = build_stations(spec, vec)
        _, opened = build_wing_sections(spec, vec, CFG.te)
        opened = [s for s in opened if not s.name.startswith("te_switch")]
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


def test_switch_section_added_where_rule_changes():
    spec = CFG.types["conventional"]
    # root 0.4 m -> 0.2 m tip: the 0.25 m switch chord falls inside a panel
    vec = params.mid_vector(spec) | {"root_chord_m": 0.4, "c2_ratio": 1.0, "c3_ratio": 0.9, "c4_ratio": 0.5}
    _, st = build_wing_sections(spec, vec, CFG.te)
    sw = [s for s in st if s.name.startswith("te_switch")]
    assert len(sw) == 1
    assert sw[0].chord == pytest.approx(CFG.te.switch_chord_m())
    ys = [s.y for s in st]
    assert ys == sorted(ys)


def test_no_switch_section_when_rule_does_not_change():
    spec = CFG.types["bwb"]
    vec = params.mid_vector(spec) | {"root_chord_m": 0.9, "c4_ratio": 0.3}  # all chords > 0.25 m
    _, st = build_wing_sections(spec, vec, CFG.te)
    assert [s.name for s in st] == ["b0", "b1", "b2", "b3"]


def test_class_ii_floor(tmp_path):
    raw = yaml.safe_load(params.DEFAULT_CONFIG.read_text())
    raw["wing_class"] = "II"
    p = tmp_path / "wing.yaml"
    p.write_text(yaml.safe_dump(raw))
    cfg = params.load_config(p)
    assert cfg.te.thickness_m(0.2) == pytest.approx(0.001)
    assert cfg.te.switch_chord_m() == pytest.approx(0.5)
