"""Where the boundary layer separates, reattaches and turns turbulent, read from an SU2 wall file (SU2 study of
12 Nov 2026). One table per span station and side, from the wall nodes of SU2's Tecplot surface file.

    python wall_map.py <surface_flow.dat> <case.json> [<out.json>] [--stations 0.1,0.3,0.5,0.7,0.9,0.95]

Per side (upper or lower: above or below the chord line from the leading-edge node to the trailing-edge node):
- separation: the first x/c past 0.02 where the streamwise friction Skin_Friction_Coefficient_x is negative
  (the wing is unswept enough in x that x is downstream; checked against the sign of the friction upstream);
- reattachment: where it turns positive again, if it does before x/c 0.98; "to the trailing edge" otherwise;
- the friction minimum ahead of the largest friction rise (where a laminar layer turns turbulent, or reattaches);
- with LM: the first x/c where the wall's LM_gamma_eff passes 0.5.
The whole wing: SU2's friction drag against a flat plate of the same wetted area at the case's Re, laminar
(1.328 / sqrt(Re)) and turbulent (0.074 / Re^0.2), so a model's friction can be placed between the two.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np


def read_tecplot(path: Path):
    with open(path) as f:
        f.readline()
        names = re.findall(r'"([^"]+)"', f.readline())
        zone = f.readline()
        nn = int(re.search(r"NODES=\s*(\d+)", zone).group(1))
        ne = int(re.search(r"ELEMENTS=\s*(\d+)", zone).group(1))
        data = np.loadtxt(f, max_rows=nn)
        conn = np.loadtxt(f, max_rows=ne, dtype=np.int64) - 1
    return names, data, conn


def side_table(xc, cfx, gam):
    o = np.argsort(xc)
    xc, cfx = xc[o], cfx[o]
    gam = gam[o] if gam is not None else None
    m = (xc > 0.02) & (xc < 0.98)
    out = {"nodes": int(m.sum())}
    neg = np.where(m & (cfx < 0))[0]
    if len(neg):
        i0 = neg[0]
        after = np.where(m & (np.arange(len(xc)) > i0) & (cfx > 0))[0]
        out["separation_xc"] = float(xc[i0])
        out["reattachment_xc"] = float(xc[after[0]]) if len(after) else "to the trailing edge"
        out["reversed_share_of_chord"] = float(np.sum(np.diff(xc)[(cfx[:-1] < 0) & m[:-1]]))
    else:
        out["separation_xc"] = None
    k = np.where(m)[0]
    if len(k) > 3:
        d = np.diff(cfx[k])
        j = int(np.argmax(d))                                   # the largest friction rise between two nodes
        up = k[: j + 1]
        out["friction_rise_at_xc"] = float(xc[k[j + 1]])
        out["friction_min_before_rise_xc"] = float(xc[up[int(np.argmin(cfx[up]))]])
    if gam is not None:
        g = np.where(m & (gam > 0.5))[0]
        out["gamma_eff_above_0.5_from_xc"] = float(xc[g[0]]) if len(g) else None
        out["gamma_eff_max"] = float(gam[m].max()) if m.any() else None
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("surface", type=Path)
    p.add_argument("case", type=Path)
    p.add_argument("out", type=Path, nargs="?")
    p.add_argument("--stations", default="0.1,0.3,0.5,0.7,0.9,0.95")
    a = p.parse_args(argv)
    case = json.loads(a.case.read_text())
    semi, sref, re_ = case["references"]["semi_span"], case["references"]["area_ref_half"], case["reynolds"]
    names, D, Q = read_tecplot(a.surface)
    c = {n: i for i, n in enumerate(names)}
    x, y, z = D[:, c["x"]], D[:, c["y"]], D[:, c["z"]]
    cfx = D[:, c["Skin_Friction_Coefficient_x"]]
    gam = D[:, c["LM_gamma_eff"]] if "LM_gamma_eff" in c else None
    ys = np.unique(np.round(y, 6))
    rep = {"file": str(a.surface), "fields": names, "stations": []}
    for frac in [float(f) for f in a.stations.split(",")]:
        yy = ys[np.argmin(np.abs(ys / semi - frac))]
        m = np.abs(y - yy) < 1e-6
        xs, zs = x[m], z[m]
        ile, ite = int(np.argmin(xs)), int(np.argmax(xs))
        xle, zle, xte, zte = xs[ile], zs[ile], xs[ite], zs[ite]
        xc = (xs - xle) / (xte - xle)
        zchord = zle + (zte - zle) * xc
        up = zs >= zchord
        st = {"y_over_s": float(yy / semi), "chord": float(xte - xle)}
        for name, s in (("upper", up), ("lower", ~up)):
            st[name] = side_table(xc[s], cfx[m][s], gam[m][s] if gam is not None else None)
        rep["stations"].append(st)
    # the whole wing: friction drag by hand is not needed, SU2's breakdown has it; the flat-plate bounds need the area
    P = np.stack([x, y, z], 1)[Q]
    area = float(np.linalg.norm(0.5 * np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 1]), axis=1).sum())
    rep["wetted_area_over_sref"] = area / sref
    rep["flat_plate_friction_counts"] = {"laminar": 1.328 / math.sqrt(re_) * area / sref * 1e4,
                                         "turbulent": 0.074 / re_ ** 0.2 * area / sref * 1e4}
    if a.out:
        a.out.write_text(json.dumps(rep, indent=1))
    for st in rep["stations"]:
        line = [f"y/s {st['y_over_s']:.3f}"]
        for sd in ("upper", "lower"):
            t = st[sd]
            sep = t.get("separation_xc")
            line.append(f"{sd}: sep {sep:.3f}" if isinstance(sep, float) else f"{sd}: no sep")
            if isinstance(sep, float):
                r = t["reattachment_xc"]
                line.append(f"reatt {r:.3f}" if isinstance(r, float) else "reatt none")
            if "friction_rise_at_xc" in t:
                line.append(f"rise {t['friction_rise_at_xc']:.3f}")
            if gam is not None:
                g = t.get("gamma_eff_above_0.5_from_xc")
                line.append(f"gamma>0.5 {g:.3f}" if isinstance(g, float) else "gamma<0.5")
        print(" | ".join(line))
    print(json.dumps({k: rep[k] for k in ("wetted_area_over_sref", "flat_plate_friction_counts")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
