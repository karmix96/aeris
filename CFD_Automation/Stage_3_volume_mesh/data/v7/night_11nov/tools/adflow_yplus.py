"""Q7 for ADflow: y+ over the wall from ADflow's surface solution (<name>_surf.cgns, ADF), read with the repo's own
ADF reader. Wall zones are ADflow's NSWall* BC zones; YPlus is cell data with one rind layer each side, stripped
here. Statistics are over wall faces, unweighted (as SU2's over wall nodes); where the largest sits is given as x/c
of the wall faces within 1 % of the semi-span of it, and y over the semi-span.

    python adflow_yplus.py <surf.cgns> <case.json> <out.json> [design y+]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))     # CFD_Automation
from cfdauto.volume.cgns import rdata, read_adf                  # noqa: E402


def main() -> int:
    surf, case_json, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    semi = json.loads(case_json.read_text())["references"]["semi_span"]
    root, raw = read_adf(surf)
    yp, cx, cy = [], [], []
    names, zones = [], []
    for base in (n for n in root.children if n.label == "CGNSBase_t"):
        for z in (n for n in base.children if n.label == "Zone_t" and n.name.startswith("NSWall")):
            fs = next(n for n in z.children if n.label == "FlowSolution_t")
            loc = next(rdata(n, raw) for n in fs.children if n.label == "GridLocation_t")
            rind = next((rdata(n, raw) for n in fs.children if n.label == "Rind_t"), np.zeros(4, int))
            y = rdata(next(n for n in fs.children if n.name == "YPlus"), raw)
            gc = next(n for n in z.children if n.label == "GridCoordinates_t")
            X = [rdata(next(n for n in gc.children if n.name == f"Coordinate{c}"), raw) for c in "XYZ"]
            if str(loc).strip() != "CellCenter":
                raise SystemExit(f"{z.name}: YPlus at {loc}, expected CellCenter")
            r = [int(v) for v in np.ravel(rind)]
            y = y[r[0]: y.shape[0] - r[1], r[2]: y.shape[1] - r[3]]
            c = [0.25 * (a[:-1, :-1] + a[1:, :-1] + a[:-1, 1:] + a[1:, 1:]) for a in X]
            if y.shape != c[0].shape:
                raise SystemExit(f"{z.name}: YPlus {y.shape} against {c[0].shape} faces")
            yp.append(y.ravel()); cx.append(c[0].ravel()); cy.append(c[1].ravel())
            names.append(z.name)
            ys, zs = X[1], X[2]
            if abs(float(ys.min()) - semi) < 1e-6 * semi and abs(float(ys.max()) - semi) < 1e-6 * semi:
                label = "tip cap"
            elif min(X[0].shape) <= 8 and float(X[0].min()) < 0.05:
                label = "nose"
            elif min(X[0].shape) <= 8:
                label = "trailing-edge base"
            else:
                label = "side"                                  # upper or lower: decided below by the mean z
            zones.append({"zone": z.name, "label": label, "faces": int(y.size), "max": float(y.max()),
                          "p99": float(np.percentile(y, 99)), "median": float(np.median(y)),
                          "share_above_design": None, "mean_z": float(zs.mean()), "y": y.ravel()})
    yp, cx, cy = map(np.concatenate, (yp, cx, cy))
    sides = [z for z in zones if z["label"] == "side"]                          # the two big ring zones
    for z in sides:
        z["label"] = "upper side" if z["mean_z"] == max(q["mean_z"] for q in sides) else "lower side"
    design = float(sys.argv[4]) if len(sys.argv) > 4 else None
    wing = np.concatenate([z["y"] for z in zones if z["label"] in ("upper side", "lower side", "nose")])
    for z in zones:
        z["share_above_design"] = None if design is None else float(np.mean(z["y"] > design))
        del z["y"]
    i = int(np.argmax(yp))
    near = np.abs(cy - cy[i]) <= 0.01 * semi
    xle, xte = float(cx[near].min()), float(cx[near].max())
    rep = {"file": str(surf), "wall_zones": len(names), "faces": int(len(yp)), "max": float(yp[i]),
           "p99": float(np.percentile(yp, 99)), "median": float(np.median(yp)),
           "max_at_x_over_c": (float(cx[i]) - xle) / (xte - xle), "max_at_y_over_semispan": float(cy[i]) / semi,
           "share_above_1": float(np.mean(yp > 1.0)), "design": design,
           "wing_surface": {"faces": int(len(wing)), "max": float(wing.max()), "p99": float(np.percentile(wing, 99)),
                            "median": float(np.median(wing)),
                            "share_above_design": None if design is None else float(np.mean(wing > design)),
                            "note": "upper side, lower side and nose: without the trailing-edge base and the tip cap"},
           "zones": zones, "note": "cell-centred, rind stripped, unweighted over wall faces"}
    out.write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
