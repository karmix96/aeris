import pytest
import yaml

from cfdauto.geometry import params


def test_config_loads_both_types():
    cfg = params.load_config()
    assert set(cfg.types) == set(params.WING_TYPES) == {"bwb", "cranked", "tapered", "flying_wing"}
    assert len(params.VARIABLES) == 17 and "root_chord_m" not in params.VARIABLES    # decision 70
    for spec in cfg.types.values():
        assert set(spec.ranges) == set(params.VARIABLES)
        # everything varies by default, except what a law computes
        assert spec.free_variables == tuple(v for v in params.VARIABLES if v not in spec.derived)


def test_same_variable_list_for_every_type():
    cfg = params.load_config()
    assert list(cfg.types["bwb"].ranges) == list(cfg.types["cranked"].ranges)


def test_forward_sweep_allowed_by_ranges():
    cfg = params.load_config()
    spec = cfg.types["cranked"]
    assert spec.ranges["sweep2_deg"][0] < 0
    vec = params.from_unit(spec, {"sweep2_deg": 0.0})
    assert vec["sweep2_deg"] < 0


def test_te_rule_is_a_chord_fraction():
    """Decision 70: 0.2 % of the local chord on every wing (no mm floor, no wing class)."""
    cfg = params.load_config()
    assert not hasattr(cfg, "wing_class") and not hasattr(cfg.te, "floor_m")
    assert cfg.te.thickness_m(0.10) == pytest.approx(0.0002)
    assert cfg.te.thickness_m(1.00) == pytest.approx(0.0020)


def _write(tmp_path, raw):
    p = tmp_path / "wing.yaml"
    p.write_text(yaml.safe_dump(raw))
    return p


@pytest.mark.parametrize("edit", [
    lambda raw: raw.update(wing_class="I"),
    lambda raw: raw.update(focus={"max_full_span_m": 7.0}),
    lambda raw: raw["trailing_edge"].update(floor_m={"I": 0.0005, "II": 0.0010}),
    lambda raw: raw["types"]["bwb"]["ranges"].update(root_chord_m=[0.4, 1.8]),
])
def test_sizes_of_the_first_approach_are_refused(tmp_path, edit):
    """A config with a size (wing class, span cap, mm floor, root chord) is refused, not misread."""
    raw = yaml.safe_load(params.DEFAULT_CONFIG.read_text())
    edit(raw)
    with pytest.raises(ValueError):
        params.load_config(_write(tmp_path, raw))


def test_pinned_and_linear_taper(tmp_path):
    raw = yaml.safe_load(params.DEFAULT_CONFIG.read_text())
    raw["types"]["cranked"]["pinned"] = {"dihedral_p1_deg": 2.0}
    raw["types"]["cranked"]["chord_law"] = "linear_taper"
    cfg = params.load_config(_write(tmp_path, raw))
    spec = cfg.types["cranked"]
    assert "dihedral_p1_deg" not in spec.free_variables
    assert "c2_ratio" not in spec.free_variables
    vec = params.mid_vector(spec)
    assert vec["dihedral_p1_deg"] == 2.0
    # chord linear in span: c3 sits on the line from 1 to c4
    y2 = 1.0 - vec["b3_ratio"]
    assert vec["c3_ratio"] == pytest.approx(1.0 + (vec["c4_ratio"] - 1.0) * y2)


@pytest.mark.parametrize("key,value", [
    ("wing_type", "box"),
])
def test_bad_top_level_values_refused(tmp_path, key, value):
    raw = yaml.safe_load(params.DEFAULT_CONFIG.read_text())
    raw[key] = value
    with pytest.raises(ValueError):
        params.load_config(_write(tmp_path, raw))


def test_bad_range_refused(tmp_path):
    raw = yaml.safe_load(params.DEFAULT_CONFIG.read_text())
    raw["types"]["bwb"]["ranges"]["c2_ratio"] = [0.9, 0.5]
    with pytest.raises(ValueError):
        params.load_config(_write(tmp_path, raw))


def test_unknown_airfoil_refused(tmp_path):
    raw = yaml.safe_load(params.DEFAULT_CONFIG.read_text())
    raw["types"]["bwb"]["airfoils"][0] = "not_an_airfoil"
    with pytest.raises(ValueError):
        params.load_config(_write(tmp_path, raw))


def test_canonical_is_order_free():
    spec = params.load_config().types["bwb"]
    vec = params.mid_vector(spec)
    rev = dict(reversed(list(vec.items())))
    assert params.canonical(vec) == params.canonical(rev)


def test_missing_variable_refused():
    spec = params.load_config().types["bwb"]
    vec = params.mid_vector(spec)
    del vec["sweep1_deg"]
    with pytest.raises(ValueError):
        params.resolve(spec, vec)


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_aspect_ratio_is_an_input_and_the_span_follows(wing_type):
    from cfdauto.geometry.planform import aspect_ratio, build_planform
    spec = params.load_config().types[wing_type]
    assert spec.span_mode == "aspect_ratio" and "semi_span_m" in spec.derived
    for u in (0.0, 0.5, 1.0):
        vec = params.from_unit(spec, {"aspect_ratio": u})
        pf = build_planform(spec, vec)
        assert aspect_ratio(pf) == pytest.approx(vec["aspect_ratio"], rel=1e-12)
        # decision 70: unit mean chord (area / span = 1), so the semi-span is AR / 2 mean chords
        assert pf.area() / (2 * pf.semi_span) == pytest.approx(1.0, rel=1e-12)
        assert pf.semi_span == pytest.approx(vec["aspect_ratio"] / 2, rel=1e-12)
