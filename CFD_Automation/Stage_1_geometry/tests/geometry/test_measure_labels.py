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
    if "span_mode" in base:      # the vectors give the semi-span in root chords
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
        assert got[0] in params.FAMILIES and got[1] in params.FAMILIES[got[0]]
        assert sum(t in got for t in ("tailless", "conventional")) == 1


@pytest.mark.pygeo
def test_hand_labelled_on_the_loft():
    pytest.importorskip("pygeo")
    from cfdauto.geometry.loft import build_loft
    from cfdauto.geometry.measure import table_from_loft
    for name in HAND["wings"]:
        spec, vec, want = hand_wing(name)
        m_exact, st = exact_measure(spec, vec)
        m_loft = measure(table_from_loft(build_loft(st)), st)
        tl = base_type(name) in params.TAILLESS_TYPES
        assert set(label(m_loft, tailless=tl)[0]) == set(want), name
        assert m_loft["area_m2"] == pytest.approx(m_exact["area_m2"], rel=1e-9)
        assert m_loft["max_thickness_c"] == pytest.approx(m_exact["max_thickness_c"], rel=2e-3)


def test_tailless_without_centre_body_is_a_flying_wing():
    spec = CFG.types["flying_wing"]
    got, _ = label(exact_measure(spec, params.mid_vector(spec))[0], tailless=True)
    assert got[:2] == ["tailless", "flying_wing"]
    # the same planform with a tail is conventional; straight edges make it 'tapered'
    got, _ = label(exact_measure(spec, params.mid_vector(spec))[0], tailless=False)
    assert got[:2] == ["conventional", "tapered"]


def test_type_rules_inside_each_family():
    """Every training wing of a type is classified back to its own type, except where noted."""
    from cfdauto.geometry.sample import lhs
    for t in params.WING_TYPES:
        spec = CFG.types[t]
        got = [label(exact_measure(spec, v)[0], tailless=t in params.TAILLESS_TYPES)[0][1] for v in lhs(spec, 40, 7)]
        share = got.count(t) / len(got)
        assert share >= (0.75 if t in ("bwb", "flying_wing") else 0.95), (t, share)


def test_value_exactly_at_a_threshold_gets_the_label():
    """Decision 79 (8 Nov 2026): a designed value exactly at a threshold gets the label on the built loft.

    BWB corner1 #8 changes its leading-edge sweep by exactly 5 deg (35 -> 30), the kink threshold: the numpy loft
    measured 4.999999999999993 deg and pyGeo 5 or more, so the two lofts gave different labels. Flying-wing
    reference #0 is designed at AR exactly 8 and measured 7.99999998 (area error), so it missed high_aspect_ratio."""
    from cfdauto.geometry.build import build
    bwb = {"c2_ratio": 0.675, "c3_ratio": 0.375, "c4_ratio": 0.145, "semi_span_m": 3.125, "aspect_ratio": 6.25,
           "b3_ratio": 0.3, "split_ratio": 0.5, "sweep1_deg": 35.0, "sweep2_deg": 35.0, "sweep3_deg": 30.0,
           "twist0_deg": 2.0, "twist1_deg": 0.0, "twist2_deg": 0.0, "twist3_deg": -1.5, "dihedral_p1_deg": 0.0,
           "dihedral_p2_deg": 0.0, "dihedral_p3_deg": 0.0, "airfoils": ["mh104", "mh104", "mh61", "mh61"]}
    assert "cranked" in build(bwb, "bwb", CFG, iges=False)["labels"]
    fw = {"c2_ratio": 0.87, "c3_ratio": 0.74, "c4_ratio": 0.6, "semi_span_m": 4.0, "aspect_ratio": 8.0,
          "b3_ratio": 0.35, "split_ratio": 0.5, "sweep1_deg": 25.0, "sweep2_deg": 25.0, "sweep3_deg": 25.0,
          "twist0_deg": 0.5, "twist1_deg": -0.5, "twist2_deg": -2.0, "twist3_deg": -3.5, "dihedral_p1_deg": 2.5,
          "dihedral_p2_deg": 2.5, "dihedral_p3_deg": 2.5, "airfoils": ["mh60", "mh60", "mh45", "mh45"]}
    assert "high_aspect_ratio" in build(fw, "flying_wing", CFG, iges=False)["labels"]
