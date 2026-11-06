"""Section tables (interpolation, blend rule), the vectorized engine, and tool = dataset."""

import shutil

import numpy as np
import pytest

from cfdauto.flowmap import engine, tables
from cfdauto.geometry import params

CFG = params.load_config()
LR, MM, AA = np.meshgrid(np.log10(tables.RE), tables.MACH, tables.ALPHA, indexing="ij")


def linear_table(name: str, shift: float = 0.0) -> tables.Table:
    """Fields linear in (log Re, Mach, angle): trilinear interpolation must reproduce them exactly."""
    d = {f: np.zeros(LR.shape) for f in tables.FIELDS}
    d["cl"] = 0.1 * AA + 0.05 * MM + shift
    d["cd"] = 0.02 - 0.002 * LR + 0.0004 * AA + 0.001 * MM + 0.1 * shift
    d["xtr_top"] = 0.6 - 0.01 * AA + shift
    return tables.Table(name, np.log10(tables.RE), tables.MACH, tables.ALPHA, d)


@pytest.fixture
def fake_tables(monkeypatch):
    """Linear tables under the real section names, so engine.evaluate runs without table files."""
    loaded = {}
    for k, s in enumerate(tables.SECTIONS):
        for mode in ("free", "trip"):
            t = linear_table(s, shift=0.01 * k + (0.005 if mode == "trip" else 0.0))
            loaded[tables.table_id(s, mode, 9.0)] = t
    monkeypatch.setattr(tables, "_LOADED", loaded)
    return loaded


def test_interp_reproduces_linear_fields():
    t = linear_table("x")
    rng = np.random.default_rng(0)
    re_ = 10 ** rng.uniform(np.log10(2e4), np.log10(5e6), 200)
    M = rng.uniform(0, 0.2, 200)
    a = rng.uniform(-9.5, 13.5, 200)
    r = tables.interp(t, re_, M, a)
    assert np.allclose(r["cl"], 0.1 * a + 0.05 * M)
    assert np.allclose(r["cd"], 0.02 - 0.002 * np.log10(re_) + 0.0004 * a + 0.001 * M)
    assert not r["re_clamped"].any()


def test_interp_nan_rule_and_edges():
    t = linear_table("x")
    i, j, k = 5, 1, 30
    t.data["cd"] = t.data["cd"].copy()
    t.data["cd"][i, j, k] = np.nan                      # one point that did not converge
    at = tables.interp(t, tables.RE[i], tables.MACH[j], tables.ALPHA[k])
    assert np.isnan(at["cd"][()])                       # on it: no value
    near = tables.interp(t, tables.RE[i], tables.MACH[j], tables.ALPHA[k] + 0.4)   # 80 % weight on the next angle
    assert np.isfinite(near["cd"][()])
    assert near["cd"][()] == pytest.approx(t.data["cd"][i, j, k + 1])
    out = tables.interp(t, [1e3, 1e8], [0.1, 0.1], [2.0, 15.0])
    assert out["re_clamped"].all() and np.isnan(out["cd"][1])         # angle beyond the grid: NaN


def test_blend_rule_end_points(fake_tables):
    re_, M, a = np.array([3e5]), np.array([0.1]), np.array([3.0])
    ra = tables.lookup("mh104", None, 0.0, re_, M, a)
    rb = tables.lookup("mh61", None, 0.0, re_, M, a)
    for s, want in ((0.0, ra), (1.0, rb)):
        r = tables.lookup("mh104", "mh61", s, re_, M, a)
        assert r["cd"][0] == pytest.approx(want["cd"][0])
    mid = tables.lookup("mh104", "mh61", 0.5, re_, M, a)
    assert mid["cd"][0] == pytest.approx(0.5 * (ra["cd"][0] + rb["cd"][0]))


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_strips_weights_and_reynolds(wing_type, fake_tables):
    spec = CFG.types[wing_type]
    ws = engine.wing_strips(spec, params.mid_vector(spec))
    assert ws.w.sum() == pytest.approx(1.0) and (ws.w > 0).all()
    assert ws.y[0] == 0.0 and ws.y[-1] == pytest.approx(0.97 * ws.semi_span)
    r = engine.evaluate(ws, [0.05, 0.1], [0.0, 3048.0], [2.0, 4.0])
    v = np.array([0.05 * 340.294, 0.1 * engine.sound_speed(3048.0)])
    assert np.allclose(r["re"], engine.rho_over_mu([0.0, 3048.0]) * v * ws.chord[:, None], rtol=1e-4)
    m = engine.metrics(ws, r)
    wc = ws.w[:, None] * ws.chord[:, None]
    want = (wc * r["trip"]["cd"]).sum(0) / (wc * r["free"]["cd"]).sum(0) - 1
    assert np.allclose(m["sa_bias"], want)
    assert m["sa_bias"].shape == (2,) and set(np.unique(m["category"])) <= {0, 1, 2, 3}


def test_category_rule():
    m = {"sa_bias": np.array([0.05, 0.3, 0.05, np.nan, 0.05, 0.05]), "span_re_lt_1e5": np.array([0, 0, 0.2, 0, 0, 0]),
         "conv_span": np.array([1, 1, 1, 1, 0.3, 1]), "lam_upper": np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.4])}
    # the last: small drag bias but a long laminar run -> a transition model, not SA
    assert engine.category(m).tolist() == [0, 1, 2, 3, 3, 1]


def test_induced_angle_lowers_local_angle(fake_tables):
    """The baseline includes the induced angle; induced=False (the old baseline) does not."""
    spec = CFG.types["tapered"]
    ws = engine.wing_strips(spec, params.mid_vector(spec))
    a = engine.evaluate(ws, [0.1], [0.0], [6.0], induced=False)
    b = engine.evaluate(ws, [0.1], [0.0], [6.0])
    assert a["alpha_induced"][0] == 0 and b["alpha_induced"][0] > 0
    assert np.all(b["alpha_local"] < a["alpha_local"])


def test_induced_angle_is_converged_and_consistent(fake_tables):
    """The returned induced angle is the one the strips were evaluated at, and it matches CL / (pi AR);
    with the induced angle the level-flight lift is the strip lift (no extra lift-slope factor)."""
    import math
    spec = CFG.types["bwb"]
    ws = engine.wing_strips(spec, params.mid_vector(spec))
    r = engine.evaluate(ws, [0.08, 0.12], [0.0, 1524.0], [4.0, 8.0])
    assert np.allclose(r["alpha_local"], np.array([4.0, 8.0])[None, :] + ws.twist[:, None] - r["alpha_induced"][None, :])
    target = np.degrees(r["cl_wing"] / (math.pi * ws.aspect_ratio))
    assert np.allclose(r["alpha_induced"], target, atol=0.05)
    m = engine.metrics(ws, r)
    assert np.allclose(m["cl3d"], m["cl2d"])


needs_tables = pytest.mark.skipif(not all(tables.has(s) and tables.has(s, "trip") for s in tables.SECTIONS),
                                  reason="section tables not built")


@needs_tables
def test_tool_equals_dataset():
    """The single-wing tool and the dataset use the same engine: same wing, same condition, same answer."""
    from cfdauto.flowmap.core import flow_map
    from cfdauto.flowmap.dataset import build
    from cfdauto.geometry.build import load_set
    df = build(types=("cranked",), n_wings=1)
    row = df[(df["set"] == "A") & (df["mach"] == 0.08) & (df["altitude_m"] == 1524) & (df["alpha_deg"] == 4)].iloc[0]
    spec = CFG.types["cranked"]
    vec = load_set("cranked", "training_focus")["vectors"][0]
    fm = flow_map(spec, vec, False, None, 1524.0, 4.0, ["naca4415", "naca4415", "naca4412", "naca4412"], mach=0.08,
                  compare_sets=False)
    assert fm["method"] == "tables"
    assert fm["metrics"]["sa_bias"] == pytest.approx(row["sa_bias"], rel=1e-5)
    assert fm["metrics"]["lam_upper"] == pytest.approx(row["lam_upper"], rel=1e-5)


@needs_tables
@pytest.mark.skipif(shutil.which("xfoil") is None, reason="xfoil not installed")
def test_table_grid_point_matches_direct_xfoil():
    from cfdauto.flowmap import xfoil
    from cfdauto.geometry.sections import load_airfoil
    re_, M, a = 4e5, 0.1, 3.0
    d = xfoil.run(load_airfoil("naca4412").selig(), re_, a, False, M)
    t = tables.interp(tables.load("naca4412"), re_, M, a)
    assert d is not None
    assert t["cd"][()] == pytest.approx(d["cd"], rel=0.02)
    assert t["xtr_top"][()] == pytest.approx(d["xtr_top"], abs=0.02)


def test_single_angle_gaps_are_filled_double_gaps_kept():
    arr = {f: np.tile(np.arange(10.0), (2, 1, 1)) for f in ("cd", "cl")}
    arr["cd"][0, 0, 4] = np.nan                      # one failed angle: filled from its neighbours
    arr["cd"][1, 0, 6] = arr["cd"][1, 0, 7] = np.nan  # two in a row: stays NaN (no 2-D answer)
    n = tables.fill_single_gaps(arr)
    assert n == 1 and arr["cd"][0, 0, 4] == pytest.approx(4.0)
    assert np.isnan(arr["cd"][1, 0, 6]) and np.isnan(arr["cd"][1, 0, 7])


def test_gap_fill_keeps_flags_zero_or_one():
    """A 0/1 bubble flag is filled only where both neighbours agree; it never becomes 0.5."""
    arr = {"cd": np.ones((1, 1, 6)), "bub_u": np.array([[[0.0, 0.0, 1.0, 1.0, 1.0, 0.0]]])}
    arr["cd"][0, 0, 1] = arr["cd"][0, 0, 3] = np.nan          # neighbours of 1: 0 and 1; of 3: 1 and 1
    arr["bub_u"][0, 0, 1] = arr["bub_u"][0, 0, 3] = np.nan
    assert tables.fill_single_gaps(arr) == 2
    assert np.isnan(arr["bub_u"][0, 0, 1]) and arr["bub_u"][0, 0, 3] == 1.0


def test_level_flight_band_follows_the_fit():
    from cfdauto.flowmap.dataset import load_flow_config, wing_loading_band
    fc = load_flow_config()
    lf = fc["level_flight"]
    lo, hi = wing_loading_band(3.0, "conventional", fc)
    centre = 10 ** (lf["a"] + lf["k"] * np.log10(3.0))
    assert lo == pytest.approx(centre / lf["factor"]) and hi == pytest.approx(centre * lf["factor"])
    lo_t, _ = wing_loading_band(3.0, "tailless", fc)
    assert lo_t < lo                                  # tailless wings are lighter per area for their span


def test_tool_reports_level_flight_and_sheet(fake_tables, monkeypatch):
    from cfdauto.flowmap import core
    monkeypatch.setattr(tables, "has", lambda *a, **k: True)
    spec = CFG.types["cranked"]
    vec = params.mid_vector(spec)
    fm = core.flow_map(spec, vec, False, None, 0.0, 4.0, mach=0.1, compare_sets=False)
    assert fm["method"] == "tables"
    lf = fm["level_flight"]
    assert lf["wing_loading_n_m2"] > 0 and lf["real_band_n_m2"][0] < lf["real_band_n_m2"][1]
    sh = core.sweep_sheet(spec, vec, [0.05, 0.1, 0.15], [0, 4, 8])
    assert np.array(sh["sa_bias"]).shape == (3, 3) and np.array(sh["level_flight"]).shape == (3, 3)


def test_eta2_and_spearman():
    import pandas as pd
    from cfdauto.flowmap.analysis import eta2, spearman
    rng = np.random.default_rng(0)
    x = pd.Series(rng.uniform(0, 1, 5000))
    noise = pd.Series(rng.uniform(0, 1, 5000))
    assert eta2(x, 3 * x, False) > 0.95                # y set by x alone
    assert eta2(noise, 3 * x, False) < 0.01            # an unrelated input explains nothing
    assert spearman(x, -x) == pytest.approx(-1.0)


@needs_tables
@pytest.mark.skipif(shutil.which("xfoil") is None, reason="xfoil not installed")
def test_tool_tables_path_matches_direct_xfoil_on_a_wing():
    """Whole wing: the table path (interpolation + blend rule) against direct XFOIL on every strip."""
    from cfdauto.flowmap.core import flow_map, rho_over_mu
    from cfdauto.geometry.build import load_set
    spec = CFG.types["bwb"]
    vec = load_set("bwb", "reference")["vectors"][0]
    # The first case in similarity form (decision 70): this shape at Re 9.3e5 on the mean chord (it was the
    # real-size wing, mean chord 0.546 m, at Mach 0.08 and 1,000 m). At unit mean chord that Re needs this speed.
    v = 9.3e5 / rho_over_mu(1000.0)
    a = flow_map(spec, vec, True, v, 1000.0, 4.0, method="tables", compare_sets=False)
    b = flow_map(spec, vec, True, v, 1000.0, 4.0, method="xfoil", compare_sets=False)
    assert a["metrics"]["sa_bias"] == pytest.approx(b["metrics"]["sa_bias"], abs=0.05)
    assert a["metrics"]["lam_upper"] == pytest.approx(b["metrics"]["lam_upper"], abs=0.02)
    assert a["model"]["category"] == b["model"]["category"]
