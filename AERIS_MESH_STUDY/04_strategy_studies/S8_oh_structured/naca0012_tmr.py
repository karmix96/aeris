"""NACA 0012 at low speed: does the S8 solver get drag right where AERIS flies?

AUDIT_2026-09-10.md next step 10, the biggest gap: nothing checked S8's drag at
AERIS's speed. The ONERA M6 is transonic and measured pressures only.

NASA's Turbulence Modeling Resource (now tmbwg.github.io/turbmodels) defines a
verification case at M 0.15, Re 6e6, alpha 10 deg whose SA answer three
independent codes -- CFL3D, FUN3D, TAU -- have grid-converged on grids up to
7169 x 2049: lift to 0.02 %, drag to 0.02 %. That is a KNOWN ANSWER for the
exact turbulence model S8 runs, at low speed.

What this verifies: ADflow, SA, the campaign's solver configuration (ANK only,
1e-6) and the force integration, on drag, at low Mach -- the solver half of S8.
What it cannot: the S8 mesher (a 2D O-grid is not an O-H wing grid), or
turbulence-model error (the reference is SA as well; see
transition_sensitivity.py for that).

The TMR repository carries only its two coarsest grids, so this builds a
systematically refined O-grid family with pyHyp -- the MACH-Aero route to 2D
cases -- and extrapolates it. Two single-change runs on the o1024 grid test
things every S8 run shares:
  * freestream turbulence: ADflow's default eddyVisInfRatio 0.009 is SA chi ~1.3,
    where the TMR prescribes chi = 3 (ratio 0.21) so that SA's ft2 term cannot
    hold part of the boundary layer laminar;
  * AERIS's own Mach number, 0.0837, on a compressible solver without low-Mach
    preconditioning: lift should follow Prandtl-Glauert and drag barely move.

    mach python naca0012_tmr.py grid
    mpirun -np 6 mach python naca0012_tmr.py solve --grid .../o1024.cgns --out ...
    python naca0012_tmr.py compare
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "AERIS_MESH_STUDY/artifacts/tmr_naca0012"
REPORT = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_naca0012_tmr.json"

#: TMR verification case, naca0012numerics_val.html. T ref 540 R.
CASE = {"mach": 0.15, "reynolds": 6.0e6, "reynolds_length": 1.0,
        "temperature_K": 300.0, "alpha_deg": 10.0}
#: SA without the point-vortex far-field correction (ADflow has none), Family II,
#: the range across CFL3D, FUN3D and TAU on the finest three grids.
#: naca0012numerics_val_sa_withoutpv.html, saved in external/tmr_naca0012/.
REFERENCE = {"CL": (1.09085, 1.09103), "CD": (0.0122715, 0.0122740),
             "CM": (0.00677, 0.00680), "CDp": (0.006066, 0.006068),
             "CDv": (0.0062057, 0.0062061)}
#: cells around the airfoil; a quarter as many off the wall; first cell halves
#: with each doubling, so every level is the same grid at a different spacing
LEVELS = {"o256": 256, "o512": 512, "o1024": 1024, "o2048": 2048}
S0_AT_1024 = 1.0e-6          # y+ ~0.2 at Re 6e6
FARFIELD_CHORDS = 500.0      # as the TMR grids, which the no-PV values assume
LIFT_INDEX = 2               # airfoil in x-y, span along z
AERIS_MACH = 0.0837


def naca0012(x: np.ndarray) -> np.ndarray:
    """The TMR's sharp-trailing-edge NACA 0012, closed exactly at x = 1."""
    return 0.594689181 * (0.298222773 * np.sqrt(x) - 0.127125232 * x
                          - 0.357907906 * x ** 2 + 0.291984971 * x ** 3
                          - 0.105174606 * x ** 4)


def surface_loop(cells: int) -> np.ndarray:
    """Trailing edge -> upper -> leading edge -> lower -> trailing edge.

    That direction, with the second surface index along +z, makes the surface
    normal point into the flow, which is the side pyHyp marches toward.
    Cosine spacing clusters points at both edges.
    """
    x = 0.5 * (1.0 - np.cos(np.pi * np.linspace(0.0, 1.0, cells // 2 + 1)))
    y = naca0012(x)
    upper = np.column_stack([x[::-1], y[::-1]])
    lower = np.column_stack([x[1:], -y[1:]])
    return np.vstack([upper, lower])


def write_surface(path: Path, loop: np.ndarray) -> None:
    """Formatted PLOT3D, one block, the loop at z = 0 and z = 1."""
    n = len(loop)
    columns = (np.tile(loop[:, 0], 2), np.tile(loop[:, 1], 2),
               np.repeat([0.0, 1.0], n))
    with open(path, "w") as fh:
        fh.write(f"1\n{n} 2 1\n")
        for values in columns:
            fh.write("\n".join(f"{v:.16e}" for v in values) + "\n")


def cmd_grid(args) -> int:
    from pyhyp import pyHyp

    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "grid_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    for name in args.levels:
        cells = LEVELS[name]
        surface = OUT / f"{name}_surface.xyz"
        write_surface(surface, surface_loop(cells))
        s0 = S0_AT_1024 * 1024 / cells
        hyp = pyHyp(options={
            "inputFile": str(surface), "fileType": "PLOT3D",
            "unattachedEdgesAreSymmetry": False, "outerFaceBC": "farfield",
            "autoConnect": True,
            "BC": {1: {"jLow": "zSymm", "jHigh": "zSymm"}},
            "families": "wall",
            "N": cells // 4 + 1, "s0": s0, "marchDist": FARFIELD_CHORDS,
            "ps0": -1.0, "pGridRatio": -1.0, "cMax": 3.0,
            "epsE": 1.0, "epsI": 2.0, "theta": 3.0,
            "volCoef": 0.25, "volBlend": 0.0001, "volSmoothIter": 100,
        })
        hyp.run()
        cgns = OUT / f"{name}.cgns"
        hyp.writeCGNS(str(cgns))
        report[name] = {"cgns": str(cgns), "cells": cells * (cells // 4),
                        "cells_around": cells, "cells_normal": cells // 4,
                        "first_cell": s0, "farfield_chords": FARFIELD_CHORDS}
        print(f"  {name}: {report[name]['cells']:,} cells, s0 {s0:.2e}")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return 0


def cmd_solve(args) -> int:
    """One point with the CAMPAIGN's option set; only the case must differ."""
    from adflow import ADFLOW
    from baseclasses import AeroProblem

    args.out.mkdir(parents=True, exist_ok=True)
    overrides: dict = {}
    if args.no_nk:
        overrides["useNKSolver"] = False
    if args.eddy_vis_inf_ratio is not None:
        overrides["eddyVisInfRatio"] = args.eddy_vis_inf_ratio
    # Nonlinear-solver settings only (subspace, fill, switch points): they change
    # the path to the converged solution, never the solution itself.
    for item in args.set:
        key, _, value = item.partition("=")
        try:
            overrides[key] = json.loads(value)
        except json.JSONDecodeError:
            overrides[key] = value
    options = {
        "gridFile": str(args.grid), "outputDirectory": str(args.out),
        "equationType": "RANS", "turbulenceModel": "SA",
        "liftIndex": LIFT_INDEX,
        "MGCycle": "sg",
        "useANKSolver": True, "ANKSwitchTol": 1.0,
        "useNKSolver": True, "NKSwitchTol": 1.0e-6,
        "ANKSubspaceSize": 10, "NKSubspaceSize": 20,
        "ANKPCILUFill": 1, "NKPCILUFill": 1,
        "L2Convergence": args.l2, "nCycles": args.n_cycles,
        "timeLimit": args.time_limit,
        "storeConvHist": True,
        "writeVolumeSolution": False, "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resturb", "cl", "cd", "cdp", "cdv"],
        "surfaceVariables": ["cp", "cf", "yplus"],
        **overrides,
    }
    solver = ADFLOW(options=options)
    problem = AeroProblem(
        name="n0012", alpha=args.alpha, beta=0.0, mach=args.mach,
        reynolds=CASE["reynolds"], reynoldsLength=CASE["reynolds_length"],
        T=CASE["temperature_K"], areaRef=1.0, chordRef=1.0,
        xRef=0.25, yRef=0.0, zRef=0.0,
        evalFuncs=["cl", "cd", "cdp", "cdv", "cmz"])
    solver.setAeroProblem(problem)

    a = np.radians(args.alpha)
    physics = solver.adflow.inputphysics
    got = np.array(physics.veldirfreestream, dtype=float).ravel()[:3]
    error = float(np.linalg.norm(got - [np.cos(a), np.sin(a), 0.0]))
    if int(physics.liftindex) != LIFT_INDEX or error > 1.0e-9:
        raise SystemExit(f"freestream direction {got} is not alpha {args.alpha} in "
                         f"the x-y plane. Not running.")

    solver(problem)
    funcs: dict = {}
    solver.evalFunctions(problem, funcs)
    try:
        iteration = solver.adflow.iteration
        residual = float(iteration.totalrfinal / iteration.totalr0)
    except Exception:  # noqa: BLE001 - never assumed converged
        residual = None
    f = {k.split("_")[-1]: float(v) for k, v in funcs.items()}
    result = {"case": {**CASE, "mach": args.mach, "alpha_deg": args.alpha},
              "grid": str(args.grid), "relative_residual": residual,
              "l2_target": args.l2,
              "converged": residual is not None and residual <= args.l2,
              "solver_overrides": overrides, "functions": funcs,
              # about the quarter chord, nose-up positive as the TMR reports it:
              # with x aft, y up and z the span, nose-up is NEGATIVE about +z
              "coefficients": {"CL": f["cl"], "CD": f["cd"], "CDp": f["cdp"],
                               "CDv": f["cdv"], "CM": -f["cmz"]}}
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["coefficients"], indent=2))
    return 0


def richardson(f1: float, f2: float, f3: float, r: float = 2.0) -> dict:
    """Celik et al. 2008 on a constant-ratio triplet, finest first."""
    e21, e32 = f2 - f1, f3 - f2
    if e21 == 0 or e32 == 0 or e32 / e21 <= 0:
        return {"monotone": False}
    p = float(np.log(abs(e32 / e21)) / np.log(r))
    extrapolated = f1 + (f1 - f2) / (r ** p - 1)
    return {"monotone": True, "observed_order": p, "extrapolated": float(extrapolated),
            "gci_fine_pct": float(100 * 1.25 * abs(e21 / f1) / (r ** p - 1))}


#: judged against the campaign's stopping rule, not the tighter target these runs
#: asked for: o512 stopped on the cycle budget at 5.7e-8, far inside the rule
CAMPAIGN_L2 = 1.0e-6


def load(name: str) -> dict | None:
    path = OUT / "runs" / name / "result.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    res = result.get("relative_residual")
    return result if res is not None and res <= CAMPAIGN_L2 else {**result, "unconverged": True}


def cmd_compare(args) -> int:
    family = {name: load(f"{name}_m0.15") for name in LEVELS}
    family = {k: v for k, v in family.items() if v and not v.get("unconverged")}
    names = [n for n in LEVELS if n in family]
    report: dict = {"schema": "aeris.s8.naca0012_tmr.v1", "case": CASE,
                    "reference_sa_no_point_vortex": REFERENCE,
                    "levels": {n: family[n]["coefficients"] for n in names}}
    print(f"{'grid':>7}" + "".join(f"{k:>11}" for k in REFERENCE))
    for n in names:
        print(f"{n:>7}" + "".join(f"{family[n]['coefficients'][k]:>11.6f}" for k in REFERENCE))
    mid = {k: sum(v) / 2 for k, v in REFERENCE.items()}
    print(f"{'TMR':>7}" + "".join(f"{mid[k]:>11.6f}" for k in REFERENCE))

    verdict = {}
    finest = names[-1] if names else None
    for key in REFERENCE:
        entry = {"finest_grid": finest}
        if finest:
            value = family[finest]["coefficients"][key]
            entry["finest_value"] = value
            entry["finest_vs_reference_pct"] = 100 * (value - mid[key]) / mid[key]
        if len(names) >= 3:
            f1, f2, f3 = (family[n]["coefficients"][key] for n in names[-1:-4:-1])
            entry["richardson_finest_three"] = rich = richardson(f1, f2, f3)
            if rich.get("monotone"):
                entry["extrapolated_vs_reference_pct"] = (
                    100 * (rich["extrapolated"] - mid[key]) / mid[key])
        verdict[key] = entry
    report["verification"] = verdict

    base = load("o1024_m0.15")
    sensitivity = {}
    for name, label in (("o1024_m0.15_chi3", "freestream chi 3 (TMR) vs ADflow default"),
                        (f"o1024_m{AERIS_MACH:g}", f"M {AERIS_MACH} (AERIS) vs M 0.15")):
        other = load(name)
        if base and other and not other.get("unconverged"):
            delta = {k: 100 * (other["coefficients"][k] - base["coefficients"][k])
                     / base["coefficients"][k] for k in ("CL", "CD", "CDp", "CDv")}
            sensitivity[name] = {"label": label, "percent_change": delta}
            print(f"  {label}: " + "  ".join(f"{k} {v:+.2f}%" for k, v in delta.items()))
    beta = lambda m: np.sqrt(1 - m ** 2)  # noqa: E731
    sensitivity["prandtl_glauert_cl_change_pct"] = 100 * (beta(0.15) / beta(AERIS_MACH) - 1)
    report["sensitivity_on_o1024"] = sensitivity

    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    for key, v in verdict.items():
        line = f"  {key:>4}: finest {v.get('finest_vs_reference_pct', float('nan')):+.2f}%"
        if "extrapolated_vs_reference_pct" in v:
            line += (f", extrapolated {v['extrapolated_vs_reference_pct']:+.2f}% "
                     f"(p {v['richardson_finest_three']['observed_order']:.2f})")
        print(line + " vs TMR")
    print(f"  wrote {REPORT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid")
    g.add_argument("--levels", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    s = sub.add_parser("solve")
    s.add_argument("--grid", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--alpha", type=float, default=CASE["alpha_deg"])
    s.add_argument("--mach", type=float, default=CASE["mach"])
    s.add_argument("--l2", type=float, default=1.0e-6)
    s.add_argument("--n-cycles", type=int, default=30000)
    s.add_argument("--time-limit", type=float, default=10800.0)
    s.add_argument("--no-nk", action="store_true")
    s.add_argument("--eddy-vis-inf-ratio", type=float, default=None)
    s.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="extra ADflow option, recorded as an override")
    sub.add_parser("compare")
    args = ap.parse_args()
    return {"grid": cmd_grid, "solve": cmd_solve, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
