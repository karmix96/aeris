#!/usr/bin/env python
"""Auto-generated static ADflow runner (aeris.cfd) — options come from
adflow_options.json / adflow_case.json next to this script; this file
bakes in nothing.  Run: mpirun -np N <mach-aero python> run_adflow.py"""
import json
import time
from pathlib import Path

import numpy


def main():
    here = Path(__file__).parent
    options = json.loads((here / "adflow_options.json").read_text())
    case = json.loads((here / "adflow_case.json").read_text())

    from adflow import ADFLOW
    from baseclasses import AeroProblem
    from mpi4py import MPI

    t0 = time.time()
    ap = AeroProblem(
        name=case["name"],
        alpha=case["alpha"],
        mach=case["mach"],
        reynolds=case["reynolds"],
        reynoldsLength=case["reynolds_length_ref"],
        T=case["temperature"],
        areaRef=case["area_ref"],
        chordRef=case["chord_ref"],
        xRef=case["moment_reference"][0] if case["moment_reference"] is not None else None,
        yRef=case["moment_reference"][1] if case["moment_reference"] is not None else None,
        zRef=case["moment_reference"][2] if case["moment_reference"] is not None else None,
        evalFuncs=case["eval_funcs"],
    )
    solver = ADFLOW(options=options)
    solver(ap)

    # Preserve the full native convergence history, including force and
    # pressure/viscous-drag tails.  ADflow owns the column definitions, so this
    # is safer than reconstructing a variable-width monitor table from stdout.
    history = solver.getConvergenceHistory()
    serial_history = {}
    for key, values in history.items():
        array = numpy.asarray(values)
        serial_history[str(key)] = array.tolist()

    history_by_key = {key.casefold(): values for key, values in serial_history.items()}

    def final_history_value(key):
        values = history_by_key.get(key.casefold())
        if not isinstance(values, list) or not values:
            return None
        return float(values[-1])

    native_residual_final = {
        "density": final_history_value("RSDMassRMS"),
        "momentum_x": final_history_value("RSDMomentumXRMS"),
        "momentum_y": final_history_value("RSDMomentumYRMS"),
        "momentum_z": final_history_value("RSDMomentumZRMS"),
        "energy": final_history_value("RSDEnergyStagnationDensityRMS"),
        "sa": final_history_value("RSDTurbulentSANuTildeRMS"),
    }
    momentum_values = [
        native_residual_final[name]
        for name in ("momentum_x", "momentum_y", "momentum_z")
        if native_residual_final[name] is not None
    ]
    native_residual_components = {
        "density": native_residual_final["density"],
        "momentum": max(momentum_values) if len(momentum_values) == 3 else None,
        "energy": native_residual_final["energy"],
        "sa": native_residual_final["sa"],
    }

    # The nonlinear residual vector is cell-major with `nw` states per cell:
    # rho, three momentum equations, energy, then turbulence equations.  Store
    # globally reduced component L2 norms so acceptance never depends on the
    # density/turbulence monitor columns alone.
    residual = numpy.asarray(solver.getResidual(ap), dtype=float)
    nstate = int(solver.adflow.flowvarrefstate.nw)
    if nstate < 5 or residual.size % nstate:
        raise RuntimeError(
            f"unexpected ADflow residual layout: size={residual.size}, nstate={nstate}"
        )
    residual = residual.reshape((-1, nstate))
    local_sumsq = numpy.sum(residual * residual, axis=0)
    global_sumsq = MPI.COMM_WORLD.allreduce(local_sumsq, op=MPI.SUM)
    local_rho_sum = float(numpy.sum(residual[:, 0]))
    local_rho_abs = float(numpy.sum(numpy.abs(residual[:, 0])))
    global_rho_sum = MPI.COMM_WORLD.allreduce(local_rho_sum, op=MPI.SUM)
    global_rho_abs = MPI.COMM_WORLD.allreduce(local_rho_abs, op=MPI.SUM)
    residual_vector_component_l2 = {
        "density": float(numpy.sqrt(global_sumsq[0])),
        "momentum": float(numpy.sqrt(numpy.sum(global_sumsq[1:4]))),
        "energy": float(numpy.sqrt(global_sumsq[4])),
        "sa": float(numpy.sqrt(numpy.sum(global_sumsq[5:]))) if nstate > 5 else None,
    }
    mass_imbalance_normalized = abs(global_rho_sum) / max(global_rho_abs, 1.0e-300)

    funcs = {}
    solver.evalFunctions(ap, funcs)
    solver.checkSolutionFailure(ap, funcs)

    secondary_funcs = None
    secondary_reference = case.get("secondary_moment_reference")
    if secondary_reference is not None:
        primary_reference = case["moment_reference"]
        ap.xRef, ap.yRef, ap.zRef = secondary_reference
        secondary_funcs = {}
        solver.evalFunctions(ap, secondary_funcs)
        ap.xRef, ap.yRef, ap.zRef = primary_reference

    if MPI.COMM_WORLD.rank == 0:
        report = {
            "schema": "aeris.cfd.adflow_run.v1",
            "solve_failed": bool(funcs.get("fail", False)),
            "functions": {k: float(v) for k, v in funcs.items() if k != "fail"},
            "secondary_reference_functions": (
                None
                if secondary_funcs is None
                else {k: float(v) for k, v in secondary_funcs.items() if k != "fail"}
            ),
            "convergence_history": serial_history,
            "residual_components_final": native_residual_components,
            "residual_component_monitor_final": native_residual_final,
            "residual_components_definition": (
                "ADflow native RMS convergence monitors; momentum is the maximum "
                "of the x/y/z component RMS values"
            ),
            "residual_vector_component_l2_diagnostic": residual_vector_component_l2,
            "mass_imbalance_normalized": float(mass_imbalance_normalized),
            "mass_imbalance_definition": (
                "abs(sum continuity residual)/sum(abs continuity residual)"
            ),
            "elapsed_seconds": time.time() - t0,
        }
        (here / "adflow_run.json").write_text(json.dumps(report, indent=2))
        print("[run_adflow] " + json.dumps(report["functions"]))
        print(f"[run_adflow] solve_failed = {report['solve_failed']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
