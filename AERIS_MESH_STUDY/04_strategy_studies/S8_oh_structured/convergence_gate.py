#!/usr/bin/env python
"""Output-based convergence gate for S8 CFD runs.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/convergence_gate.py \
        --runs 'AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd/oh_L3_fixed_a*'

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
#: Fluent judges a run equation by equation, and so does this gate. Columns of the
#: same table, and the orders each must drop.
EQUATION_COLUMNS = {"rho": 0, "rhou": 1, "rhov": 2, "rhow": 3, "rhoE": 4, "nuturb": 5}
#: Fluent's own defaults: 1e-3 for continuity, momentum and turbulence, 1e-6 for
#: energy. Measured over 77 runs of this campaign, the actual drops are
#: continuity 5.91-7.43, momentum 4.55-6.28, energy 6.12-7.48, turbulence
#: 3.32-5.33 -- so every run already clears these, and turbulence is the laggard
#: in every single one (reports/s8_equation_convergence.json). Tightening
#: turbulence to 4.0 would reject 48 of the 77, and the evidence says those are
#: converged: carrying four of them 20-40x further moved no force by more than
#: 0.073 % (reports/s8_l2_revalidation.json). So the limit is set where Fluent
#: sets it, and the force-settling test below does the fine work.
EQUATION_LIMITS = {"rho": 3.0, "rhou": 3.0, "rhov": 3.0, "rhow": 3.0,
                   "rhoE": 6.0, "nuturb": 3.0}
#: Residuals are normalised by the LARGEST value in the first five iterations,
#: which is what Fluent scales by. Iteration zero is the freestream guess, where
#: an equation can start artificially small -- nuturb starts near 7e-4 while
#: continuity starts near 9e+2 -- and dividing by it would demand a fall from
#: nowhere.
FLUENT_WINDOW = 5
#: The linear-solve residual column, read from the RAW row rather than the
#: post-column-7 slice, because it sits before the residuals.
RAW_LINRES = 6


def read_history(log: Path) -> np.ndarray | None:
    rows = [line.split() for line in log.read_text().splitlines() if ROW.match(line)]
    if len(rows) < 20:
        return None
    width = min(len(r) for r in rows)
    return np.array([[float(c) for c in r[7:width]] for r in rows])


def read_linres(log: Path) -> np.ndarray | None:
    """The linear-solve residual per iteration, when ADflow printed one.

    ADflow writes `----` for CFL and a linear residual of 1.000 when the Krylov
    solve achieves no reduction at all.  That is the definitive signature of a
    dead Newton step, and it is what actually diagnosed the gci_M NK stall --
    `Step 0.01  LinRes 1.000` -- while the residual drifted about four per cent
    and so never tripped the "residual is bit-flat" test below.  A run can have
    forces frozen to thirteen significant figures and still pass that test.
    """
    values = []
    for line in log.read_text().splitlines():
        if not ROW.match(line):
            continue
        parts = line.split()
        if len(parts) <= RAW_LINRES:
            continue
        try:
            values.append(float(parts[RAW_LINRES]))
        except ValueError:
            values.append(np.nan)
    return np.array(values) if values else None


def equation_orders(history: np.ndarray) -> dict:
    """Each equation's own drop, Fluent-style. One lagging equation can hide
    behind five healthy ones in both `totalRes` and the continuity residual."""
    out = {}
    for name, column in EQUATION_COLUMNS.items():
        if column >= history.shape[1]:
            continue
        series = np.abs(history[:, column])
        reference, final = float(series[:FLUENT_WINDOW].max()), float(series[-1])
        if not (reference > 0 and final > 0):
            continue
        orders = math.log10(reference / final)
        limit = EQUATION_LIMITS[name]
        out[name] = {"orders": orders, "limit": limit, "pass": orders >= limit,
                     "final": final, "reference_first_five": reference}
    return out


def gate(history: np.ndarray, *, window: int, min_orders: float,
         cl_pct: float, cd_pct: float, cmy_abs: float,
         linres: np.ndarray | None = None,
         l2_target: float | None = None) -> dict:
    resid = history[:, COLUMNS["resrho"]]
    tail = history[-window:]
    orders = math.log10(resid[0] / resid[-1])
    relative_residual = float(resid[-1] / resid[0])

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
    # ...or the linear solve is achieving nothing, which is the same failure with
    # a drifting residual and is invisible to the test above.
    linear_dead = False
    if linres is not None and len(linres) >= window:
        # NOT `tail`. That name is the force history this function's `spread`
        # and `rel` closures read, and rebinding it here to a 1-D linear-residual
        # slice silently broke every call to either of them made after this
        # point. Nothing called them after this point until the runaway guard
        # below was added on 2026-09-18, which is the only reason it was never
        # seen -- the failure is an IndexError, not a wrong number, so it would
        # have surfaced loudly the first time. Shadowing is the defect; the fix
        # is a name of its own.
        linres_tail = linres[-window:]
        linres_tail = linres_tail[np.isfinite(linres_tail)]
        if linres_tail.size:
            linear_dead = bool(np.median(linres_tail) > 0.99)
    frozen = frozen or linear_dead

    checks = {
        "residual_orders": {"value": orders, "limit": min_orders, "pass": orders >= min_orders},
        "cl_percent": {"value": cl_rel, "limit": cl_pct, "pass": cl_rel <= cl_pct},
        "cd_percent": {"value": cd_rel, "limit": cd_pct, "pass": cd_rel <= cd_pct},
        "cmy_absolute": {"value": cmy_a, "limit": cmy_abs, "pass": cmy_a <= cmy_abs},
        "not_diverging": {"value": diverging, "pass": not diverging},
        "no_growing_oscillation": {"value": growing_envelope, "pass": not growing_envelope},
    }
    # Two routes to acceptance, not one hurdle made of both.
    #
    # This gate exists because a strict residual cutoff alone "rejected alpha 4,
    # whose forces were stable to under 2e-8 relative" -- i.e. the force-stability
    # test was added to RESCUE runs that miss the residual target. It was then
    # applied as an ADDITIONAL requirement, so a run that hits a strict residual
    # target also had to pass a criterion built for runs that did not.
    #
    # Once the stopping target moved to 1e-6 the runs got short, and a short tail
    # is still descending monotonically, so its SPREAD over the window is
    # dominated by the approach rather than by the remaining error. Measured on
    # g12 alpha 0, which this gate rejected on a 0.107 % CL tail spread: taking
    # the same case on to 1e-8 moved CL by 0.015 % and CD by 0.018 %. The metric
    # overstated the error sevenfold, and 14 of 40 pilot runs were refused on it.
    #
    # So: a run is accepted if it MET ITS RESIDUAL TARGET and is healthy, OR if
    # it dropped enough orders and its forces settled. Health -- not diverging,
    # no growing envelope, linear solve alive -- is required either way, because
    # that is what distinguishes convergence from a solver that stopped.
    health = ("not_diverging", "no_growing_oscillation")
    healthy = all(checks[k]["pass"] for k in health)
    settled = all(checks[k]["pass"] for k in
                  ("residual_orders", "cl_percent", "cd_percent", "cmy_absolute"))
    hit_target = (l2_target is not None
                  and math.isfinite(relative_residual)
                  and relative_residual <= l2_target)
    equations = equation_orders(history)
    short = sorted(k for k, v in equations.items() if not v["pass"])
    checks["every_equation"] = {
        "value": {k: round(v["orders"], 2) for k, v in equations.items()},
        "limit": EQUATION_LIMITS, "pass": not short,
        "note": "Fluent's per-equation test: continuity, each momentum component, "
                "energy and turbulence, each against its own limit"}
    checks["residual_target_met"] = {
        "value": relative_residual, "limit": l2_target,
        "pass": bool(hit_target),
        "note": "the run reached the L2Convergence target it was given"}
    # Defect 30. The OR above is deliberate and measured -- a short tail's
    # spread is dominated by the approach, and on g12 alpha 0 it overstated the
    # error sevenfold and refused 14 of 40 good runs. But it left the residual
    # route with no force test AT ALL, and the health checks do not catch a
    # monotonic ramp. A synthetic history whose residual falls cleanly to 1e-8
    # while CL runs from -0.1 to 2.0 -- a 19 % spread over the final window --
    # is ACCEPTED, "via residual target". An external review predicted this on
    # 2026-09-16; it was reproduced against this function on 2026-09-18.
    #
    # The fix keeps the OR and adds a floor under BOTH routes. The separation is
    # wide and not delicate: the legitimate short-tail case measured 0.107 %
    # against a 0.05 % tolerance, or 2.1x, while the runaway is 380x. Twenty
    # times the tolerance sits an order of magnitude clear of each.
    RUNAWAY_MULTIPLE = 20.0
    #: A relative test alone cannot be used here, and the first version of this
    #: guard proved it by rejecting two good runs. At alpha 0 these wings carry
    #: almost no lift -- g65 sits at CL = -0.0087 -- so a tail movement of
    #: 1.8e-4 in ABSOLUTE CL reads as 2.07 % and trips a percentage test, while
    #: the actual counterexample moves 0.35 in absolute CL. Percentages are
    #: meaningless near zero, which is the same trap that made "AVL within 2 %"
    #: look false at low incidence. So a runaway must be BOTH relatively large
    #: AND absolutely material, and these floors sit between the two by more
    #: than an order of magnitude at each end.
    RUNAWAY_FLOOR = {"cl_percent": 0.01, "cd_percent": 5.0e-4, "cmy_absolute": 0.0}
    ABSOLUTE = {"cl_percent": "cl", "cd_percent": "cd", "cmy_absolute": "cmy"}
    runaway = {}
    for name, column in ABSOLUTE.items():
        value, limit = checks[name]["value"], checks[name]["limit"]
        if not math.isfinite(value) or value <= RUNAWAY_MULTIPLE * limit:
            continue
        absolute = spread(column)
        if absolute <= RUNAWAY_FLOOR[name]:
            continue
        runaway[name] = {"relative_or_absolute": round(value, 4),
                         "absolute_span": absolute,
                         "floor": RUNAWAY_FLOOR[name]}
    checks["forces_not_running_away"] = {
        "value": runaway,
        "limit": f"{RUNAWAY_MULTIPLE:g} x each settling tolerance AND above {RUNAWAY_FLOOR}",
        "pass": not runaway,
        "note": "a floor under BOTH acceptance routes: meeting a residual target "
                "says nothing about a force that is still travelling"}

    # Every equation must clear its own limit by EITHER route: a combined
    # residual or a settled force can both be reached with one equation lagging.
    passed = healthy and not short and not runaway and (hit_target or settled)
    return {
        "passes": passed,
        "solver_frozen": frozen,
        "linear_solve_dead": linear_dead,
        "accepted_via": ("residual target" if passed and hit_target else
                         "force settling" if passed else None),
        "verdict": (
            "ACCEPTED" if passed and not frozen else
            "ACCEPTED_SOLVER_FROZEN" if passed else
            "REJECTED"
        ),
        "equations_short_of_limit": short,
        "equation_orders": {k: round(v["orders"], 3) for k, v in equations.items()},
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
    ap.add_argument("--window", type=int, default=0,
                    help="iterations of force tail to judge stability over. 0 "
                         "means ADAPTIVE: min(100, max(20, 25%% of the run)). See "
                         "why below.")
    ap.add_argument("--min-orders", type=float, default=5.0)
    ap.add_argument("--cl-pct", type=float, default=0.05)
    ap.add_argument("--cd-pct", type=float, default=0.10)
    ap.add_argument("--cmy-abs", type=float, default=1.0e-4)
    ap.add_argument("--l2-target", type=float, default=None,
                    help="override the residual target; by default each run's own "
                         "l2_target is read from its result.json")
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
        # Accept both naming schemes. The refinement study writes gci_C_a-2 and
        # the pilot writes a bare a-2, and a regex requiring the underscore
        # returned None on the pilot and crashed -- so NO pilot geometry got a
        # gate verdict at all, silently, because the driver runs this as a
        # subprocess and only checks the return code loosely.
        match = re.search(r"_a(-?\d+(?:\.\d+)?)$", directory.name) or \
            re.fullmatch(r"a(-?\d+(?:\.\d+)?)", directory.name)
        if match is None:
            print(f"  skipping {directory.name}: no alpha in the directory name")
            continue
        alpha = float(match.group(1))
        # A TAIL, not a fixed count.
        #
        # The window was a flat 100 iterations. That is a tail on a run of 1300
        # and it is 65 per cent of a run of 155, and once the stopping target
        # moved to 1e-6 the runs got short: gci_M converged in 156 to 187
        # iterations, so the window reached back through most of each run into
        # the rapidly-converging approach and measured "did this run change
        # while it was converging", which is trivially yes. It rejected three of
        # four gci_M runs whose forces had in fact settled to 2e-06 over their
        # last 40 iterations.
        #
        # This is a calibration fault, not a threshold to relax, and the fix is
        # tested as one: on every run where 100 IS a tail the verdict is
        # unchanged, INCLUDING gci_C alpha 4, which stays ACCEPTED_SOLVER_FROZEN.
        # The failure mode this gate exists to catch is not blinded by it.
        window = args.window or max(20, min(100, len(history) // 4))
        # the target the run was actually given, from its own record -- not a
        # constant here, because a verification run may have been tightened
        target = args.l2_target
        result = directory / "result.json"
        if target is None and result.exists():
            try:
                target = json.loads(result.read_text()).get("l2_target")
            except (OSError, ValueError):
                target = None
        record = gate(history, window=window, min_orders=args.min_orders,
                      cl_pct=args.cl_pct, cd_pct=args.cd_pct, cmy_abs=args.cmy_abs,
                      linres=read_linres(log), l2_target=target)
        record["alpha_deg"] = alpha
        record["directory"] = str(directory)
        results.append(record)
    results.sort(key=lambda r: r["alpha_deg"])

    print(f"gate: residual >= {args.min_orders} orders, CL < {args.cl_pct} %, "
          f"CD < {args.cd_pct} %, |dCMy| < {args.cmy_abs:g}, over "
          f"{'an adaptive tail of min(100, max(20, 25%)) iterations' if not args.window else f'{args.window} iterations'}\n")
    print(f"{'alpha':>6}{'orders':>8}{'rel resid':>11}{'CL %':>9}{'CD %':>9}"
          f"{'dCMy':>10}{'iters':>7}{'win':>6}   verdict")
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
        if r.get("linear_solve_dead"):
            print(f"\n  alpha {r['alpha_deg']:g}: the LINEAR SOLVE is dead -- median "
                  f"linear residual above 0.99 over the tail, meaning the Krylov "
                  f"solve reduced nothing. The residual may still drift, so the "
                  f"flatness test alone does not see this.")
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
