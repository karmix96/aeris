"""V0 measurement: how to build the grid in one station plane (decision 84).

Three methods, the same inputs: the same C line (ring + wake lines), the same far-field nodes, the same wall-normal
distribution of each station (s0, the boundary-layer zone, the fine zone, the wake band, the far growth):

    march      the line shapes from one front moved the same distance everywhere and smoothed along itself over
               its distance from the wall (a hyperbolic march with dissipation), straight on to the far-field node;
               the nodes then placed along each line at the station's distances
    algebraic  each line a cubic curve from the wall node (leaving along the wall normal) to the far-field node
               (arriving along the boundary normal), the nodes placed along it the same way
    elliptic   the algebraic grid, then 300 Winslow (Laplace) sweeps on every node past the fine zone

Measured on every station plane of 8 reference wings (2 per type) at VC, Re 3e5: folded quads, the smallest scaled
Jacobian, the largest in-plane wall angle (all but the two trailing-edge corners), the growth along the lines
against the level's limit, and the time. No volume mesh is judged. Writes data/studies/plane_method.json and
docs/page/plane_method.png.

    python scripts/plane_method_study.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import build_surface, wing_from_set          # noqa: E402
from cfdauto.volume import march as mr, plane as pl                  # noqa: E402
from cfdauto.volume import volume as vol                             # noqa: E402
from cfdauto.volume.checks import growth_along                       # noqa: E402
from cfdauto.volume.laws import rules                                # noqa: E402

WINGS = [("bwb", 0), ("bwb", 3), ("flying_wing", 0), ("flying_wing", 3), ("cranked", 0), ("cranked", 3),
         ("tapered", 0), ("tapered", 3)]


def hermite_paths(X, Q, m, n_t=400):
    """(n_t, N, 2) cubic curves from X (leaving along the bisector normal) to Q (arriving along m)."""
    n = mr.line_normals(X, vol.ENDS)
    L = np.linalg.norm(Q - X, axis=1)[None, :, None]
    t = np.concatenate([[0.0], np.geomspace(1e-9, 1.0, n_t - 1)])[:, None, None]
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    return h00 * X[None] + h10 * L * n[None] + h01 * Q[None] + h11 * L * m[None]


def winslow(G, j_hold, sweeps=300, omega=0.5):
    """Winslow (Laplace in computational space) sweeps on G (n_c, nj+1, 2), nodes with j >= j_hold and inside."""
    G = G.copy()
    for _ in range(sweeps):
        xi = 0.5 * (G[2:, 1:-1] - G[:-2, 1:-1])
        et = 0.5 * (G[1:-1, 2:] - G[1:-1, :-2])
        a = (et ** 2).sum(-1)[..., None]
        b = (xi * et).sum(-1)[..., None]
        c = (xi ** 2).sum(-1)[..., None]
        cross = G[2:, 2:] - G[2:, :-2] - G[:-2, 2:] + G[:-2, :-2]
        new = (a * (G[2:, 1:-1] + G[:-2, 1:-1]) + c * (G[1:-1, 2:] + G[1:-1, :-2]) - 0.5 * b * cross) / (2 * (a + c))
        upd = G[1:-1, 1:-1] + omega * (new - G[1:-1, 1:-1])
        mask = np.zeros(G.shape[1] - 2, bool)
        mask[max(j_hold - 1, 0):] = True
        G[1:-1, 1:-1][:, mask] = upd[:, mask]
    return G


def metrics(G, st, lay, d_ref, rl) -> dict:
    q = vol.quad_quality(G)
    ring = st.ring[: lay.n_air]
    nrm = mr.line_normals(ring)
    a = lay.i_te_up
    v = G[a: a + lay.n_air, 1] - G[a: a + lay.n_air, 0]
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    ang = np.degrees(np.arccos(np.clip((v * nrm).sum(1), -1, 1)))[1:-1]
    d = np.concatenate([np.zeros((G.shape[0], 1)), np.cumsum(np.linalg.norm(np.diff(G, axis=1), axis=2), axis=1)], 1)
    r = growth_along(d.T)
    mid = 0.5 * (d[:, 1:-1] + d[:, 2:]).T
    lim = np.where(mid < rl.fine_zone_local_c * st.chord, rl.wall_growth, rl.far_growth)
    s0 = np.linalg.norm(G[a: a + lay.n_air, 1] - G[a: a + lay.n_air, 0], axis=1)
    return {"folded": int((q <= 0).sum()), "min_sj": float(q.min()), "wall_angle_max": float(ang.max()),
            "growth_over_limit": float((r / lim).max()), "s0_error": float(np.abs(s0 / st.s0 - 1).max())}


def main() -> None:
    rl = rules("VC")
    res = {m: [] for m in ("march", "algebraic", "elliptic")}
    times = {m: 0.0 for m in res}
    per_wing = []
    for typ, idx in WINGS:
        w = wing_from_set(typ, "reference", idx)
        sm = build_surface(w.loft, 3e5, "VC")
        sts = vol.stations_of(sm, rl)
        dom = pl.domain([s.ring for s in sts], sm.info["n_side"], rl)
        dq, _ = vol.wake_nodes(sts, dom, rl)
        lay = pl.PlaneLayout(sm.info["n_side"], sm.info["n_base"], dq.shape[0])
        t = time.time()
        ps = vol.plane_set(sts, dom, lay, dq, rl, vol.KAPPA_LADDER[0])
        t_march = time.time() - t
        Q = ps["Q"]
        m_out = mr.on_boundary(Q, dom)                                    # (Q is on the boundary already)
        m_out = np.where((Q[:, 0] >= dom.x_b)[:, None], np.stack([np.zeros(len(Q)), np.sign(Q[:, 1] - dom.z_m)], -1),
                         mr.unit(Q - np.array([dom.x_b, dom.z_m])))
        row = {"type": typ, "index": idx, "stations": len(sts), "n_c": lay.n_c, "nj": ps["nj"]}
        for k, st in enumerate(sts):
            G = vol.station_grid(lay, ps["paths"][k], ps["S"][k], ps["d"][:, k])
            res["march"].append(metrics(G, st, lay, ps["d"][:, k], rl))
            t = time.time()
            X = ps["X"][k]
            H = hermite_paths(X, Q, m_out)
            S = mr.path_length(H)
            Ga = np.transpose(mr.place(H, S, pl.shrink(ps["d"][:, k], S[-1])), (1, 0, 2))
            times["algebraic"] += time.time() - t
            res["algebraic"].append(metrics(Ga, st, lay, ps["d"][:, k], rl))
            t = time.time()
            j_hold = int(np.searchsorted(ps["d"][:, k], rl.fine_zone_local_c * st.chord))
            Ge = winslow(Ga, j_hold)
            times["elliptic"] += time.time() - t + 0.0
            res["elliptic"].append(metrics(Ge, st, lay, ps["d"][:, k], rl))
        times["march"] += t_march
        for m in res:
            sl = res[m][-len(sts):]
            row[m] = {"folded_stations": int(sum(x["folded"] > 0 for x in sl)),
                      "min_sj": float(min(x["min_sj"] for x in sl)),
                      "wall_angle_max": float(max(x["wall_angle_max"] for x in sl)),
                      "growth_over_limit": float(max(x["growth_over_limit"] for x in sl)),
                      "s0_error": float(max(x["s0_error"] for x in sl))}
        per_wing.append(row)
        print(typ, idx, {m: (row[m]["folded_stations"], round(row[m]["min_sj"], 3), round(row[m]["wall_angle_max"], 2),
                             round(row[m]["growth_over_limit"], 3)) for m in res}, flush=True)
    summary = {}
    for m, rows in res.items():
        summary[m] = {"station_planes": len(rows), "planes_with_a_fold": int(sum(r["folded"] > 0 for r in rows)),
                      "min_sj": float(min(r["min_sj"] for r in rows)),
                      "min_sj_median": float(np.median([r["min_sj"] for r in rows])),
                      "wall_angle_max_deg": float(max(r["wall_angle_max"] for r in rows)),
                      "growth_over_limit_max": float(max(r["growth_over_limit"] for r in rows)),
                      "s0_error_max": float(max(r["s0_error"] for r in rows)),
                      "seconds": round(times[m], 1)}
    out = HERE / "data" / "studies" / "plane_method.json"
    out.write_text(json.dumps({"what": "V0: the station-plane grid method, the same inputs for three methods; 8 "
                                       "reference wings at VC, Re 3e5, every station plane; no volume mesh judged",
                               "summary": summary, "wings": per_wing}, indent=1))
    print(json.dumps(summary, indent=1))
    figure(res, summary)


def figure(res, summary) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    names = list(res)
    for i, m in enumerate(names):
        v = np.array([r["min_sj"] for r in res[m]])
        ax[0].scatter(np.full(len(v), i) + np.random.default_rng(1).uniform(-0.25, 0.25, len(v)), v, s=4, alpha=0.5)
    ax[0].axhline(0.0, color="k", lw=0.8)
    ax[0].axhline(0.05, color="r", lw=0.8, ls="--")
    ax[0].set_xticks(range(len(names)), [f"{m}\n{summary[m]['planes_with_a_fold']} of {summary[m]['station_planes']} folded" for m in names])
    ax[0].set_ylabel("smallest scaled Jacobian of a plane")
    ax[0].set_title("Quality per station plane (8 wings, VC)")
    for i, m in enumerate(names):
        v = np.array([r["wall_angle_max"] for r in res[m]])
        ax[1].scatter(np.full(len(v), i) + np.random.default_rng(2).uniform(-0.25, 0.25, len(v)), v, s=4, alpha=0.5)
    ax[1].axhline(5.0, color="r", lw=0.8, ls="--")
    ax[1].set_yscale("log")
    ax[1].set_xticks(range(len(names)), names)
    ax[1].set_ylabel("largest in-plane wall angle [deg]")
    ax[1].set_title("Lines leaving the wall (limit 5 deg)")
    fig.tight_layout()
    fig.savefig(HERE / "docs" / "page" / "plane_method.png", dpi=130)


if __name__ == "__main__":
    main()
