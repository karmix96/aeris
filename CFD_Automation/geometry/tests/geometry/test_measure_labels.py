import dataclasses
from pathlib import Path

import numpy as np
import pytest
import yaml

from cfdauto.geometry import params
from cfdauto.geometry.labels import label
from cfdauto.geometry.measure import measure, table_from_stations
from cfdauto.geometry.planform import aspect_ratio, mean_aero_chord
from cfdauto.geometry.sections import build_wing_sections

CFG = params.load_config()
HAND = yaml.safe_load((Path(__file__).parent / "hand_labelled.yaml").read_text())


def hand_wing(name):
    w = HAND["wings"][name]
    base = HAND["bases"][w["base"]]
    spec = CFG.types[base["type"]]
    if "chord_law" in base:      # the vectors are written as fractions of the root chord
        spec = dataclasses.replace(spec, chord_law=base["chord_law"])
    if "span_mode" in base:      # the vectors give the semi-span in metres
        spec = dataclasses.replace(spec, span_mode=base["span_mode"])
    vec = params.mid_vector(spec) if base["vector"] == "mid" else dict(base["vector"])
    vec |= {k: float(v) for k, v in (w.get("set") or {}).items()}
    return spec, vec, w["labels"]


def base_type(name):
    return HAND["bases"][HAND["wings"][name]["base"]]["type"]


def exact_measure(spec, vec):
    _, st = build_wing_sections(spec, vec, CFG.te)
    return measure(table_from_stations(st), st), st


def test_hand_set_has_about_20_wings():
    assert len(HAND["wings"]) >= 20


@pytest.mark.parametrize("name", list(HAND["wings"]))
def test_hand_labelled(name):
    spec, vec, want = hand_wing(name)
    got, _ = label(exact_measure(spec, vec)[0], tailless=base_type(name) in params.TAILLESS_TYPES)
    assert set(got) == set(want)


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_measured_matches_planform(wing_type):
    from cfdauto.geometry.planform import build_planform
    spec = CFG.types[wing_type]
    vec = params.mid_vector(spec)
    m, st = exact_measure(spec, vec)
    pf = build_planform(spec, vec)
    assert np.allclose(m["stations"]["chord_m"], pf.chord, rtol=1e-12)
    assert np.allclose(m["panels"]["sweep_le_deg"], pf.sweep_le_deg, atol=1e-9)
    assert m["area_m2"] == pytest.approx(pf.area(), rel=1e-3)        # twist shortens projected chord slightly
    assert m["mac_m"] == pytest.approx(mean_aero_chord(pf), rel=1e-3)
    assert m["aspect_ratio"] == pytest.approx(aspect_ratio(pf), rel=1e-3)
    assert [s["te_thickness_m"] for s in m["sections"]] == pytest.approx(
        [CFG.te.thickness_m(s.chord) for s in st], abs=1e-9)


def test_every_wing_has_exactly_one_type_label():
    for name in HAND["wings"]:
        got, _ = label(exact_measure(*hand_wing(name)[:2])[0], tailless=base_type(name) in params.TAILLESS_TYPES)
        assert sum(t in got for t in ("bwb", "flying_wing", "conventional")) == 1


@pytest.mark.pygeo
def test_hand_labelled_on_the_loft():
    pytest.importorskip("pygeo")
    from cfdauto.geometry.loft import build_loft
    from cfdauto.geometry.measure import table_from_loft
    for name in HAND["wings"]:
        spec, vec, want = hand_wing(name)
        m_exact, st = exact_measure(spec, vec)
        m_loft = measure(table_from_loft(build_loft(st)), st)
        assert set(label(m_loft)[0]) == set(want), name
        assert m_loft["area_m2"] == pytest.approx(m_exact["area_m2"], rel=1e-9)
        assert m_loft["max_thickness_c"] == pytest.approx(m_exact["max_thickness_c"], rel=2e-3)


def test_tailless_without_centre_body_is_a_flying_wing():
    spec = CFG.types["flying_wing"]
    got, _ = label(exact_measure(spec, params.mid_vector(spec))[0], tailless=True)
    assert got[0] == "flying_wing"
    # the same planform on a type with a tail is 'conventional'
    got, _ = label(exact_measure(spec, params.mid_vector(spec))[0], tailless=False)
    assert got[0] == "conventional"
