#!/usr/bin/env python
"""Measure ADflow's peak RSS on a grid, for a stated solver configuration.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/measure_memory.py \
        --grid <volume.cgns> --ranks 6 --cycles 25 --nk-switch-tol 0.1

Why this exists.  The memory column of the grid-family table was one MEASURED
point at 567,256 cells and three LINEAR EXTRAPOLATIONS from it at 10,632
bytes/cell.  That is not the same thing, and an external reviewer said so.
Extrapolating a per-cell cost is wrong in both directions at once: fixed
overhead (Python, MPI, PETSc, the CGNS read) does not scale with cells, so the
marginal cost per cell is LOWER than the small-mesh average; while the
measurement it was taken from stayed in the ANK phase and never allocated the
Newton-Krylov subspace, so it understates the peak of a real run.

`--nk-switch-tol` forces Newton-Krylov to engage almost immediately, so a short
run reaches the phase that actually sets the peak. The default of 0.1 does that;
production uses 1e-6.

RSS is summed across every ADflow process on this host once per second, which is
what a single workstation actually has to supply. It is not divided by ranks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MACH = "/home/mike/miniconda3/envs/mach-aero/bin"


def sample_rss(stop: threading.Event, out: dict, interval: float = 1.0) -> None:
    peak = 0
    trace = []
    while not stop.is_set():
        try:
            ps = subprocess.run(["ps", "-eo", "rss,args", "--no-headers"],
                                capture_output=True, text=True, timeout=10)
            total = 0
            for line in ps.stdout.splitlines():
                if "adflow" in line or "_probe_runner" in line:
                    if "grep" in line or "measure_memory" in line:
                        continue
                    total += int(line.split(None, 1)[0])
            if total:
                trace.append(total)
                peak = max(peak, total)
        except Exception:  # noqa: BLE001 - sampling must never kill the run
            pass
        stop.wait(interval)
    out["peak_kb"] = peak
    out["trace_kb"] = trace


RUNNER = '''
import json, sys
from adflow import ADFLOW
from baseclasses import AeroProblem
opts = json.loads(sys.argv[1])
solver = ADFLOW(options=opts)
ap = AeroProblem(name="_probe_runner", alpha=0.0, beta=0.0, mach=0.0837,
                 reynolds=1530708.188575197, reynoldsLength=0.9, T=278.4,
                 areaRef=0.394918242017589, chordRef=0.9,
                 xRef=0.4, yRef=0.0, zRef=0.0, evalFuncs=["cl", "cd"])
solver(ap)
funcs = {}
solver.evalFunctions(ap, funcs)
print("PROBE_FUNCS " + json.dumps({k: float(v) for k, v in funcs.items()}))
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grid", type=Path, required=True)
    ap.add_argument("--ranks", type=int, default=6)
    ap.add_argument("--cycles", type=int, default=25)
    ap.add_argument("--nk-switch-tol", type=float, default=0.1,
                    help="0.1 engages NK almost at once so the peak is reached; "
                         "production uses 1e-6")
    ap.add_argument("--nk-subspace", type=int, default=20)
    ap.add_argument("--nk-ilu-fill", type=int, default=1)
    ap.add_argument("--ank-only", action="store_true",
                    help="disable NK entirely, the configuration a 5-order "
                         "output-based gate may not need NK for")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    workdir = HERE / "runs/s8_memory"
    workdir.mkdir(parents=True, exist_ok=True)
    options = {
        "gridFile": str(args.grid), "outputDirectory": str(workdir),
        "equationType": "RANS", "turbulenceModel": "SA", "liftIndex": 3,
        "MGCycle": "sg", "useANKSolver": True, "ANKSwitchTol": 1.0,
        "useNKSolver": not args.ank_only,
        "NKSwitchTol": args.nk_switch_tol,
        "ANKSubspaceSize": 10, "NKSubspaceSize": args.nk_subspace,
        "ANKPCILUFill": 1, "NKPCILUFill": args.nk_ilu_fill,
        "L2Convergence": 1.0e-12, "nCycles": args.cycles,
        "writeVolumeSolution": False, "writeSurfaceSolution": False,
        "printTiming": False, "monitorVariables": ["resrho", "cl", "cd"],
    }
    runner = workdir / "_probe_runner.py"
    runner.write_text(RUNNER)

    stop = threading.Event()
    result: dict = {}
    watcher = threading.Thread(target=sample_rss, args=(stop, result))
    watcher.start()
    started = time.time()
    proc = subprocess.run(
        [f"{MACH}/mpirun", "-np", str(args.ranks), f"{MACH}/python",
         str(runner), json.dumps(options)],
        capture_output=True, text=True, cwd=REPO,
    )
    elapsed = time.time() - started
    stop.set()
    watcher.join()

    import re
    rows = [l for l in proc.stdout.splitlines() if re.match(r"^ +1 +\d+ +\d+ ", l)]
    phases = sorted({l.split()[3] for l in rows}) if rows else []
    peak_kb = result.get("peak_kb", 0)
    cells = None
    for line in proc.stdout.splitlines():
        m = re.search(r"Total Number of Cells\s*:\s*(\d+)", line)
        if m:
            cells = int(m.group(1))
    record = {
        "grid": str(args.grid), "ranks": args.ranks, "cells": cells,
        "requested_cycles": args.cycles, "iterations_run": len(rows),
        "solver_phases_seen": phases,
        "nk_switch_tol": args.nk_switch_tol, "nk_subspace": args.nk_subspace,
        "nk_ilu_fill": args.nk_ilu_fill, "ank_only": args.ank_only,
        "peak_rss_kb": peak_kb,
        "peak_rss_gib": peak_kb / 1048576.0,
        "bytes_per_cell": (peak_kb * 1024.0 / cells) if cells else None,
        "wall_time_s": round(elapsed, 1),
        "returncode": proc.returncode,
        "note": "peak RSS summed over every ADflow process on this host, not "
                "divided by ranks: this is what one workstation must supply",
    }
    if not phases or "NK" not in " ".join(phases):
        record["warning"] = ("Newton-Krylov never engaged, so this peak does NOT "
                             "include the Krylov subspace allocation")
    print(json.dumps(record, indent=2))
    out = args.out or (workdir / f"mem_{args.grid.stem}_{args.ranks}r.json")
    out.write_text(json.dumps(record, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
