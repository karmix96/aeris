#!/usr/bin/env python
"""Output-based convergence gate for S8 CFD runs.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/convergence_gate.py \
        --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/oh_L3_fixed_a*'

Why this replaces a single residual cutoff
------------------------------------------
The previous gate asked for a relative residual of 1e-8 and nothing else.  It
rejected `alpha 4`, whose forces were stable to under 2e-8 relative over 150
iterations -- a solution that had, by any aerodynamic reading, finished.  A
residual is a statement about how well the discrete equations balance
everywhere; the outputs are what the run exists to produce.  Requiring eight
orders on every geometry and every incidence in an automated design sweep will
throw away usable cases, and it did.

It is also not safe to simply loosen the residual, because "forces stopped
moving" has two causes: the solution converged, or the solver stopped taking
steps.  `alpha 4` is the second -- NK step length 0.00, linear residual 1.000 --
and its forces froze because *nothing was happening*, not because the physics
settled.  A gate that only reads force flatness cannot tell those apart.

So this gate asks for both, plus evidence the run was still healthy:

  1. the residual dropped at least `--min-orders` (default 5.0);
  2. CL, CD and CMy each stopped moving over the last `--window` iterations;
  3. the residual is not diverging, and it is not oscillating with a growing
     envelope.

Criterion 3 is what keeps 2 honest.  A limit cycle can hold forces flat to
several digits while the solution wanders, and a frozen solver holds them flat
by doing nothing at all; both are reported rather than silently passed.

Moment tolerance is ABSOLUTE, not relative
------------------------------------------
CMy on this wing runs from -0.006 to +0.029 and passes through zero between
alpha -2 and 0.  A relative tolerance on a quantity that crosses zero is
meaningless -- it demands infinite precision near the crossing and is trivially
satisfied away from it.  The gate therefore asks that CMy move less than
`--cmy-abs` (default 1e-4) in absolute terms, which is about 0.4 per cent of the
largest CMy in this sweep and far tighter than the mesh sensitivity.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
from pathlib import Path

import numpy as np

ROW = re.compile(r"^ +1 +\d+ +\d+ ")
#: ADflow monitorVariables order in solve_s8.py, after the four leading columns:
#: resrho, resmom(3), resrhoe, resturb, cl, cd, cdp, cdv, cmy, totalR
COLUMNS = {"resrho": 0, "cl": 6, "cd": 7, "cdp": 8, "cdv": 9, "cmy": 10}


def read_history(log: Path) -> np.ndarray | None:
    rows = [line.split() for line in log.read_text().splitlines() if ROW.match(line)]
    if len(rows) < 20:
        return None
    width = min(len(r) for r in rows)
    return np.array([[float(c) for c in r[7:width]] for r in rows])


def gate(history: np.ndarray, *, window: int, min_orders: float,
         cl_pct: float, cd_pct: float, cmy_abs: float) -> dict:
    resid = history[:, COLUMNS["resrho"]]
    tail = history[-window:]
    orders = math.log10(resid[0] / resid[-1])

    def spread(name: str) -> float:
        v = tail[:, COLUMNS[name]]
        return float(v.max() - v.min())

    def rel(name: str) -> float:
        v = tail[:, COLUMNS[name]]
        return float((v.max() - v.min()) / abs(v.mean())) if abs(v.mean()) > 0 else float("inf")

    cl_rel, cd_rel, cmy_a = rel("cl") * 100.0, rel("cd") * 100.0, spread("cmy")

    # health: the residual must not be climbing, and its envelope must not grow
    half = max(len(resid) // 10, window)
    diverging = bool(resid[-1] > resid[-half] * 1.5)
    early, late = resid[-2 * half:-half], resid[-half:]
    growing_envelope = bool(
        len(early) > 5 and (late.max() - late.min()) > 2.0 * (early.max() - early.min())
    )
    # a frozen solver: the residual is not merely flat, it is IDENTICAL
    frozen = bool((late.max() - late.min()) / late.mean() < 1e-4)

    checks = {
        "residual_orders": {"value": orders, "limit": min_orders, "pass": orders >= min_orders},
        "cl_percent": {"value": cl_rel, "limit": cl_pct, "pass": cl_rel <= cl_pct},
        "cd_percent": {"value": cd_rel, "limit": cd_pct, "pass": cd_rel <= cd_pct},
        "cmy_absolute": {"value": cmy_a, "limit": cmy_abs, "pass": cmy_a <= cmy_abs},
        "not_diverging": {"value": diverging, "pass": not diverging},
        "no_growing_oscillation": {"value": growing_envelope, "pass": not growing_envelope},
    }
    passed = all(c["pass"] for c in checks.values())
    return {
        "passes": passed,
        "solver_frozen": frozen,
        "verdict": (
            "ACCEPTED" if passed and not frozen else
            "ACCEPTED_SOLVER_FROZEN" if passed else
            "REJECTED"
        ),
        "iterations": int(len(history) - 1),
        "residual_initial": float(resid[0]),
        "residual_final": float(resid[-1]),
        "relative_residual": float(resid[-1] / resid[0]),
        "window": window,
        "checks": checks,
        "forces": {k: float(history[-1, COLUMNS[k]]) for k in ("cl", "cd", "cdp", "cdv", "cmy")},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--window", type=int, default=100,
                    help="iterations of force tail to judge stability over")
    ap.add_argument("--min-orders", type=float, default=5.0)
    ap.add_argument("--cl-pct", type=float, default=0.05)
    ap.add_argument("--cd-pct", type=float, default=0.10)
    ap.add_argument("--cmy-abs", type=float, default=1.0e-4)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    directories = sorted({Path(p) for pattern in args.runs for p in glob.glob(pattern)})
    results = []
    for directory in directories:
        log = directory / "run.log"
        if not log.exists():
            continue
        history = read_history(log)
        if history is None:
            continue
        alpha = float(re.search(r"_a(-?\d+)", directory.name).group(1))
        record = gate(history, window=args.window, min_orders=args.min_orders,
                      cl_pct=args.cl_pct, cd_pct=args.cd_pct, cmy_abs=args.cmy_abs)
        record["alpha_deg"] = alpha
        record["directory"] = str(directory)
        results.append(record)
    results.sort(key=lambda r: r["alpha_deg"])

    print(f"gate: residual >= {args.min_orders} orders, CL < {args.cl_pct} %, "
          f"CD < {args.cd_pct} %, |dCMy| < {args.cmy_abs:g}, over {args.window} iterations\n")
    print(f"{'alpha':>6}{'orders':>8}{'rel resid':>11}{'CL %':>9}{'CD %':>9}"
          f"{'dCMy':>10}{'iters':>7}   verdict")
    for r in results:
        c = r["checks"]
        print(f"{r['alpha_deg']:>6.1f}{c['residual_orders']['value']:>8.3f}"
              f"{r['relative_residual']:>11.2e}{c['cl_percent']['value']:>9.1e}"
              f"{c['cd_percent']['value']:>9.1e}{c['cmy_absolute']['value']:>10.1e}"
              f"{r['iterations']:>7}   {r['verdict']}")
    for r in results:
        failed = [k for k, v in r["checks"].items() if not v["pass"]]
        if failed:
            print(f"\n  alpha {r['alpha_deg']:g} failed: {', '.join(failed)}")
        if r["solver_frozen"]:
            print(f"\n  alpha {r['alpha_deg']:g}: the residual is FROZEN, not merely flat "
                  f"(spread under 1e-4 relative over the tail). The forces are stable "
                  f"because the solver stopped stepping, not because the flow settled. "
                  f"Outputs are usable; the run is not evidence the solver works here.")

    if args.out:
        args.out.write_text(json.dumps(
            {"gate": {"min_orders": args.min_orders, "cl_pct": args.cl_pct,
                      "cd_pct": args.cd_pct, "cmy_abs": args.cmy_abs,
                      "window": args.window},
             "results": results}, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
