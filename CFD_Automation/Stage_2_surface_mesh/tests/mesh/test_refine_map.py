"""The refine map in its two modes: Re levels (similarity, decision 70) and Mach (the first approach, the record)."""

import numpy as np
import pytest

from cfdauto.flowmap import engine
from cfdauto.mesh import refine_map as rm
from cfdauto.mesh.laws import rules

ALPHAS = (-5.0, 0.0, 8.0, 12.0)


@pytest.fixture(scope="module")
def re_map():
    return rm.strip_map("bwb", "reference", 0, alphas=ALPHAS, n_per_panel=2, res=rm.RE_LEVELS)


@pytest.fixture(scope="module")
def mach_map():
    return rm.strip_map("bwb", "reference", 0, machs=(0.03, 0.08, 0.13), alphas=ALPHAS, alts=(0.0,), n_per_panel=2)


def test_decided_band_is_the_config_band():
    r = rules()                                   # configs/surface.yaml, the decided rules
    assert tuple(rm.DECIDED_BAND["upper"]) == tuple(r.band_upper)
    assert tuple(rm.DECIDED_BAND["lower"]) == tuple(r.band_lower)


def test_re_mode_grid_and_reynolds(re_map):
    g = re_map["grid"]
    assert rm.grid_axis(re_map) == "re" and "mach" not in g and re_map["mode"] == "re"
    assert g["re"] == list(rm.RE_LEVELS) and g["alt_m"] == [0.0] and g["mach_in_tables"] == 0.1
    assert g["n"] == len(rm.RE_LEVELS) * len(ALPHAS) == re_map["shape"][1]
    c_mean = re_map["wing"]["mean_chord_m"]
    assert c_mean == pytest.approx(1.0, abs=1e-9)                    # unit mean chord (decision 70)
    assert g["speed_m_s"] == pytest.approx([r / (engine.rho_over_mu(0.0) * c_mean) for r in rm.RE_LEVELS])
    re_mean = np.array(re_map["per_condition"]["re_mean"]).reshape(len(rm.RE_LEVELS), len(ALPHAS))
    assert re_mean == pytest.approx(np.array(rm.RE_LEVELS)[:, None] * np.ones((1, len(ALPHAS))), rel=1e-9)
    n, m = re_map["shape"]
    re_strip = np.array(re_map["fields"]["re"], float).reshape(n, m)
    chord = np.array(re_map["strips"]["chord"])
    want = chord[:, None] / c_mean * np.repeat(rm.RE_LEVELS, len(ALPHAS))[None, :]
    assert re_strip == pytest.approx(want, rel=2e-4)                 # the map rounds to 4 decimals


def test_re_mode_reads_the_tables_at_mach_01(re_map):
    """The same answers as the engine with the 2-D tables at Mach 0.1, whatever the speed."""
    from cfdauto.geometry.build import load_set
    from cfdauto.geometry.params import load_config, resolve
    spec = load_config().types["bwb"]
    ws = engine.wing_strips(spec, resolve(spec, load_set("bwb", "reference")["vectors"][0]), None, 2)
    re_, a = 3.0e5, 8.0
    mach = re_ / engine.rho_over_mu(0.0) / engine.sound_speed(0.0)          # unit mean chord
    r = engine.evaluate(ws, [mach], [0.0], [a], mach_in_tables=[0.1])
    n, m = re_map["shape"]
    k = rm.RE_LEVELS.index(re_) * len(ALPHAS) + ALPHAS.index(a)
    got = np.array([np.nan if v is None else v for v in re_map["fields"]["xtr_u"]], float).reshape(n, m)[:, k]
    want = np.round(r["free"]["xtr_top"][:, 0], 4)
    assert np.allclose(got, want, equal_nan=True)


def test_condition_mask_in_both_modes(re_map, mach_map):
    keep = rm.condition_mask(re_map, alphas=(-5, 8), res=(3e5, 3e5))
    assert keep.sum() == 3                                           # one Re level x -5, 0, 8 deg
    assert rm.condition_mask(re_map).all()
    keep = rm.condition_mask(mach_map, (0.03, 0.08), (0, 12))
    assert keep.sum() == 2 * 3
    with pytest.raises(ValueError):
        rm.condition_mask(re_map, machs=(0.03, 0.13))
    with pytest.raises(ValueError):
        rm.condition_mask(mach_map, res=(1e5, 3e5))


def test_envelope_band_in_both_modes(re_map, mach_map):
    e = rm.envelope_band(re_map, res=(1e5, 1e5), alphas=(-5, 8))
    assert e["res"] == [1e5, 1e5] and "machs" not in e
    assert len(e["upper"]) == len(e["lower"]) == re_map["shape"][0]
    for side in ("upper", "lower"):
        assert all(0.0 <= lo <= hi <= 1.0 for lo, hi in e[side])
    e = rm.envelope_band(mach_map)                                   # the first approach's default: Mach 0.03-0.13
    assert e["machs"] == [0.03, 0.13] and "res" not in e


def test_fallback_band_follows_the_mode(re_map, mach_map):
    """A strip with no answer falls back to the generic band of its mode."""
    for sm, band in ((re_map, rm.DECIDED_BAND), (mach_map, rm.GENERIC_BAND)):
        dead = dict(sm, fields=dict(sm["fields"], answered=[False] * len(sm["fields"]["answered"])))
        e = rm.envelope_band(dead, alphas=(-5, 8))
        assert all(e["fallback"])
        assert e["upper"][0] == list(band["upper"]) and e["lower"][0] == list(band["lower"])
