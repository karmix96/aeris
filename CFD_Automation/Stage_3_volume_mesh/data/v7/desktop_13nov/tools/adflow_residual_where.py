"""Where an ADflow solve's density residual sits last, from its volume file (ResDensity per cell, ADF), as D1 did for
SU2 (DESKTOP_13NOV block W: "where the residual sits last").

    python adflow_residual_where.py <vol.cgns> <case.json> [<out.json>]

The share of the sum of squares held by the largest 10 and 100 cells and 0.1 % of the cells, and where the largest
100 sit: on the symmetry plane (y < 0.02 s), at the tip (y > 0.98 s), near the wall (within 0.05 of a wall face
centre... approximated here by the distance to the root-to-tip chord box), or in the far field (more than 10 mean
chords from the wing's centre); and the ten largest cells' centres.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))     # CFD_Automation
from cfdauto.volume.cgns import rdata, read_adf                  # noqa: E402


def main() -> int:
    vol, case = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
    semi = case["references"]["semi_span"]
    root, raw = read_adf(vol)
    base = next(n for n in root.children if n.label == "CGNSBase_t")
    R, C = [], []
    for z in (n for n in base.children if n.label == "Zone_t"):
        fs = next(n for n in z.children if n.label == "FlowSolution_t")
        rind = next((rdata(n, raw) for n in fs.children if n.label == "Rind_t"), np.zeros(6, int))
        r = [int(v) for v in np.ravel(rind)]
        res = rdata(next(n for n in fs.children if n.name == "ResDensity"), raw)
        res = res[tuple(slice(r[2 * k], res.shape[k] - r[2 * k + 1]) for k in range(3))]
        gc = next(n for n in z.children if n.label == "GridCoordinates_t")
        X = [rdata(next(n for n in gc.children if n.name == f"Coordinate{c}"), raw) for c in "XYZ"]
        cen = [0.125 * sum(a[i:a.shape[0] - 1 + i, j:a.shape[1] - 1 + j, k:a.shape[2] - 1 + k]
                           for i in (0, 1) for j in (0, 1) for k in (0, 1)) for a in X]
        if cen[0].shape != res.shape:
            continue
        R.append(np.abs(res).ravel()); C.append(np.stack([c.ravel() for c in cen], 1))
    R, C = np.concatenate(R), np.concatenate(C)
    o = np.argsort(R)[::-1]
    ss = float(np.sum(R ** 2)) or 1e-300
    t = C[o[:100]]
    xc = 0.5 * (C[:, 0].min() + C[:, 0].max()) if False else 1.0
    far = np.hypot(np.hypot(t[:, 0] - xc, t[:, 1]), t[:, 2]) > 10
    rep = {"cells": int(len(R)),
           "share_of_sum_of_squares": {"largest_10": float(np.sum(R[o[:10]] ** 2) / ss),
                                       "largest_100": float(np.sum(R[o[:100]] ** 2) / ss),
                                       "largest_0.1%": float(np.sum(R[o[:max(1, len(R) // 1000)]] ** 2) / ss)},
           "largest_100": {"symmetry_plane": float(np.mean(t[:, 1] < 0.02 * semi)), "tip": float(np.mean(t[:, 1] > 0.98 * semi)),
                           "far_field": float(np.mean(far)),
                           "y_over_s_quantiles_5_50_95": np.percentile(t[:, 1] / semi, [5, 50, 95]).round(3).tolist(),
                           "x_quantiles_5_50_95": np.percentile(t[:, 0], [5, 50, 95]).round(3).tolist(),
                           "z_quantiles_5_50_95": np.percentile(t[:, 2], [5, 50, 95]).round(3).tolist()},
           "largest_10_xyz": [[round(float(v), 4) for v in C[i]] for i in o[:10]]}
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
