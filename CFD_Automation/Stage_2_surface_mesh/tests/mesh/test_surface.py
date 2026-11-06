import json

import numpy as np
import pytest

from cfdauto.mesh.laws import rules
from cfdauto.mesh.ring import turning
from cfdauto.mesh.surface import build_surface, mesh_name, wing_from_set, write

R = rules("VC")


def test_all_checks_pass(mesh_vc):
    assert mesh_vc.passed, [c.name for c in mesh_vc.failed()]
    assert mesh_vc.level == "VC" and len(mesh_vc.checks) == 14     # the 13 checks (cap quads in two parts)
    assert mesh_vc.info["turning_repairs"] == 0
    assert {r["nose_solved_at"] for r in mesh_vc.stations} <= {"VC", "F"}


def test_checks_read_the_levels_own_values(mesh_vc):
    limit = {c.name: c.limit for c in mesh_vc.checks}
    assert limit["nose_turning"].startswith("<= 17.10 deg (VC: 16.9 + 0.2)")
    assert limit["chord_growth"].startswith("<= 1.25 (VC)")
    assert "9.1" in limit["band_spacing"] and "0.169 % c" in limit["te_spacing"]
    assert "2 x s0" in limit["tip_gap"]


def test_ring_layout(mesh_vc):
    n_side, n_base = mesh_vc.info["n_side"], mesh_vc.info["n_base"]
    assert mesh_vc.wing.shape[0] == 2 * n_side + n_base - 3
    assert n_base % 2 == 1 and n_base - 1 == R.base_cells == 8
    assert mesh_vc.cap.shape == (n_side - (n_base - 1) // 2, n_base, 3)


def test_every_node_is_on_the_loft(mesh_vc, bwb):
    n_side = mesh_vc.info["n_side"]
    v = np.array([r["v"] for r in mesh_vc.stations])
    up = mesh_vc.wing[:n_side][::-1]                       # LE -> TE
    lo = mesh_vc.wing[n_side - 1: 2 * n_side - 1]
    uu, ul = mesh_vc.u[:n_side][::-1], mesh_vc.u[n_side - 1: 2 * n_side - 1]
    vv = np.broadcast_to(v, uu.shape)
    assert np.abs(bwb.loft.upper(uu, vv) - up).max() < R.checks["on_loft_m"]
    assert np.abs(bwb.loft.lower(ul, vv) - lo).max() < R.checks["on_loft_m"]


def test_nose_turning_at_every_station(mesh_vc):
    n_side = mesh_vc.info["n_side"]
    target = R.nose_turning_deg + 10 * R.nose_turning_tol_deg        # VC: 16.9 + 0.2
    for j in range(mesh_vc.wing.shape[1]):
        t = turning(mesh_vc.wing[:, j])
        t[[0, 2 * n_side - 2]] = 0.0
        assert t.max() <= target


def test_trailing_edge_and_band_spacing(mesh_vc):
    for r in mesh_vc.stations:
        assert r["h_te_c_delivered"] <= R.te_spacing_c * 1.01
        assert r["band_max_c"] <= r["h_band_c"] * 1.01
        assert r["growth_max"] <= R.chord_growth_limit


def test_stations_on_every_loft_station_and_tip_gap(mesh_vc, bwb):
    y = np.array([r["y_m"] for r in mesh_vc.stations])
    for yl in mesh_vc.info["loft_station_y_m"]:
        assert np.abs(y - yl).min() == 0.0
    gaps = np.diff(y)
    asked = mesh_vc.info["tip_gap_asked_m"]
    assert asked == pytest.approx(2.0 * mesh_vc.info["s0_tip_m"], rel=1e-12)    # tip gap = 2 x s0 (decision 72)
    assert 0.8 * asked <= gaps[-1] <= asked * (1 + 1e-9)
    r = gaps[1:] / gaps[:-1]
    assert max(r.max(), (1 / r).max()) <= R.span_growth_limit


def test_cap_edge_is_the_tip_ring(mesh_vc):
    cap, ring = mesh_vc.cap, mesh_vc.wing[:, -1]
    edge = np.vstack([cap[0, :], cap[1:, -1], cap[-1, -2::-1], cap[-2::-1, 0]])[:-1]
    assert np.abs(np.sort(edge, axis=0) - np.sort(ring, axis=0)).max() < 1e-12
    assert np.abs(cap[:, :, 1] - ring[0, 1]).max() < 1e-12    # the cap is flat in the tip plane


def test_same_input_same_mesh(bwb, mesh_vc):
    again = build_surface(bwb.loft, 3.0e5)                        # the default level is the coarsest, VC
    assert again.level == "VC" and again.node_hash() == mesh_vc.node_hash()


def test_sealed_sets_refused():
    with pytest.raises(PermissionError):
        wing_from_set("bwb", "holdout_focus", 0)


def test_write_and_refusal(tmp_path, bwb, mesh_vc):
    out = write(mesh_vc, bwb, tmp_path / "ok")
    names = {p.name for p in out.iterdir()}
    assert names == {"surface.npz", "surface.xyz", "stations.csv", "quality.json", "manifest.json"}
    man = json.loads((out / "manifest.json").read_text())
    assert man["name"] == mesh_name(mesh_vc, bwb) == f"mesh_VC_{bwb.input_hash[:8]}_re3e5"
    assert man["passed"] and man["mesh_node_hash"] == mesh_vc.node_hash()
    assert man["rules_config"] == "surface.yaml" and len(man["rules_hash"]) == 64
    q = json.loads((out / "quality.json").read_text())
    assert q["info"]["rules"]["reasons"]["nose_turning_deg"].startswith("law 1")
    bad = build_surface(bwb.loft, 3.0e5, "VC")
    bad.checks[0].passed = False
    out = write(bad, bwb, tmp_path / "bad")
    assert [p.name for p in out.iterdir()] == ["refusal.json"]
