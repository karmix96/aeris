"""SU2's wall pressure force integrated by hand from its Tecplot surface file (surface_flow.dat: nodes with
Pressure_Coefficient, Y_Plus, ..., and quad connectivity), as a check that does not trust SU2's own integration
(night of 11-12 Nov 2026: B1 reported a negative pressure drag).

    python su2_surface_forces.py <surface_flow.dat> <case.json> [<out.json>]

1. Orientation: the area vectors of the wall quads, as SU2 orders them, summed. The wing is open only at the
   symmetry plane y = 0, so a consistently oriented wall sums to (0, -A_root, 0) or (0, +A_root, 0): the x and z
   parts must vanish. Each quad is also tested against the local thickness direction (the vector from the nearest
   point of the opposite surface).
2. The pressure force: CF = -sum(Cp n A) / S_ref with n made outward, drag along (cos a, 0, sin a), lift along
   (-sin a, 0, cos a); by region (the trailing-edge base, the tip cap, the rest) so a difference can be placed.
3. y+ over the wall nodes (Q7): largest, 99 %, median, where the largest sits; on the wing surface without the base
   and the cap as well.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import numpy as np


def read_tecplot(path: Path) -> tuple[list[str], np.ndarray, np.ndarray]:
    with open(path) as f:
        f.readline()
        names = re.findall(r'"([^"]+)"', f.readline())
        zone = f.readline()
        nn = int(re.search(r"NODES=\s*(\d+)", zone).group(1))
        ne = int(re.search(r"ELEMENTS=\s*(\d+)", zone).group(1))
        data = np.loadtxt(f, max_rows=nn)
        conn = np.loadtxt(f, max_rows=ne, dtype=np.int64) - 1
    return names, data, conn


def main() -> int:
    surf, case_json = Path(sys.argv[1]), Path(sys.argv[2])
    case = json.loads(case_json.read_text())
    a = math.radians(case["alpha_deg"])
    sref, semi = case["references"]["area_ref_half"], case["references"]["semi_span"]
    names, D, Q = read_tecplot(surf)
    col = {n: i for i, n in enumerate(names)}
    X = D[:, [col["x"], col["y"], col["z"]]]
    cp = D[:, col["Pressure_Coefficient"]]
    yp = D[:, col["Y_Plus"]]
    P = X[Q]                                                    # (ne, 4, 3)
    nA = 0.5 * np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 1])   # quad area vector, as SU2 orders the nodes
    A = np.linalg.norm(nA, axis=1)
    cen = P.mean(axis=1)
    cpf = cp[Q].mean(axis=1)
    total_nA = nA.sum(axis=0)
    # outward test: the thickness direction at each face, from the nearest face centroid that faces the other way
    # is fragile on a thin trailing edge, so use the section: points at the same y (within half a station gap) and
    # the face centroid against the local mid-surface (the mean z of the section at that x)
    tip = np.abs(cen[:, 1] - semi) < 1e-6 * semi
    base_like = (nA[:, 0] / np.maximum(A, 1e-300)) > 0.9
    out = np.ones(len(Q))
    # sign of n.z against which side of the local camber the face sits on (upper faces must point up)
    order = np.argsort(cen[:, 1])
    ys = np.unique(np.round(cen[:, 1], 9))
    camber_z = np.empty(len(Q))
    for y in ys:
        m = np.abs(cen[:, 1] - y) < 1e-9 + 1e-6
        xs, zs = cen[m, 0], cen[m, 2]
        k = np.argsort(xs)
        # the mid-surface at each x: mean z of the faces nearest in x
        for idx in np.where(m)[0]:
            near = np.abs(xs - cen[idx, 0]) < 0.02 * (xs.max() - xs.min() + 1e-12)
            camber_z[idx] = 0.5 * (zs[near].max() + zs[near].min())
    side = np.sign(cen[:, 2] - camber_z)                        # +1 above the mid-surface, -1 below
    regular = ~tip & ~base_like & (np.abs(cen[:, 2] - camber_z) > 1e-9)
    agree = np.sign(nA[:, 2]) == side
    frac_out = float(np.mean(agree[regular]))
    # if most regular faces point outward the file is outward; else inward
    sense = 1.0 if frac_out >= 0.5 else -1.0
    n_out = sense * nA
    drag_dir = np.array([math.cos(a), 0.0, math.sin(a)])
    lift_dir = np.array([-math.sin(a), 0.0, math.cos(a)])
    F = -(cpf[:, None] * n_out)                                 # pressure force per face, in q*S units before / S_ref
    region = np.where(tip, "tip cap", np.where(base_like, "trailing-edge base", "wing surface"))
    rep = {"file": str(surf), "nodes": int(len(D)), "quads": int(len(Q)),
           "area_vector_sum": total_nA.tolist(), "area_vector_sum_xz_over_total_area": float(np.hypot(total_nA[0], total_nA[2]) / A.sum()),
           "faces_pointing_outward_share": frac_out if sense > 0 else 1.0 - frac_out,
           "file_orientation": "outward" if sense > 0 else "inward (flipped here)",
           "pressure_force": {}, "yplus": {}}
    for r in ("wing surface", "trailing-edge base", "tip cap", "all"):
        m = np.ones(len(Q), bool) if r == "all" else region == r
        f = F[m].sum(axis=0) / sref
        rep["pressure_force"][r] = {"faces": int(m.sum()), "area": float(A[m].sum()), "cdp": float(f @ drag_dir),
                                    "clp": float(f @ lift_dir), "cdp_counts": float(f @ drag_dir) * 1e4}
    # y+ at the nodes; the nodes of the base and the cap faces are left out of the "wing surface" set
    wing_nodes = np.zeros(len(D), bool)
    wing_nodes[np.unique(Q[region == "wing surface"])] = True
    other = np.zeros(len(D), bool)
    other[np.unique(Q[region != "wing surface"])] = True
    for name, m in (("all wall nodes", np.ones(len(D), bool)), ("wing surface", wing_nodes & ~other)):
        i = int(np.argmax(np.where(m, yp, -1)))
        rep["yplus"][name] = {"nodes": int(m.sum()), "max": float(yp[i]), "p99": float(np.percentile(yp[m], 99)),
                              "median": float(np.median(yp[m])), "max_at_xyz": X[i].tolist(),
                              "max_at_y_over_semispan": float(X[i, 1] / semi),
                              "share_above_1.3": float(np.mean(yp[m] > 1.3)), "share_above_1.0": float(np.mean(yp[m] > 1.0))}
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
