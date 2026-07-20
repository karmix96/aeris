#!/usr/bin/env python
"""ADflow smoke test for AERIS pyHyp volume meshes (WP1 of DSE_READINESS.md).

Runs a single RANS point on a wing_vol_*.cgns half-model mesh and reports
convergence + force coefficients + post-solve y+. Must run inside the
mach-aero conda environment, e.g.:

    conda activate mach-aero
    mpirun -np 8 python scripts/adflow_smoke.py \
        --grid data/meshes/bwb_cap4_L4/surface/wing_vol_L4.cgns \
        --output-dir data/meshes/bwb_cap4_L4/adflow \
        --area-ref 1.094 --chord-ref 0.8774

areaRef must be the HALF-model reference area (mesh is a half wing with a
symmetry plane); chordRef the mean aerodynamic chord.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adflow import ADFLOW
from baseclasses import AeroProblem
from mpi4py import MPI


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--area-ref", type=float, required=True, help="Half-model reference area [m^2].")
    p.add_argument("--chord-ref", type=float, required=True, help="Mean aerodynamic chord [m].")
    p.add_argument("--alpha", type=float, default=2.0)
    p.add_argument("--mach", type=float, default=0.2)
    p.add_argument("--reynolds", type=float, default=1.0e6)
    p.add_argument("--temperature", type=float, default=288.15)
    p.add_argument("--l2-convergence", type=float, default=1.0e-8)
    p.add_argument("--n-cycles", type=int, default=20000)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if MPI.COMM_WORLD.rank == 0:
        print(
            "[adflow_smoke] DEPRECATED: this script is superseded by "
            "'aeris cfd solve --grid ... --output-dir ... --area-ref ... "
            "--chord-ref ...' (full option authority + provenance manifests). "
            "It keeps working, but new options land in the adapter only.",
            flush=True,
        )
    out_dir = args.output_dir.expanduser().resolve()
    if MPI.COMM_WORLD.rank == 0:
        out_dir.mkdir(parents=True, exist_ok=True)
    MPI.COMM_WORLD.barrier()

    options = {
        # I/O
        "gridFile": str(args.grid.expanduser().resolve()),
        "outputDirectory": str(out_dir),
        "monitorVariables": ["resrho", "resturb", "cl", "cd"],
        "surfaceVariables": ["cp", "cf", "yplus", "vx", "vy", "vz"],
        "writeTecplotSurfaceSolution": False,
        # Physics
        "equationType": "RANS",
        "liftIndex": 3,  # span is y, lift is z
        # Solver: single grid (tip collar blocks are 2 cells wide -> no MG),
        # ANK from the start, NK for the final orders.
        "MGCycle": "sg",
        "useANKSolver": True,
        "ANKSwitchTol": 1.0,
        "useNKSolver": True,
        "NKSwitchTol": 1.0e-6,
        "nCycles": args.n_cycles,
        "L2Convergence": args.l2_convergence,
    }

    ap = AeroProblem(
        name="smoke",
        alpha=args.alpha,
        mach=args.mach,
        reynolds=args.reynolds,
        reynoldsLength=args.chord_ref,
        T=args.temperature,
        areaRef=args.area_ref,
        chordRef=args.chord_ref,
        evalFuncs=["cl", "cd", "cmy"],
    )

    solver = ADFLOW(options=options)
    solver(ap)

    funcs: dict[str, float] = {}
    solver.evalFunctions(ap, funcs)
    solver.checkSolutionFailure(ap, funcs)

    if MPI.COMM_WORLD.rank == 0:
        report = {
            "grid": options["gridFile"],
            "alpha_deg": args.alpha,
            "mach": args.mach,
            "reynolds": args.reynolds,
            "area_ref_half": args.area_ref,
            "chord_ref": args.chord_ref,
            "solve_failed": bool(funcs.get("fail", False)),
            "functions": {k: float(v) for k, v in funcs.items() if k != "fail"},
        }
        (out_dir / "adflow_smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("\n[adflow_smoke] " + json.dumps(report["functions"], indent=2))
        print(f"[adflow_smoke] solve_failed = {report['solve_failed']}")
        print(f"[adflow_smoke] report -> {out_dir / 'adflow_smoke.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
