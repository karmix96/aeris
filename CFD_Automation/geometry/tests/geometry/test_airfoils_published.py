"""Airfoils from the AERIS database and NACA formulas; the published wings."""

import numpy as np
import pytest

from cfdauto.geometry import airfoils, gates, params, published_wings
from cfdauto.geometry.measure import measure, table_from_stations
from cfdauto.geometry.planform import aspect_ratio, mean_aero_chord
from cfdauto.geometry.sample import lhs
from cfdauto.geometry.sections import build_stations, build_wing_sections, load_airfoil

needs_db = pytest.mark.skipif(not airfoils.AERIS_DB.is_dir(), reason="AERIS airfoil database not found")


def _surfaces(pts, x):
    i = int(np.argmin(pts[:, 0]))
    up, lo = pts[: i + 1][::-1], pts[i:]
    return np.interp(x, up[:, 0], up[:, 1]), np.interp(x, lo[:, 0], lo[:, 1])


# --- airfoils -----------------------------------------------------------------

@needs_db
def test_database_sections_are_found():
    for name in ("sc20412", "naca0012", "e387", "rae2822", "s1223"):
        assert airfoils.find_file(name) is not None
    assert len(airfoils.available()) > 2000


@needs_db
@pytest.mark.parametrize("name", ["naca23012", "naca23018", "naca0012"])
def test_naca_formula_matches_database_file(name):
    x = np.linspace(0.02, 0.98, 49)
    a = _surfaces(airfoils.read_dat(airfoils.find_file(name)), x)
    b = _surfaces(airfoils.naca_points(name[4:]), x)
    assert np.max(np.abs(a[0] - b[0])) < 1e-3 and np.max(np.abs(a[1] - b[1])) < 1e-3


def test_naca25118_from_formula():
    assert airfoils.naca_code("naca25118") == "25118"
    a = load_airfoil("naca25118")
    assert a.thickness.max() == pytest.approx(0.18, abs=0.002)
    x = np.linspace(0, 1, 2001)
    yc, _ = airfoils.naca_camber("25118", x)
    assert x[np.argmax(yc)] == pytest.approx(0.25, abs=0.01)    # P = 5 -> maximum camber at 25 %
    assert abs(yc[-1]) < 1e-6                                    # reflexed: back to zero at the edge
    assert yc[x > 0.8].min() < 0                                 # with a small reflex


def test_lednicer_file_is_read(tmp_path):
    x = 0.5 * (1 - np.cos(np.linspace(0, np.pi, 30)))
    yt = airfoils.naca_thickness(x, 0.12)
    lines = ["LEDNICER TEST", f"{len(x)}. {len(x)}.", ""]
    lines += [f"{a:.6f} {b:.6f}" for a, b in zip(x, yt)] + [""]
    lines += [f"{a:.6f} {-b:.6f}" for a, b in zip(x, yt)]
    f = tmp_path / "led.dat"
    f.write_text("\n".join(lines))
    a = load_airfoil(str(f))
    assert a.thickness.max() == pytest.approx(0.12, abs=0.002)


def test_unknown_airfoil_is_refused():
    assert not airfoils.exists("not_an_airfoil")
    with pytest.raises(ValueError):
        load_airfoil("not_an_airfoil")


@needs_db
def test_vector_can_carry_its_own_airfoils():
    spec = params.load_config().types["conventional"]
    vec = params.mid_vector(spec) | {"airfoils": ["naca2415", "naca2412", "sc20412", "naca0012"]}
    _, st = build_stations(spec, vec)
    assert [s.airfoil.name for s in st] == ["naca2415", "naca2412", "sc20412", "naca0012"]
    assert params.canonical(params.resolve(spec, vec)) != params.canonical(params.mid_vector(spec))


@needs_db
def test_per_station_choices_are_sampled():
    spec = params.load_config().types["conventional"]
    choices = (("naca4415", "naca2415"), ("naca4415",), ("naca4412", "e387"), ("naca0012", "naca0009", "sc20410"))
    spec = params.TypeSpec(spec.name, spec.chord_law, spec.span_mode, tuple(c[0] for c in choices),
                           spec.ranges, spec.pinned, choices)
    assert spec.choice_variables == ("airfoil_b0", "airfoil_b2", "airfoil_b3")
    wings = lhs(spec, 30, 7)
    tip = [w["airfoils"][3] for w in wings]
    assert {tip.count(n) for n in choices[3]} == {10}           # each candidate used equally
    assert all(w["airfoils"][1] == "naca4415" for w in wings)
    assert wings == lhs(spec, 30, 7)                            # same seed, same draw


def test_as_is_needs_a_blunt_edge():
    spec = params.load_config().types["conventional"]
    vec = params.mid_vector(spec) | {"airfoils": ["mh91", "mh91", "mh91", "mh91"]}
    cfg = params.load_config()
    te = params.TERule(cfg.te.floor_m, cfg.te.chord_fraction, cfg.te.open_from_xc, "as_is")
    if load_airfoil("mh91").te_thickness > 1e-6:
        pytest.skip("mh91 file has a blunt edge")
    with pytest.raises(ValueError):
        build_wing_sections(spec, vec, te)


# --- published wings ------------------------------------------------------------

def _measured(name):
    spec, vec, te, meta = published_wings.get(name)
    pf, st = build_wing_sections(spec, vec, te)
    return pf, st, te, measure(table_from_stations(st), st)


@pytest.mark.parametrize("name", published_wings.names())
def test_published_wings_pass_the_geometry_checks(name):
    pf, st, te, m = _measured(name)
    assert gates.vector_to_loft(m, pf, st).passed
    assert gates.trailing_edge(m, st, te).passed
    for s in st:                                              # as_is: each section keeps its own edge
        assert s.airfoil.te_thickness == pytest.approx(load_airfoil(s.airfoil.name).te_thickness, abs=1e-12)


def test_onera_m6_matches_published_numbers():
    pf, _, _, _ = _measured("onera_m6")
    assert pf.chord[0] == pytest.approx(0.8059, abs=5e-4) and pf.chord[-1] == pytest.approx(0.4533, abs=5e-4)
    assert mean_aero_chord(pf) == pytest.approx(0.64607, abs=5e-4)
    assert aspect_ratio(pf) == pytest.approx(3.80, abs=0.01)
    assert np.allclose(pf.sweep_le_deg, 30.0)


def test_ribes_matches_published_numbers():
    pf, _, _, _ = _measured("ribes")
    assert pf.area() / 2 == pytest.approx(0.816, abs=0.001)
    assert pf.chord[-1] / pf.chord[0] == pytest.approx(0.700, abs=0.001)


CRM_TABLE = np.array([  # 2y/b, chord [m], twist [deg]; Characterization of the CRM wing (USU), Table A1
    [0.00, 13.6161, 6.7166], [0.10, 11.8976, 4.4402], [0.15, 11.0384, 3.6063], [0.20, 10.1790, 3.0131],
    [0.25, 9.3197, 2.2419], [0.30, 8.4604, 1.5252], [0.35, 7.6010, 0.9379], [0.37, 7.2573, 0.7635],
    [0.40, 7.0416, 0.4285], [0.45, 6.6821, -0.2621], [0.50, 6.3226, -0.6782], [0.55, 5.9631, -0.9436],
    [0.60, 5.6035, -1.2067], [0.65, 5.2440, -1.4526], [0.70, 4.8845, -1.6350], [0.75, 4.5250, -1.8158],
    [0.80, 4.1654, -2.0301], [0.85, 3.8059, -2.2772], [0.90, 3.4464, -2.5773], [0.95, 3.0869, -3.1248],
    [1.00, 2.7274, -3.7500]])


def test_crm_chords_exact_and_twist_close():
    pf, st, _, _ = _measured("nasa_crm")
    eta = np.array([s.y for s in st]) / pf.semi_span
    chord = np.interp(CRM_TABLE[:, 0], eta, [s.chord for s in st])
    twist = np.interp(CRM_TABLE[:, 0], eta, [s.twist_deg for s in st])
    assert np.max(np.abs(chord - CRM_TABLE[:, 1])) < 2e-3        # chord linear between the stations
    assert np.max(np.abs(twist - CRM_TABLE[:, 2])) < 0.52         # stated fidelity
    assert pf.area() == pytest.approx(412.1, rel=0.002)           # published gross area


def test_blendednet_conversion():
    spec, vec, _, meta = published_wings.blendednet(C2=0.7, C3=0.23, C4=0.075, B1=0.15, B2=0.125, B3=0.45,
                                                    S1=50, S2=50, S3=32)
    from cfdauto.geometry.planform import build_planform
    pf = build_planform(spec, vec)
    assert pf.semi_span == pytest.approx(0.725)                   # (B1 + B2 + B3) x C1, C1 = 1 m
    assert np.allclose(np.diff(pf.y), [0.15, 0.125, 0.45])
    assert np.allclose(pf.chord, [1.0, 0.7, 0.23, 0.075])
    assert np.allclose(pf.sweep_le_deg, [50, 50, 32])


def test_blendednetpp_x3_gives_the_middle_sweep():
    spec, vec, _, meta = published_wings.blendednet(C2=0.7, C3=0.23, C4=0.075, B1=0.15, B2=0.125, B3=0.525,
                                                    X3=0.575, S1=50, S3=30)
    from cfdauto.geometry.planform import build_planform
    pf = build_planform(spec, vec)
    assert pf.x_le[2] == pytest.approx(0.575)                     # station 3 leading edge at X3
    with pytest.raises(ValueError):
        published_wings.blendednet(C2=0.7, C3=0.23, C4=0.075, B1=0.15, B2=0.125, B3=0.5, S1=50, S3=30)
