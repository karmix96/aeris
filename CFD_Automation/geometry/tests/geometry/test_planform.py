import numpy as np
import pytest

from cfdauto.geometry import params
from cfdauto.geometry.planform import (
    aspect_ratio, build_planform, mean_aero_chord, panel_sweep_deg, semi_span_m,
)


def _random_vectors(spec, n=200, seed=0):
    rng = np.random.default_rng(seed)
    return [params.from_unit(spec, dict(zip(spec.free_variables, rng.random(len(spec.free_variables)))))
            for _ in range(n)]


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_chords_and_sweeps_exact(wing_type):
    spec = params.load_config().types[wing_type]
    for vec in _random_vectors(spec):
        pf = build_planform(spec, vec)
        r = np.array([1, vec["c2_ratio"], vec["c3_ratio"], vec["c4_ratio"]])
        want_c = vec["root_chord_m"] * (np.cumprod(r) if spec.chord_law == "per_panel" else r)
        assert np.max(np.abs(pf.chord / want_c - 1)) < 1e-3          # 0.1 %
        want_sw = [vec["sweep1_deg"], vec["sweep2_deg"], vec["sweep3_deg"]]
        assert np.max(np.abs(panel_sweep_deg(pf.y, pf.x_le) - want_sw)) < 0.1  # 0.1 deg
        assert pf.semi_span == pytest.approx(semi_span_m(spec, vec))


def test_panel_spans_follow_ratios():
    spec = params.load_config().types["bwb"]
    vec = params.mid_vector(spec)
    pf = build_planform(spec, vec)
    s = semi_span_m(spec, vec)
    p1, p2, p3 = pf.panel_span
    assert p3 == pytest.approx(vec["b3_ratio"] * s)
    assert p1 == pytest.approx(vec["split_ratio"] * (s - p3))
    assert p1 + p2 + p3 == pytest.approx(s)


def test_root_chord_fraction_span_mode():
    import dataclasses
    spec = dataclasses.replace(params.load_config().types["conventional"], span_mode="root_chord_fractions")
    vec = params.mid_vector(spec) | {"semi_span_m": 4.0}
    pf = build_planform(spec, vec)
    assert pf.semi_span == pytest.approx(vec["semi_span_m"] * vec["root_chord_m"])


def test_forward_sweep_builds():
    spec = params.load_config().types["conventional"]
    vec = params.mid_vector(spec) | {"sweep1_deg": -10.0, "sweep2_deg": -10.0, "sweep3_deg": -10.0}
    pf = build_planform(spec, vec)
    assert np.all(np.diff(pf.x_le) < 0)


def test_rectangle_area_mac_ar():
    import dataclasses
    spec = dataclasses.replace(params.load_config().types["conventional"], span_mode="root_chord_fractions")
    vec = params.mid_vector(spec) | {
        "root_chord_m": 0.5, "c2_ratio": 1.0, "c3_ratio": 1.0, "c4_ratio": 1.0,
        "semi_span_m": 4.0, "sweep1_deg": 0.0, "sweep2_deg": 0.0, "sweep3_deg": 0.0,
    }
    pf = build_planform(spec, vec)
    assert pf.area() == pytest.approx(2 * 2.0 * 0.5)
    assert mean_aero_chord(pf) == pytest.approx(0.5)
    assert aspect_ratio(pf) == pytest.approx(8.0)


def test_mac_of_straight_taper():
    # MAC of a straight taper: (2/3) c_r (1 + l + l^2) / (1 + l)
    spec = params.load_config().types["tapered"]
    lam = 0.4
    vec = params.mid_vector(spec) | {"root_chord_m": 1.0, "c4_ratio": lam}
    vec = params.resolve(spec, vec)
    y = build_planform(spec, vec).y / build_planform(spec, vec).semi_span
    vec |= {"c2_ratio": 1 + (lam - 1) * y[1], "c3_ratio": 1 + (lam - 1) * y[2]}
    assert mean_aero_chord(build_planform(spec, vec)) == pytest.approx(
        2 / 3 * (1 + lam + lam**2) / (1 + lam))


def test_negative_chord_refused():
    spec = params.load_config().types["bwb"]
    vec = params.mid_vector(spec) | {"c4_ratio": -0.1}
    with pytest.raises(ValueError):
        build_planform(spec, vec)


def test_per_panel_never_wider_outboard():
    spec = params.load_config().types["conventional"]
    assert spec.chord_law == "per_panel"
    for vec in _random_vectors(spec, n=500, seed=3):
        c = build_planform(spec, vec).chord
        assert np.all(np.diff(c) <= 1e-12)


def test_tapered_has_straight_edges():
    spec = params.load_config().types["tapered"]
    assert set(spec.derived) == {"c2_ratio", "c3_ratio", "sweep2_deg", "sweep3_deg", "semi_span_m"}
    for vec in _random_vectors(spec, n=200, seed=4):
        pf = build_planform(spec, vec)
        x_te = pf.x_le + pf.chord
        for x in (pf.x_le, x_te):           # leading and trailing edge: one straight line each
            slope = np.diff(x) / np.diff(pf.y)
            assert np.ptp(slope) < 1e-9
        assert pf.chord[-1] / pf.chord[0] == pytest.approx(vec["c4_ratio"])


def test_resolve_is_idempotent():
    cfg = params.load_config()
    for spec in cfg.types.values():
        for vec in _random_vectors(spec, n=20, seed=5):
            once = params.resolve(spec, vec)
            assert params.resolve(spec, once) == once
