import json

import numpy as np
import pytest

from cfdauto.mesh.laws import rules
from cfdauto.mesh.ring import turning
from cfdauto.mesh.surface import build_surface, mesh_name, wing_from_set, write

R = rules("C")


def test_all_checks_pass(mesh_c):
    assert mesh_c.passed, [c.name for c in mesh_c.failed()]


def test_ring_layout(mesh_c):
    n_side, n_base = mesh_c.info["n_side"], mesh_c.info["n_base"]
    assert mesh_c.wing.shape[0] == 2 * n_side + n_base - 3
    assert n_base % 2 == 1 and n_base - 1 == R.base_cells
    assert mesh_c.cap.shape == (n_side - (n_base - 1) // 2, n_base, 3)


def test_every_node_is_on_the_loft(mesh_c, bwb):
    n_side = mesh_c.info["n_side"]
    v = np.array([r["v"] for r in mesh_c.stations])
    up = mesh_c.wing[:n_side][::-1]                       # LE -> TE
    lo = mesh_c.wing[n_side - 1: 2 * n_side - 1]
    uu, ul = mesh_c.u[:n_side][::-1], mesh_c.u[n_side - 1: 2 * n_side - 1]
    vv = np.broadcast_to(v, uu.shape)
    assert np.abs(bwb.loft.upper(uu, vv) - up).max() < R.checks["on_loft_m"]
    assert np.abs(bwb.loft.lower(ul, vv) - lo).max() < R.checks["on_loft_m"]


def test_nose_turning_at_every_station(mesh_c):
    n_side = mesh_c.info["n_side"]
    target = R.nose_turning_deg + 10 * R.nose_turning_tol_deg
    for j in range(mesh_c.wing.shape[1]):
        t = turning(mesh_c.wing[:, j])
        t[[0, 2 * n_side - 2]] = 0.0
        assert t.max() <= target


def test_trailing_edge_and_band_spacing(mesh_c):
    for r in mesh_c.stations:
        assert r["h_te_c_delivered"] <= R.te_spacing_c * 1.01
        assert r["band_max_c"] <= r["h_band_c"] * 1.01
        assert r["growth_max"] <= R.chord_growth_limit


def test_stations_on_every_loft_station_and_tip_gap(mesh_c, bwb):
    y = np.array([r["y_m"] for r in mesh_c.stations])
    for yl in mesh_c.info["loft_station_y_m"]:
        assert np.abs(y - yl).min() == 0.0
    gaps = np.diff(y)
    assert 0.8 * mesh_c.info["s0_tip_m"] <= gaps[-1] <= mesh_c.info["s0_tip_m"] * (1 + 1e-9)
    r = gaps[1:] / gaps[:-1]
    assert max(r.max(), (1 / r).max()) <= R.span_growth_limit


def test_cap_edge_is_the_tip_ring(mesh_c):
    cap, ring = mesh_c.cap, mesh_c.wing[:, -1]
    edge = np.vstack([cap[0, :], cap[1:, -1], cap[-1, -2::-1], cap[-2::-1, 0]])[:-1]
    assert np.abs(np.sort(edge, axis=0) - np.sort(ring, axis=0)).max() < 1e-12
    assert np.abs(cap[:, :, 1] - ring[0, 1]).max() < 1e-12    # the cap is flat in the tip plane


def test_same_input_same_mesh(bwb, mesh_c):
    again = build_surface(bwb.loft, 3.0e5, "C")
    assert again.node_hash() == mesh_c.node_hash()


def test_sealed_sets_refused():
    with pytest.raises(PermissionError):
        wing_from_set("bwb", "holdout_focus", 0)


def test_write_and_refusal(tmp_path, bwb, mesh_c):
    out = write(mesh_c, bwb, tmp_path / "ok")
    names = {p.name for p in out.iterdir()}
    assert names == {"surface.npz", "surface.xyz", "stations.csv", "quality.json", "manifest.json"}
    man = json.loads((out / "manifest.json").read_text())
    assert man["name"] == mesh_name(mesh_c, bwb) == f"mesh_C_{bwb.input_hash[:8]}_re3e5"
    assert man["passed"] and man["mesh_node_hash"] == mesh_c.node_hash()
    bad = build_surface(bwb.loft, 3.0e5, "C")
    bad.checks[0].passed = False
    out = write(bad, bwb, tmp_path / "bad")
    assert [p.name for p in out.iterdir()] == ["refusal.json"]
