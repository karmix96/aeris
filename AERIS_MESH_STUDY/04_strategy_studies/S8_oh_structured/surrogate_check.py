"""Can AVL plus a learned correction predict CFD on a wing it has never seen?

AUDIT_2026-09-10.md next step 16. The multifidelity plan is to run AVL on every
design and correct it with a few CFD runs. Defect 23 once made the correction
look geometry-specific; that is gone. What the plan actually needs is the error
of a correction learned on nine wings and applied to the tenth, so this measures
exactly that -- leave one geometry out, ten times.

Drag is reported separately: AVL computes induced drag only, so the remainder
has to come from somewhere else, and how much it varies between wings says how
hard that somewhere else is.

    python surrogate_check.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cg_limits import C_REF, STUDY, avl_neutral_point, cfd_neutral_points, load_rows, planform


def model_errors(y: np.ndarray, x: np.ndarray, alpha: np.ndarray, geom: np.ndarray) -> dict:
    """Leave-one-geometry-out errors of three corrections of x (AVL) toward y (CFD)."""
    err = {"none": [], "offset_per_alpha": [], "linear": []}
    for g in np.unique(geom):
        test, train = geom == g, geom != g
        err["none"].append(y[test] - x[test])
        offset = {a: np.mean((y - x)[train & (alpha == a)]) for a in np.unique(alpha[test])}
        err["offset_per_alpha"].append(y[test] - (x[test] + np.array([offset[a] for a in alpha[test]])))
        k, b = np.polyfit(x[train], y[train], 1)
        err["linear"].append(y[test] - (k * x[test] + b))
    out = {}
    for name, e in err.items():
        e = np.concatenate(e)
        out[name] = {"rms": float(np.sqrt(np.mean(e ** 2))), "max_abs": float(np.max(np.abs(e)))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--level", default="gci_C")
    ap.add_argument("--out", type=Path,
                    default=HERE / "reports/s8_surrogate_check.json")
    args = ap.parse_args()

    rows = [r for r in load_rows() if r["grid_level"] == args.level
            and r.get("gate_verdict") == "ACCEPTED" and r.get("avl_cl") is not None]
    geom = np.array([r["geometry_index"] for r in rows])
    alpha = np.array([r["alpha_deg"] for r in rows])
    c_ref = {g: planform(int(g))["avl_c_ref_m"] for g in np.unique(geom)}
    cl, cl_avl = (np.array([r[k] for r in rows]) for k in ("CL", "avl_cl"))
    # AVL scales its moment by its own c_ref about the same 0.40 m point
    cm = np.array([r["CMy"] for r in rows])
    cm_avl = np.array([r["avl_cm"] * c_ref[r["geometry_index"]] / C_REF for r in rows])

    report = {"schema": "aeris.s8.surrogate_check.v1", "level": args.level,
              "rows": len(rows), "geometries": sorted(int(g) for g in np.unique(geom)),
              "method": "leave one geometry out: correction fitted on nine, error on the tenth",
              "CL": model_errors(cl, cl_avl, alpha, geom),
              "CMy_cfd_chord": model_errors(cm, cm_avl, alpha, geom)}
    lifting = np.abs(cl) > 0.1
    report["CL"]["none"]["median_relative_where_abs_cl_gt_0p1"] = float(
        np.median(np.abs((cl - cl_avl) / cl)[lifting]))

    nps = cfd_neutral_points(load_rows())
    d_np = np.array([nps[int(g)][args.level]["x_np_m"] - avl_neutral_point(int(g))["x_np_m"]
                     for g in np.unique(geom)])
    logo = [d_np[i] - np.mean(np.delete(d_np, i)) for i in range(len(d_np))]
    report["neutral_point_m"] = {
        "none": {"rms": float(np.sqrt(np.mean(d_np ** 2))), "max_abs": float(np.max(np.abs(d_np)))},
        "constant_offset": {"rms": float(np.sqrt(np.mean(np.square(logo)))),
                            "max_abs": float(np.max(np.abs(logo)))}}

    drag = {}
    for a in sorted(np.unique(alpha)):
        pick = alpha == a
        rest = np.array([r["CD"] - r["avl_cd"] for r, p in zip(rows, pick) if p])
        drag[f"{a:g}"] = {"mean": float(rest.mean()), "std": float(rest.std(ddof=1)),
                          "coefficient_of_variation": float(rest.std(ddof=1) / rest.mean())}
    report["drag_not_from_avl"] = {
        "definition": "CFD CD minus AVL induced CD, per incidence across geometries",
        "by_alpha": drag,
        "note": ("gci_C carries the chordwise CDp offset, a near-constant ~0.0027; it "
                 "shifts the mean and barely changes the spread")}

    args.out.write_text(json.dumps(report, indent=2) + "\n")
    for q in ("CL", "CMy_cfd_chord", "neutral_point_m"):
        print(f"  {q:<16}" + "  ".join(f"{k}: rms {v['rms']:.4f} max {v['max_abs']:.4f}"
                                      for k, v in report[q].items() if isinstance(v, dict)))
    for a, v in drag.items():
        print(f"  drag not from AVL, alpha {a:>2}: mean {v['mean']:.5f}  std {v['std']:.5f}"
              f"  CV {100 * v['coefficient_of_variation']:.1f}%")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
