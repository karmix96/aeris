"""Search for SU2 settings that actually converge this geometry.

The preregistered numerics reach a limit cycle: over 3 000 iterations the density
residual oscillates between about -3.2 and -5.2 for a net drop of 1.658 orders
against a six-order gate, while CD settles to 1.8e-3.  Forces converging while
residuals do not is the signature of limiter-induced limit cycling.

This runs candidate settings on the cheap mesh, where 1 500 iterations costs
minutes rather than hours, and reports what each one actually does.  It changes
no frozen setting: every variant is an override applied on top of the real config
writer, and the results are evidence for a decision, not a decision.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2.common import atomic_write_text, load_policy  # noqa: E402
from S7_unstructured_gmsh_su2.su2_pipeline import fixed_su2_options  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / (
    "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/conv_matrix"
)

VARIANTS: dict[str, dict[str, object]] = {
    # Control: first order cannot limit-cycle, so if this converges deeply the
    # limiter is implicated and the rest of the setup is sound.
    "A_first_order": {"MUSCL_FLOW": "NO"},
    # SU2's usual external-aero practice; the policy never set this and the
    # solver is running dimensional, where residuals are not comparable.
    "B_nondim": {"REF_DIMENSIONALIZATION": "FREESTREAM_PRESS_EQ_ONE"},
    # No multigrid is configured on a 20L/30L/20L domain.
    "C_multigrid": {
        "MGLEVEL": 3,
        "MGCYCLE": "V_CYCLE",
        "MG_PRE_SMOOTH": "( 1, 2, 3, 3 )",
        "MG_POST_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_CORRECTION_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_DAMP_RESTRICTION": 0.75,
        "MG_DAMP_PROLONGATION": 0.75,
    },
    # The policy uses 0.5; SU2's default is 0.05, which limits more strongly.
    "D_venkat_005": {"VENKAT_LIMITER_COEFF": 0.05},
    # Freeze late, after the flow has developed - freezing at 400 was refuted.
    "E_freeze_late": {"LIMITER_ITER": 1200},
    "F_baseline": {},
    # Multigrid was the clear winner of the first round; these push it further.
    "G_mg_long": {
        "MGLEVEL": 3,
        "MGCYCLE": "V_CYCLE",
        "MG_PRE_SMOOTH": "( 1, 2, 3, 3 )",
        "MG_POST_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_CORRECTION_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_DAMP_RESTRICTION": 0.75,
        "MG_DAMP_PROLONGATION": 0.75,
    },
    # Multigrid plus a late limiter freeze, once multigrid has already settled
    # the field.  Freezing at 400 without multigrid was refuted.
    "H_mg_freeze": {
        "MGLEVEL": 3,
        "MGCYCLE": "V_CYCLE",
        "MG_PRE_SMOOTH": "( 1, 2, 3, 3 )",
        "MG_POST_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_CORRECTION_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_DAMP_RESTRICTION": 0.75,
        "MG_DAMP_PROLONGATION": 0.75,
        "LIMITER_ITER": 2500,
    },
    # Multigrid with a higher CFL ceiling, since multigrid tolerates more.
    "I_mg_cfl": {
        "MGLEVEL": 3,
        "MGCYCLE": "V_CYCLE",
        "MG_PRE_SMOOTH": "( 1, 2, 3, 3 )",
        "MG_POST_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_CORRECTION_SMOOTH": "( 0, 0, 0, 0 )",
        "MG_DAMP_RESTRICTION": 0.75,
        "MG_DAMP_PROLONGATION": 0.75,
        "CFL_NUMBER": 25.0,
        "CFL_ADAPT_PARAM": "( 0.1, 2.0, 5.0, 250.0 )",
    },
}
ROUND_TWO = {"G_mg_long", "H_mg_freeze", "I_mg_cfl"}


def _residual_report(directory: Path) -> dict[str, object]:
    history = directory / "history.csv"
    if not history.is_file():
        return {"error": "no history.csv"}
    rows = list(csv.reader(history.open()))
    header = [h.strip().strip('"').strip() for h in rows[0]]
    try:
        rho = header.index("rms[Rho]")
        cd = header.index("CD")
        cl = header.index("CL")
    except ValueError:
        return {"error": "columns missing"}
    data = np.array(
        [[float(r[rho]), float(r[cd]), float(r[cl])] for r in rows[1:] if len(r) > cl]
    )
    if len(data) < 10:
        return {"error": f"only {len(data)} rows"}
    tail = data[-200:]
    return {
        "iterations": int(len(data)),
        "rms_start": float(data[0, 0]),
        "rms_min": float(data[:, 0].min()),
        "rms_final": float(data[-1, 0]),
        "orders_dropped": float(data[0, 0] - data[-1, 0]),
        "best_drop": float(data[0, 0] - data[:, 0].min()),
        "cd_mean": float(tail[:, 1].mean()),
        "cd_spread": float(tail[:, 1].max() - tail[:, 1].min()),
        "cl_mean": float(tail[:, 2].mean()),
    }


def run_variant(name: str, mesh: Path, iterations: int, ranks: int) -> dict[str, object]:
    policy = load_policy()
    directory = ROOT / name
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    shutil.copy2(mesh, directory / "mesh.su2")
    options = fixed_su2_options(
        directory / "mesh.su2",
        flow=dict(policy["flow_conditions"]["baseline"]),
        references={"area_ref": 0.9610974474634779, "chord_ref": 0.5349896481665188},
        iterations=iterations,
        restart=False,
    )
    options["ITER"] = iterations
    options.update(VARIANTS[name])
    atomic_write_text(
        directory / "case.cfg",
        "\n".join(f"{k}= {v}" for k, v in sorted(options.items())) + "\n",
    )
    started = time.time()
    # The linux64 SU2 release is statically linked against MPICH.  Launching it
    # with an OpenMPI mpirun does not fail: each rank singleton-inits as rank 0
    # of its own world, so -np N silently runs N duplicate serial solves that
    # race on one history.csv.  SU2_MPI_LAUNCHER pins a matching launcher.
    launcher = os.environ.get("SU2_MPI_LAUNCHER", "mpirun")
    with (directory / "su2.log").open("w", encoding="utf-8") as log:
        code = subprocess.run(
            [launcher, "-np", str(ranks), "SU2_CFD", "case.cfg"],
            cwd=directory,
            stdout=log,
            stderr=subprocess.STDOUT,
        ).returncode
    report = {"variant": name, "exit": code, "wall_s": round(time.time() - started)}
    report.update(_residual_report(directory))
    print(json.dumps(report), flush=True)
    return report


def main() -> int:
    mesh = Path(sys.argv[1])
    iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
    ranks = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        selected = [n for n in VARIANTS if n in ROUND_TWO] if len(sys.argv) > 5 else list(VARIANTS)
        results = list(
            pool.map(lambda n: run_variant(n, mesh, iterations, ranks), selected)
        )
    (ROOT / "matrix.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\n%-16s %8s %9s %9s %10s %11s %10s" % (
        "variant", "exit", "rms_final", "drop", "best_drop", "cd_mean", "cd_spread"))
    for r in sorted(results, key=lambda x: -(x.get("best_drop") or -99)):
        if "error" in r:
            print("%-16s %8s  %s" % (r["variant"], r["exit"], r["error"]))
            continue
        print("%-16s %8d %9.3f %9.3f %10.3f %11.5f %10.2e" % (
            r["variant"], r["exit"], r["rms_final"], r["orders_dropped"],
            r["best_drop"], r["cd_mean"], r["cd_spread"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
