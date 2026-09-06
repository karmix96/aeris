#!/usr/bin/env python
"""How the STABILITY result moves with grid refinement.  PLAN 3.4, last bullet.

    .venv/bin/python .../stability_convergence.py \
        --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*' \
        --gate AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_gci_gate.json \
        --out AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_stability_convergence.json

Why four angles and not two
----------------------------
PLAN 3.3 runs four incidences per level rather than two, and this script is the
reason.  The outputs that matter for stability are dCMy/dCL and the neutral
point, and two points define a line BY CONSTRUCTION: a two-point fit has zero
residual whether or not the relationship is linear, so it cannot tell you that
it failed.  Four points give a slope WITH a residual, at every grid level, so
the stability derivative gets a convergence study of its own instead of being
inferred from coefficients that were converged separately.

The neutral point, and the sign that was wrong once
----------------------------------------------------
    Cm(x_ref) = Cm_np + CL * (x_ref - x_np) / c   =>   x_np = x_ref - slope * c

`plot_sweep.py` carries the note: this was once written `x_ref + slope * c`,
which put the neutral point on the wrong side of the reference and inverted the
stability verdict.  The formula is written once here, with that history attached,
because PLAN 0.7 is the record of two sign errors compounding into hours of
reconciling conventions.

What refuses to happen
-----------------------
A level whose gate verdict is not ACCEPTED does not contribute a point.  PLAN
0.6: `alpha 4` held its forces stable to 9.2e-09 while its residual was frozen
to eight significant figures, because nothing was happening.  Fitting a slope
through a point like that produces a stability derivative with a confident-looking
residual and no physical content.  Excluded points are listed, never dropped
silently, and a level left with fewer than three usable angles reports that
instead of a slope.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np

#: the reference contract the CFD runs use, from solve_s8.py
X_REF_M = 0.4
C_REF_M = 0.9
FUNCTIONS = ("cl", "cd", "cdp", "cdv", "cmy")
#: fewer than this many angles and a slope is not worth quoting
MIN_POINTS = 3


def load(directory: Path) -> dict | None:
    path = directory / "result.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    short = {}
    for key, value in d.get("functions", {}).items():
        for name in FUNCTIONS:
            if key.endswith("_" + name):
                short[name] = float(value)
    d["short"] = short
    return d


def fit(x: np.ndarray, y: np.ndarray) -> dict:
    """Least squares with the residual kept, because the residual is the point."""
    coefficients, residuals, rank, _ = np.linalg.lstsq(
        np.vstack([x, np.ones_like(x)]).T, y, rcond=None)
    slope, intercept = float(coefficients[0]), float(coefficients[1])
    prediction = slope * x + intercept
    resid = y - prediction
    n = len(x)
    out = {"slope": slope, "intercept": intercept, "n_points": int(n),
           "residual_rms": float(np.sqrt(np.mean(resid ** 2))),
           "residual_max_abs": float(np.abs(resid).max())}
    denominator = float(((y - y.mean()) ** 2).sum())
    out["r_squared"] = float(1.0 - (resid ** 2).sum() / denominator) if denominator > 0 else None
    if n > 2:
        sxx = float(((x - x.mean()) ** 2).sum())
        s_err = float(np.sqrt((resid ** 2).sum() / (n - 2)))
        out["slope_standard_error"] = s_err / np.sqrt(sxx) if sxx > 0 else None
    else:
        out["slope_standard_error"] = None
        out["note"] = ("two points define a line by construction: this residual is "
                       "zero because it has to be, not because the fit is good")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--gate", type=Path, default=None)
    ap.add_argument("--allow-frozen", action="store_true",
                    help="include ACCEPTED_SOLVER_FROZEN points. A frozen solver "
                         "bounds no iterative error; a slope through one is decorative.")
    ap.add_argument("--x-ref", type=float, default=X_REF_M)
    ap.add_argument("--c-ref", type=float, default=C_REF_M)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    verdicts = {}
    if args.gate and args.gate.exists():
        for record in json.loads(args.gate.read_text())["results"]:
            verdicts[Path(record["directory"]).name] = record["verdict"]

    directories = sorted({Path(p) for pattern in args.runs for p in glob.glob(pattern)})
    levels: dict[str, list[dict]] = {}
    excluded: list[dict] = []
    for directory in directories:
        record = load(directory)
        if record is None:
            continue
        level = re.sub(r"_a-?\d+(\.\d+)?$", "", directory.name)
        verdict = verdicts.get(directory.name)
        acceptable = (verdict is None or verdict == "ACCEPTED"
                      or (args.allow_frozen and verdict.startswith("ACCEPTED")))
        entry = {"dir": directory.name, "alpha": record["alpha_deg"],
                 "verdict": verdict, **record["short"]}
        if acceptable:
            levels.setdefault(level, []).append(entry)
        else:
            excluded.append(entry)

    if excluded:
        print("excluded from every fit below:")
        for entry in excluded:
            print(f"  {entry['dir']:<18} alpha {entry['alpha']:>5.1f}  "
                  f"verdict {entry['verdict']}")
        print("  PLAN 0.6: a solver that stopped stepping holds its forces flat "
              "because nothing is happening.\n")

    report = {"plan_section": "3.4", "x_ref_m": args.x_ref, "c_ref_m": args.c_ref,
              "excluded": excluded, "levels": {}}

    print(f"{'level':>9}{'n':>4}{'dCMy/dCL':>11}{'resid rms':>12}{'R^2':>9}"
          f"{'x_np m':>9}{'dCL/dalpha':>12}")
    for level in sorted(levels, key=lambda k: len(levels[k]), reverse=True):
        points = sorted(levels[level], key=lambda p: p["alpha"])
        if len(points) < MIN_POINTS:
            print(f"{level:>9}{len(points):>4}   only {len(points)} usable angle(s); "
                  f"no slope reported")
            report["levels"][level] = {
                "n_points": len(points), "points": points,
                "condition": (f"only {len(points)} usable angle(s). A slope needs at "
                              f"least {MIN_POINTS} to carry a residual that means "
                              f"anything.")}
            continue
        cl = np.array([p["cl"] for p in points])
        cmy = np.array([p["cmy"] for p in points])
        alpha = np.array([p["alpha"] for p in points])
        moment = fit(cl, cmy)
        lift = fit(alpha, cl)
        x_np = args.x_ref - moment["slope"] * args.c_ref
        entry = {"n_points": len(points), "points": points,
                 "dCMy_dCL": moment, "dCL_dalpha_per_deg": lift,
                 "x_np_m": x_np,
                 "x_np_formula": "x_np = x_ref - (dCMy/dCL) * c_ref",
                 "static_margin_m": args.x_ref - x_np,
                 "stability": ("stable: neutral point aft of the moment reference"
                               if x_np > args.x_ref else
                               "UNSTABLE: neutral point forward of the moment reference"),
                 "condition": "ok"}
        report["levels"][level] = entry
        print(f"{level:>9}{len(points):>4}{moment['slope']:>11.5f}"
              f"{moment['residual_rms']:>12.2e}"
              f"{(moment['r_squared'] if moment['r_squared'] is not None else float('nan')):>9.5f}"
              f"{x_np:>9.4f}{lift['slope']:>12.5f}")

    usable = {k: v for k, v in report["levels"].items() if v.get("condition") == "ok"}
    if len(usable) >= 2:
        order = sorted(usable, key=lambda k: -len(usable[k]["points"]))
        # finest first is not knowable from the name alone, so order by the
        # convention the family uses: gci_C coarse, gci_M medium, gci_F fine
        rank = {"gci_CC": 0, "gci_C": 1, "gci_M": 2, "gci_MF": 3, "gci_F": 4, "gci_FF": 5}
        order = sorted(usable, key=lambda k: rank.get(k, 99))
        coarse, fine = usable[order[0]], usable[order[-1]]
        movement = {
            "coarse_level": order[0], "fine_level": order[-1],
            "dCMy_dCL": {"coarse": coarse["dCMy_dCL"]["slope"],
                         "fine": fine["dCMy_dCL"]["slope"],
                         "change": fine["dCMy_dCL"]["slope"] - coarse["dCMy_dCL"]["slope"]},
            "x_np_m": {"coarse": coarse["x_np_m"], "fine": fine["x_np_m"],
                       "change_m": fine["x_np_m"] - coarse["x_np_m"],
                       "change_percent_of_cref": 100.0 * (fine["x_np_m"] - coarse["x_np_m"]) / args.c_ref},
        }
        report["movement_with_refinement"] = movement
        print(f"\nmovement from {order[0]} to {order[-1]}:")
        print(f"  dCMy/dCL  {movement['dCMy_dCL']['coarse']:+.5f} -> "
              f"{movement['dCMy_dCL']['fine']:+.5f}   "
              f"change {movement['dCMy_dCL']['change']:+.5f}")
        print(f"  x_np      {movement['x_np_m']['coarse']:.4f} m -> "
              f"{movement['x_np_m']['fine']:.4f} m   "
              f"change {movement['x_np_m']['change_m']:+.4f} m "
              f"({movement['x_np_m']['change_percent_of_cref']:+.2f} % of c_ref)")
        if len(usable) < 3:
            print("\n  Two levels: this is the MOVEMENT, not an uncertainty on it. "
                  "No\n  observed order, no extrapolation, no band. PLAN 2.1.")
            report["statement"] = ("Two levels. The movement of the stability result "
                                   "under one refinement step, not an uncertainty "
                                   "band on it.")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
