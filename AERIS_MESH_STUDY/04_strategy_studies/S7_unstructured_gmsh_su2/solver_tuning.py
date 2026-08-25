"""Search SU2 settings for one that actually converges, on a mesh small enough to iterate.

The coarse mesh takes 8.7 s an iteration and needs hundreds, so one experiment is
hours and a search is impossible.  The smoke mesh is 42 745 cells and about a
second an iteration, which turns the same search into minutes per experiment.  The
settings that fix a stall generally transfer; the resolution that fixes an accuracy
claim does not, so nothing here is an accuracy result and the winner must be
re-confirmed at coarse resolution before it is believed.

The configuration S7 has been running is deliberately conservative - implicit Euler,
CFL capped at 100, ten linear iterations, LU-SGS - and never enabled the
Newton-Krylov path SU2 8 provides, which is the same class of method S6's policy
already names for ADflow.  That is the main hypothesis under test.

    python solver_tuning.py <case.json> [--iterations N] [--workers N] [--smoke]

`--smoke` runs every variant for a few iterations only, to prove each one starts
before a long run is committed to.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# Every variant carries multigrid: it was the clear winner of the earlier search
# and the question now is what else is needed on top of it.
MULTIGRID: dict[str, Any] = {
    "MGLEVEL": 3,
    "MGCYCLE": "V_CYCLE",
    "MG_PRE_SMOOTH": "( 1, 2, 3, 3 )",
    "MG_POST_SMOOTH": "( 0, 0, 0, 0 )",
    "MG_CORRECTION_SMOOTH": "( 0, 0, 0, 0 )",
    "MG_DAMP_RESTRICTION": 0.75,
    "MG_DAMP_PROLONGATION": 0.75,
}

# Newton-Krylov replaces the fixed-CFL implicit march with an inexact Newton
# solve, which is what usually breaks a residual stall of this shape.
NEWTON_KRYLOV: dict[str, Any] = {"NEWTON_KRYLOV": "YES"}

# A stronger preconditioner and more Krylov iterations: ten is few for an implicit
# RANS step, and an under-solved linear system stalls the outer iteration.
STRONG_LINEAR: dict[str, Any] = {
    "LINEAR_SOLVER_PREC": "ILU",
    "LINEAR_SOLVER_ILU_FILL_IN": 0,
    "LINEAR_SOLVER_ITER": 25,
}

# The CFL ceiling of 100 is modest for an implicit scheme; the ramp is what makes
# the residual crawl for hundreds of iterations before it moves.
HIGH_CFL: dict[str, Any] = {
    "CFL_NUMBER": 25.0,
    "CFL_ADAPT_PARAM": "( 0.1, 2.0, 1.0, 1000.0 )",
}

# POLICY.yaml su2.convergence, quoted not redefined.  A variant is only
# interesting if it can satisfy BOTH; see the stop-residual note in main().
GATE_DROP_ORDERS = 6.0
GATE_FINAL_LOG10 = -8.0

VARIANTS: dict[str, dict[str, Any]] = {
    "A_baseline": {**MULTIGRID},
    "B_newton_krylov": {**MULTIGRID, **NEWTON_KRYLOV},
    "C_strong_linear": {**MULTIGRID, **STRONG_LINEAR},
    "D_high_cfl": {**MULTIGRID, **HIGH_CFL},
    "E_quasi_newton": {**MULTIGRID, "QUASI_NEWTON_NUM_SAMPLES": 10},
    "F_nk_linear": {**MULTIGRID, **NEWTON_KRYLOV, **STRONG_LINEAR},
    "G_nk_cfl": {**MULTIGRID, **NEWTON_KRYLOV, **HIGH_CFL},
    "H_linear_cfl": {**MULTIGRID, **STRONG_LINEAR, **HIGH_CFL},
    "I_combined": {**MULTIGRID, **NEWTON_KRYLOV, **STRONG_LINEAR, **HIGH_CFL},
    # No multigrid, to check it is still earning its place once the rest improves.
    "J_nk_no_mg": {**NEWTON_KRYLOV, **STRONG_LINEAR, **HIGH_CFL},
}


def _history(directory: Path) -> dict[str, Any]:
    path = directory / "history.csv"
    if not path.is_file():
        return {"error": "no history.csv"}
    rows = list(csv.reader(path.open()))
    if len(rows) < 3:
        return {"error": f"history has {len(rows)} rows"}
    header = [h.strip().strip('"') for h in rows[0]]

    def column(name: str) -> list[float]:
        if name not in header:
            return []
        out = []
        for row in rows[1:]:
            try:
                out.append(float(row[header.index(name)]))
            except (ValueError, IndexError):
                pass
        return out

    rms = column("rms[Rho]")
    if not rms:
        return {"error": "no rms[Rho] column"}
    cl, cd = column("CL"), column("CD")
    tail = cd[-100:] if len(cd) > 100 else cd
    return {
        "iterations": len(rms),
        "rms_final": rms[-1],
        "orders_dropped": rms[0] - rms[-1],
        "best_drop": rms[0] - min(rms),
        "cd_final": cd[-1] if cd else None,
        "cl_final": cl[-1] if cl else None,
        "cd_tail_spread": (max(tail) - min(tail)) if len(tail) > 1 else None,
        # The two frozen residual conditions, reported separately: they can fail
        # for opposite reasons and a single pass/fail hides which one bit.
        "gate_final_ok": rms[-1] <= GATE_FINAL_LOG10,
        "gate_orders_ok": (rms[0] - rms[-1]) >= GATE_DROP_ORDERS,
    }


def run_variant(
    name: str,
    root: Path,
    case: dict[str, Any],
    iterations: int,
    timeout_s: int,
    stop_residual: float,
) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from S7_unstructured_gmsh_su2 import su2_pipeline as su2

    directory = root / name
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)

    options = su2.fixed_su2_options(
        Path(case["mesh"]),
        flow={"mach": 0.2, "alpha": 2.0, "reynolds": 1.0e6, "temperature": 288.15},
        references={"area_ref": case["area_ref"], "chord_ref": case["chord_ref"]},
        iterations=iterations,
        restart=False,
    )
    options.update(VARIANTS[name])
    # Deliberately BELOW the acceptance bar.  fixed_su2_options derives
    # CONV_RESIDUAL_MINVAL from residual_log10_final_max, so the solver halts the
    # instant it touches the bar and the achievable drop is capped at
    # initial + 8 -- which is 5.4 orders here, against a gate of 6.0.  Measuring
    # what a variant CAN reach requires the stop to sit below what the gate asks.
    options["CONV_RESIDUAL_MINVAL"] = stop_residual
    (directory / "case.cfg").write_text(
        "\n".join(f"{k}= {v}" for k, v in options.items()) + "\n", encoding="utf-8"
    )

    started = time.time()
    try:
        completed = subprocess.run(
            ["SU2_CFD", "case.cfg"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        code = completed.returncode
        (directory / "run.log").write_text(completed.stdout, encoding="utf-8")
        if completed.stderr:
            (directory / "run.err").write_text(completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired:
        code = -9
    report = {"variant": name, "exit": code, "wall_s": round(time.time() - started)}
    report.update(_history(directory))
    print(json.dumps(report), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="case.json holding mesh path and references")
    parser.add_argument("--iterations", type=int, default=4000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--smoke", action="store_true", help="30 iterations, prove each starts")
    parser.add_argument(
        "--stop-residual",
        type=float,
        default=-12.0,
        help="CONV_RESIDUAL_MINVAL for the solver; must sit below the -8 gate bar",
    )
    args = parser.parse_args()

    case = json.loads(args.case.read_text(encoding="utf-8"))
    iterations = 30 if args.smoke else args.iterations
    root = args.case.parent / ("smoke" if args.smoke else "runs")
    root.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(
                lambda n: run_variant(
                    n, root, case, iterations, args.timeout, args.stop_residual
                ),
                VARIANTS,
            )
        )
    (root / "matrix.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n%-18s %6s %8s %9s %10s %11s %12s %6s" % (
        "variant", "exit", "iters", "drop", "best_drop", "cd_final", "cd_spread",
        "gate"))
    for r in sorted(results, key=lambda x: -(x.get("best_drop") or -99)):
        if "error" in r:
            print("%-18s %6s  %s" % (r["variant"], r["exit"], r["error"]))
            continue
        gate = "PASS" if (r["gate_final_ok"] and r["gate_orders_ok"]) else "fail"
        print("%-18s %6d %8d %9.3f %10.3f %11.6f %12.2e %6s" % (
            r["variant"], r["exit"], r["iterations"], r["orders_dropped"],
            r["best_drop"], r["cd_final"] or float("nan"),
            r["cd_tail_spread"] or float("nan"), gate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
