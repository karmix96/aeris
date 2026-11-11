"""Q5 of the V7 night plan (NIGHT_11NOV.md section 5): does the wake stay inside the mesh's wake fan?

    python solve/wake_check.py --case runs/n11_today_VVC_am5           # -> runs/<case>/adflow/wake_check.json, .png
    python solve/wake_check.py --case runs/n11_today_VVC_a10 --y-frac 0.5 --d 0.25 0.5 1 2

On the station plane nearest y_frac of the semi-span (the stations are exact planes y = const: one k-index of the
mesh), the wake centre is the lowest velocity magnitude on vertical lines d local chords behind the trailing edge.
It is compared with the band the mesh was built for (configs/volume.yaml, wake.band, or the mesh's own what-if copy):

    z_TE + d tan(alpha_lo) - margin c  <=  z_wake  <=  z_TE + d tan(alpha_hi) + margin c

with c the local chord and z_TE the middle of the two trailing-edge corners of the wall at that station (the wall
points with the largest x on the upper and the lower side, from blocks.npz). x is measured from the same middle.

Written on the night of 11-12 Nov 2026 (the first ADflow volume solutions on a Stage 3 mesh). The volume file is
read with the repo's own ADF reader (cfdauto.volume.cgns.read_adf); each solution zone is matched to its mesh block
by its coordinates, so zone names do not matter. Node data and cell data (with or without rind) are both read.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]                     # Stage_3_volume_mesh
sys.path.insert(0, str(HERE.parent))
from cfdauto.volume.cgns import rdata, read_adf                 # noqa: E402

WAKE_BLOCKS = ("WU_in", "B_in", "WL_in")


def band(mesh: Path) -> dict:
    """wake.band of the rules the mesh was built with: its what-if copy if it has one, else configs/volume.yaml."""
    import yaml
    for f in (mesh / "whatif_volume.yaml", HERE / "configs" / "volume.yaml"):
        if f.exists():
            b = yaml.safe_load(f.read_text())["wake"]["band"]
            return {"alpha_lo_deg": float(b["alpha_lo_deg"]), "alpha_hi_deg": float(b["alpha_hi_deg"]),
                    "margin_c": float(b["margin_c"]), "length_local_c": float(b["length_local_c"]), "source": str(f)}
    raise SystemExit("no wake band found")


def zones(path: Path) -> list[dict]:
    """Every Zone_t: coordinates (ni, nj, nk, 3) and the flow solution arrays with their location and rind."""
    root, raw = read_adf(path)
    out = []
    for base in (n for n in root.children if n.label == "CGNSBase_t"):
        for z in (n for n in base.children if n.label == "Zone_t"):
            gc = next(n for n in z.children if n.label == "GridCoordinates_t")
            xyz = np.stack([rdata(next(n for n in gc.children if n.name == c), raw) for c in
                            ("CoordinateX", "CoordinateY", "CoordinateZ")], axis=-1)
            sol = {}
            for fs in (n for n in z.children if n.label == "FlowSolution_t"):
                loc = next((rdata(n, raw) for n in fs.children if n.label == "GridLocation_t"), "Vertex")
                rind = next((rdata(n, raw) for n in fs.children if n.label == "Rind_t"), None)
                for a in (n for n in fs.children if n.label == "DataArray_t"):
                    sol[a.name] = {"data": rdata(a, raw), "location": str(loc).strip(),
                                   "rind": None if rind is None else [int(v) for v in np.ravel(rind)]}
            out.append({"name": z.name, "xyz": xyz, "solution": sol})
    return out


def match(blocks: dict, zs: list[dict]) -> dict:
    """mesh block name -> solution zone, by the coordinates (shape and values)."""
    got = {}
    for name, X in blocks.items():
        for z in zs:
            if z["xyz"].shape == X.shape and np.allclose(z["xyz"], X, atol=1e-9 * max(1.0, float(np.abs(X).max()))):
                got[name] = z
                break
    return got


def plane_values(z: dict, k: int, var: str) -> tuple[np.ndarray, np.ndarray]:
    """In-plane points (x, z) and the values of `var` on the station plane k of one zone."""
    X = z["xyz"]
    s = z["solution"][var]
    a, loc, rind = s["data"], s["location"], s["rind"]
    ni, nj, nk = X.shape[:3]
    if loc.lower().startswith("vertex"):
        lo = [0, 0, 0] if not rind else rind[0::2]
        v = a[lo[0]: lo[0] + ni, lo[1]: lo[1] + nj, lo[2] + k]
        return X[:, :, k, [0, 2]].reshape(-1, 2), v.reshape(-1)
    # cell data: cell c spans nodes c..c+1; the plane value is the mean of the two cell layers beside node plane k
    lo = [0, 0, 0] if not rind else rind[0::2]
    C = 0.125 * sum(X[a_: ni - 1 + a_, b_: nj - 1 + b_, c_: nk - 1 + c_] for a_ in (0, 1) for b_ in (0, 1) for c_ in (0, 1))
    layers = [c for c in (k - 1, k) if 0 <= c < nk - 1]
    pts = np.mean([C[:, :, c, :][..., [0, 2]] for c in layers], axis=0)
    val = np.mean([a[lo[0]: lo[0] + ni - 1, lo[1]: lo[1] + nj - 1, lo[2] + c] for c in layers], axis=0)
    return pts.reshape(-1, 2), val.reshape(-1)


def speed(z: dict, k: int) -> tuple[np.ndarray, np.ndarray, str]:
    sol = z["solution"]
    if all(v in sol for v in ("VelocityX", "VelocityY", "VelocityZ")):
        p, u = plane_values(z, k, "VelocityX")
        _, v = plane_values(z, k, "VelocityY")
        _, w = plane_values(z, k, "VelocityZ")
        return p, np.sqrt(u * u + v * v + w * w), "|V| from VelocityX/Y/Z"
    if all(v in sol for v in ("Density", "MomentumX", "MomentumY", "MomentumZ")):
        p, r = plane_values(z, k, "Density")
        m = [plane_values(z, k, f"Momentum{c}")[1] for c in "XYZ"]
        return p, np.sqrt(sum(q * q for q in m)) / r, "|V| from Momentum / Density"
    raise SystemExit(f"no velocity in the solution: {sorted(sol)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", type=Path, required=True)
    ap.add_argument("--volume", type=Path, default=None, help="default: the *_vol.cgns in <case>/adflow")
    ap.add_argument("--y-frac", type=float, default=0.5)
    ap.add_argument("--d", type=float, nargs="+", default=[0.25, 0.5, 1.0, 2.0])
    ap.add_argument("--figure", action="store_true", help="also write wake_check.png")
    a = ap.parse_args()
    case = json.loads((a.case / "case.json").read_text())
    mesh = Path(case["mesh_folder"])
    vol = a.volume or next(iter(sorted((a.case / "adflow").glob("*_vol.cgns"))), None)
    if vol is None or not vol.exists():
        raise SystemExit(f"no volume solution in {a.case / 'adflow'}")
    B = np.load(mesh / "blocks.npz")
    st = json.loads((mesh / "quality.json").read_text())["info"]["stations"]
    semi = case["references"]["semi_span"]
    k = int(np.argmin([abs(s["y"] - a.y_frac * semi) for s in st]))
    y_k, c = float(st[k]["y"]), float(st[k]["chord"])
    up = B["CU_in"][:, 0, k]                                    # the wall ring of the upper side at station k
    dn = B["CL_in"][:, 0, k]
    cu, cl = up[int(np.argmax(up[:, 0]))], dn[int(np.argmax(dn[:, 0]))]
    x_te, z_te = 0.5 * (cu[0] + cl[0]), 0.5 * (cu[2] + cl[2])
    bd = band(mesh)
    zs = zones(vol)
    m = match({n: B[n] for n in WAKE_BLOCKS}, zs)
    missing = [n for n in WAKE_BLOCKS if n not in m]
    if missing:
        raise SystemExit(f"blocks not found in {vol.name} by their coordinates: {missing}; zones "
                         f"{[(z['name'], z['xyz'].shape) for z in zs]}")
    pts, spd, how = [], [], ""
    for n in WAKE_BLOCKS:
        p, s, how = speed(m[n], k)
        pts.append(p)
        spd.append(s)
    P, S = np.concatenate(pts), np.concatenate(spd)
    from scipy.interpolate import LinearNDInterpolator
    f = LinearNDInterpolator(P, S)
    v_inf = float(np.nanmedian(S[np.abs(P[:, 1] - z_te) > 2.0 * c])) if np.any(np.abs(P[:, 1] - z_te) > 2.0 * c) else None
    lo_t, hi_t = math.tan(math.radians(bd["alpha_lo_deg"])), math.tan(math.radians(bd["alpha_hi_deg"]))
    rows = []
    for d in a.d:
        x = x_te + d * c
        lo, hi = z_te + d * lo_t - bd["margin_c"] * c, z_te + d * hi_t + bd["margin_c"] * c
        zz = np.linspace(lo - 0.5 * c, hi + 0.5 * c, 4001)        # wider than the band: a wake outside it is found too
        vv = f(np.full_like(zz, x), zz)
        ok = np.isfinite(vv)
        if not ok.any():
            rows.append({"d_local_c": d, "error": "the line is outside the wake blocks"})
            continue
        i = int(np.nanargmin(vv))
        zw = float(zz[i])
        rows.append({"d_local_c": d, "x": x, "z_wake": zw, "speed_min": float(vv[i]),
                     "deficit": None if not v_inf else 1.0 - float(vv[i]) / v_inf,
                     "band_lo": lo, "band_hi": hi, "inside": bool(lo <= zw <= hi),
                     "margin_to_band_edge_c": min(zw - lo, hi - zw) / c,
                     "z_wake_minus_z_te_c": (zw - z_te) / c,
                     "wake_angle_deg": math.degrees(math.atan2(zw - z_te, d * c)),
                     "at_window_edge": bool(i in (0, len(zz) - 1))})
    rep = {"case": str(a.case), "alpha_deg": case["alpha_deg"], "volume_file": str(vol), "station_k": k,
           "y": y_k, "y_over_semispan": y_k / semi, "local_chord": c, "x_te": x_te, "z_te": z_te,
           "te_corners": {"upper": cu.tolist(), "lower": cl.tolist()}, "band": bd, "speed": how,
           "v_inf_estimate": v_inf, "lines": rows,
           "all_inside": all(r.get("inside", False) for r in rows),
           "zones_matched": {n: m[n]["name"] for n in WAKE_BLOCKS},
           "locations": sorted({s["location"] for n in WAKE_BLOCKS for s in m[n]["solution"].values()})}
    out = a.case / "adflow" / "wake_check.json"
    out.write_text(json.dumps(rep, indent=1))
    if a.figure:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4.2))
        sel = (P[:, 0] > x_te - 0.2 * c) & (P[:, 0] < x_te + 2.3 * c) & (np.abs(P[:, 1] - z_te) < 0.8 * c)
        t = ax.tricontourf((P[sel, 0] - x_te) / c, (P[sel, 1] - z_te) / c, S[sel] / (v_inf or 1.0), 40, cmap="viridis")
        fig.colorbar(t, ax=ax, label="|V| / V∞" if v_inf else "|V|")
        dd = np.linspace(0, bd["length_local_c"], 50)
        ax.plot(dd, dd * lo_t - bd["margin_c"], "w--", lw=1)
        ax.plot(dd, dd * hi_t + bd["margin_c"], "w--", lw=1, label=f"band {bd['alpha_lo_deg']:g}° to {bd['alpha_hi_deg']:g}° ± {bd['margin_c']:g} c")
        for r in rows:
            if "z_wake" in r:
                ax.plot(r["d_local_c"], r["z_wake_minus_z_te_c"], "o", color="r" if not r["inside"] else "w", ms=5)
        ax.set_xlabel("(x − x_TE) / c")
        ax.set_ylabel("(z − z_TE) / c")
        ax.set_title(f"α {case['alpha_deg']:g}°, station y/s = {y_k / semi:.3f}: the wake centre (dots) and the band")
        ax.legend(loc="upper left", fontsize=8)
        ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(out.with_suffix(".png"), dpi=130)
    print(json.dumps({k_: v for k_, v in rep.items() if k_ not in ("te_corners",)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
