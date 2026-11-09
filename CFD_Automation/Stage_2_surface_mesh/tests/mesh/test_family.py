"""The family rule: every spacing of level C is the VC spacing divided by r (law 23), and the C build is checked
against C's own values."""

import numpy as np
import pytest

from cfdauto.mesh.laws import rules
from cfdauto.mesh.surface import build_surface


def spacings(m):
    y = np.array([r["y_m"] for r in m.stations])
    root, tip = m.stations[0], m.stations[-1]
    return {
        "nose_root": root["h_le_c"], "nose_tip": tip["h_le_c"],
        "te": root["h_te_c_delivered"], "band_root": root["band_max_c"], "band_tip": tip["band_max_c"],
        "tip_gap": float(np.diff(y)[-1]), "root_gap": float(np.diff(y)[0]),
        "base": float(np.linalg.norm(m.wing[-1, 0] - m.wing[0, 0])),   # one base cell at the root
        # a cell over 85-100 % c of the upper side (behind the band written until 8 Nov 2026) and a station gap
        # in the tip squeeze: both must refine by r too (a true scaled copy, not only the end spacings)
        "upper_aft_cell": _cell_at(m, 0, 0.92), "squeeze_gap": _gap_at(m, 0.5 * (y[-1] + m.info["loft_station_y_m"][-2])),
    }


def _cell_at(m, j, x_c):
    n = m.info["n_side"]
    pts, u = m.wing[:n, j][::-1], m.u[:n, j][::-1]
    d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return float(np.interp(x_c, 0.5 * (u[1:] + u[:-1]), d))


def _gap_at(m, y_at):
    y = np.array([r["y_m"] for r in m.stations])
    return float(np.interp(y_at, 0.5 * (y[1:] + y[:-1]), np.diff(y)))


@pytest.mark.slow
def test_level_c_is_level_vc_divided_by_r(bwb, mesh_vc):
    r = rules("VC").ratio
    m = build_surface(bwb.loft, 3.0e5, "C")
    assert m.passed, [c.name for c in m.failed()]
    limit = {c.name: c.limit for c in m.checks}                # C is checked against C's own values
    assert limit["nose_turning"].startswith("<= 13.20 deg (C: 13 + 0.2)")
    assert limit["chord_growth"].startswith("<= 1.187 (C)")
    v_sp, c_sp = spacings(mesh_vc), spacings(m)
    # whole numbers: the base (8 -> 10 cells) and the root panel, whose gaps are set by the gaps per panel
    # (12 at M: 8 at VC, 10 at C, rounded up) on the short BWB root panel: both refine by 10 / 8 = 1.25, not 1.3
    n_vc, n_c = mesh_vc.info["cells_per_panel"][0], m.info["cells_per_panel"][0]
    want = {k: r for k in v_sp} | {"base": 10 / 8, "root_gap": n_c / n_vc if n_vc == 8 else r}
    for k in v_sp:
        assert abs(v_sp[k] / c_sp[k] / want[k] - 1.0) < 0.03, (k, v_sp[k] / c_sp[k], want[k])
    for k in ("n_ring", "n_span"):           # counts refine by r too (within the integer steps)
        assert abs(m.info[k] / mesh_vc.info[k] / r - 1.0) < 0.05, (k, m.info[k], mesh_vc.info[k])


@pytest.mark.slow
def test_family_nose_repair_keeps_the_ratio_and_is_labelled(bwb, monkeypatch):
    """Owner, 8 Nov 2026: a nose repair is a property of the family. Forced here (the trigger moved 0.4 deg below each
    level's angle), build_family puts the same factor on every level, so the asked nose spacing still refines by
    exactly r between levels, no level keeps a repair of its own, and every mesh carries the label."""
    import cfdauto.mesh.surface as S
    monkeypatch.setattr(S, "REPAIR_TOL_STEPS", -20)
    ms = S.build_family(bwb.loft, 3.0e5, ["VC", "C"])
    fam = ms["VC"].info["nose_family"]
    assert fam["rounds"] >= 1 and fam["label"].startswith("family repair") and fam["found"]
    for m in ms.values():
        assert m.info["turning_repairs"] == 0
        assert m.info["nose_factor"] == pytest.approx(fam["factor"])
        assert m.info["nose_repair"]["label"].startswith("family repair")
        assert m.info["nose_family"] is fam
    r = rules("VC").ratio
    vc, c = ms["VC"].stations[0], ms["C"].stations[0]          # the root station is on every level
    assert vc["h_le_c_solved"] == c["h_le_c_solved"]
    assert vc["h_le_c_asked"] / c["h_le_c_asked"] == pytest.approx(r, rel=1e-12)


def test_no_repair_means_label_none(mesh_vc):
    assert mesh_vc.info["nose_repair"]["label"] == "none" and mesh_vc.info["nose_factor"] == 1.0


def test_band_off_is_a_coarser_ring_with_the_family_kept(bwb):
    """The band option off (fully turbulent runs): fewer ring nodes at a Re where the band cell is finer than the
    largest cell, every check passed, the asked nose spacing still x r between levels, and the name says _noband."""
    import cfdauto.mesh.surface as S
    on = S.build_family(bwb.loft, 1.0e6, ["VC", "C"])
    off = S.build_family(bwb.loft, 1.0e6, ["VC", "C"], band=False)
    r = rules("VC").ratio
    for lev in ("VC", "C"):
        assert off[lev].passed and off[lev].info["rules"]["transition_band"] is False
        assert off[lev].info["n_ring"] < on[lev].info["n_ring"]
        assert off[lev].info["n_span"] == on[lev].info["n_span"]          # the stations do not depend on the band
    a, b = off["VC"].stations[0], off["C"].stations[0]
    assert a["h_le_c_asked"] / b["h_le_c_asked"] == pytest.approx(r, rel=1e-12)

    class W:                                                               # mesh_name needs only the input hash
        input_hash = "0123456789abcdef"
    assert S.mesh_name(off["VC"], W).endswith("_noband") and not S.mesh_name(on["VC"], W).endswith("_noband")
