#!/usr/bin/env python
"""One ADflow SA point on a Stage 3 case (case.py wrote case.json and adflow_options.json).

    mpirun -np 6 python solve/run_adflow.py --case runs/v7_a4 --preflight    # reads the grid, no iteration
    mpirun -np 6 python solve/run_adflow.py --case runs/v7_a4                # the solve -> runs/v7_a4/adflow/result.json
    mpirun -np 6 python solve/run_adflow.py --case runs/v7_a4 --lift-distribution 150 --slices 0.5,0.9,0.95,0.98

Pieces copied from S8 (solve_s8.py, preflight_adflow.py), not imported: the freestream is read back from ADflow and
checked before the solve (liftIndex 3: span +y, lift +z; S8 defect 14 turned alpha into sideslip); the residual is
totalrfinal / totalr0 (S8 defect 16); a run with fewer than 10 iterations or forces out of range is not converged;
the options that reached the solver are read back into result.json. The peak memory of every rank is summed into
result.json ("memory": decision 113).
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

DIRECTION_TOLERANCE = 1.0e-9
MIN_ITERATIONS = 10
BOUNDS = {"cl": (-3.0, 3.0), "cd": (0.0, 0.5), "cdp": (-0.05, 0.5), "cdv": (0.0, 0.1), "cmy": (-3.0, 3.0)}


def verify_flow_directions(solver, alpha_deg: float, lift_index: int = 3) -> dict:
    """Fail closed unless ADflow built velDir = (cos a, 0, sin a) and liftDir = (-sin a, 0, cos a)."""
    import numpy as np
    a = np.radians(alpha_deg)
    want_vel, want_lift = np.array([np.cos(a), 0.0, np.sin(a)]), np.array([-np.sin(a), 0.0, np.cos(a)])
    try:
        ph = solver.adflow.inputphysics
        got_vel = np.array(ph.veldirfreestream, dtype=float).ravel()[:3]
        got_lift = np.array(ph.liftdirection, dtype=float).ravel()[:3]
        got_index = int(ph.liftindex)
    except Exception as exc:                                   # unverifiable is a failure
        raise SystemExit(f"cannot read the freestream back from ADflow ({exc}): not running") from exc
    ev, el = float(np.linalg.norm(got_vel - want_vel)), float(np.linalg.norm(got_lift - want_lift))
    rep = {"lift_index": got_index, "velocity_direction": got_vel.tolist(), "lift_direction": got_lift.tolist(),
           "velocity_error": ev, "lift_error": el}
    if got_index != lift_index or max(ev, el) > DIRECTION_TOLERANCE:
        raise SystemExit(f"freestream is not the one asked for: {rep}. A y-component is sideslip on this mesh.")
    return rep


def peak_memory(comm, cells: int | None) -> dict:
    """Peak resident memory of the run, summed over the MPI ranks (ru_maxrss, kB on Linux), against S8's two laws
    (decisions 112, 113: the laws are two-point fits at 0.57 and 1.11 M cells; this is the third point)."""
    import resource
    mine = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0 ** 2          # GiB
    try:
        every = comm.gather(mine, root=0) or [mine]
    except Exception:
        every = [mine]
    out = {"ranks": len(every), "peak_rss_gib_sum": float(sum(every)), "peak_rss_gib_largest_rank": float(max(every))}
    if cells:
        m = cells / 1.0e6
        out |= {"cells": int(cells), "gib_per_million_cells": out["peak_rss_gib_sum"] / m,
                "law_ank_only_gib": 2.69 + 7.23 * m, "law_ank_then_nk_gib": 1.51 + 9.46 * m}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", type=Path, required=True, help="the folder case.py wrote")
    ap.add_argument("--preflight", action="store_true", help="read and partition the grid, report, no iteration")
    ap.add_argument("--set-option", action="append", default=[], metavar="KEY=VALUE",
                    help="any other ADflow option (recorded in result.json)")
    ap.add_argument("--lift-distribution", type=int, default=0, metavar="N",
                    help="after the solve: the spanwise lift distribution in N segments along y (lift_distribution.dat)")
    ap.add_argument("--slices", default="", metavar="F1,F2,...",
                    help="after the solve: Cp slices at these fractions of the semi-span (slices.dat), e.g. 0.5,0.9,0.98")
    a = ap.parse_args()
    case = json.loads((a.case / "case.json").read_text())
    opts = json.loads((a.case / "adflow_options.json").read_text())
    over = {}
    for item in a.set_option:
        k, _, v = item.partition("=")
        try:
            over[k] = json.loads(v)
        except json.JSONDecodeError:
            over[k] = v
    if a.preflight:
        opts |= {"nCycles": 0, "writeVolumeSolution": False, "writeSurfaceSolution": False, "printIterations": False}
    opts |= over
    out = Path(opts["outputDirectory"])                        # after the overrides: a second run can have its own folder
    out.mkdir(parents=True, exist_ok=True)

    from adflow import ADFLOW
    from baseclasses import AeroProblem

    t0 = time.time()
    solver = ADFLOW(options=opts)
    r = case["references"]
    ap_ = AeroProblem(name=f"v7_a{case['alpha_deg']:g}", alpha=case["alpha_deg"], beta=0.0, mach=case["mach"],
                      reynolds=case["reynolds"], reynoldsLength=case["reynolds_length"], T=case["temperature_K"],
                      areaRef=r["area_ref_half"], chordRef=r["chord_ref"], xRef=r["moment_ref"][0],
                      yRef=r["moment_ref"][1], zRef=r["moment_ref"][2], evalFuncs=["cl", "cd", "cmy", "cdp", "cdv"])
    solver.setAeroProblem(ap_)
    directions = verify_flow_directions(solver, case["alpha_deg"])
    if a.preflight:
        rep = {"accepted": True, "families": sorted(solver.families.keys()), "directions": directions,
               "seconds": round(time.time() - t0, 1)}
        try:
            rep["wall_surface_nodes"] = int(solver.getSurfaceCoordinates(groupName="wall").shape[0])
        except Exception as e:                                 # reported, not swallowed
            rep["wall_surface_nodes"] = f"unavailable: {e}"
        rep["memory"] = peak_memory(solver.comm, case.get("cells"))
        (out / "preflight.json").write_text(json.dumps(rep, indent=1))
        print(json.dumps(rep, indent=1))
        return 0
    solver(ap_)
    funcs = {}
    solver.evalFunctions(ap_, funcs)
    coef = {k.split("_")[-1]: float(v) for k, v in funcs.items()}
    try:
        it = solver.adflow.iteration
        residual, src = float(it.totalrfinal / it.totalr0), "adflow.iteration.totalrfinal/totalr0"
    except Exception as e:                                     # never assumed converged
        residual, src = None, f"unavailable: {e}"
    try:
        done = int(solver.adflow.iteration.itertot)
    except Exception:
        done = None
    try:
        failed = bool(solver.adflow.killsignals.routinefailed)
    except Exception:
        failed = None
    bad = {k: v for k, v in coef.items() if k in BOUNDS and not (math.isfinite(v) and BOUNDS[k][0] <= v <= BOUNDS[k][1])}
    eff = {}
    for k in ("equationType", "turbulenceModel", "eddyVisInfRatio", "liftIndex", "useANKSolver", "useNKSolver",
              "L2Convergence", "nCycles", "MGCycle", "ANKSubspaceSize", "ANKPCILUFill", "ANKASMOverlap"):
        try:
            eff[k] = solver.getOption(k)
        except Exception:
            pass
    res = {"case": case["mesh"], "solver": "ADflow", "model": "SA", "alpha_deg": case["alpha_deg"],
           "converged": residual is not None and residual <= opts["L2Convergence"] and not bad and
           (done is None or done >= MIN_ITERATIONS) and not failed,
           "relative_residual": residual, "residual_source": src, "iterations": done, "routine_failed": failed,
           "implausible": bad or None, "coefficients": coef, "directions": directions, "options_effective": eff,
           "overrides": over, "seconds": round(time.time() - t0, 1),
           "memory": peak_memory(solver.comm, case.get("cells"))}
    try:
        hist = solver.getConvergenceHistory()
        res["history"] = {k: [float(x) for x in v] for k, v in hist.items()
                          if k.lower() in ("iter", "totalres", "resrho", "cl", "cd", "cmy", "cdp", "cdv")}
    except Exception as e:
        res["history"] = f"unavailable: {e}"
    (out / "result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "history"}, indent=1))
    if a.lift_distribution or a.slices:
        # Added 11 Nov 2026 for the tip comparison of decision 114; not tested on ADflow when written. It runs after
        # result.json is on disk, so a failure here cannot lose the solve: it is recorded in result.json["extras"].
        extras = {}
        try:
            if a.lift_distribution:
                solver.addLiftDistribution(a.lift_distribution, "y")
            if a.slices:
                fr = [float(f) for f in a.slices.split(",") if f.strip()]
                solver.addSlices("y", [f * r["semi_span"] for f in fr])
                extras["slice_fractions"] = fr
            if a.lift_distribution:
                solver.writeLiftDistributionFile(str(out / "lift_distribution.dat"))
                extras["lift_distribution"] = f"{a.lift_distribution} segments along y: lift_distribution.dat"
            if a.slices:
                solver.writeSlicesFile(str(out / "slices.dat"))
                extras["slices"] = "slices.dat"
        except Exception as e:                                 # recorded, the solve stands
            extras["error"] = f"{type(e).__name__}: {e}"
        res["extras"] = extras
        (out / "result.json").write_text(json.dumps(res, indent=1))
        print(json.dumps({"extras": extras}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
