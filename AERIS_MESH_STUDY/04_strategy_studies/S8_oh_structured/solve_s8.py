#!/usr/bin/env python
"""Run one ADflow point on the S8 O-H grid.  NOT AUTHORIZED — see RUNBOOK_cfd.md.

    mpirun -np 6 python solve_s8.py --grid ..._volume.cgns --alpha 0.0 --out <dir>

Operating point is `mission_authority_v1.yaml` verbatim and solver settings
follow `policies/m2_a_c03_canary_v4.yaml`, so a result from this is comparable
with the C03 measurements rather than being a separate experiment.

The script refuses to run unless `--i-have-authorization` is passed, because
`05_s6_cfd_qualification/POLICY.yaml` blocks heavy work and S8 has no policy
entry yet.  That flag is a record that a human decided, not a formality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

#: mission_authority_v1.yaml, authority_id s6_nominal_mission_20260830
MISSION = {
    "mach": 0.0837,
    "reynolds": 1530708.188575197,
    "reynolds_length_m": 0.9,
    "temperature_K": 278.4,
    "chord_ref_m": 0.9,
}
#: the C03 reference contract, unchanged, so the numbers are comparable
AREA_REF_M2 = 0.394918242017589
MOMENT_REF_XYZ = (0.4, 0.0, 0.0)


#: AERIS meshes span +y and lift +z.  ADflow's default is 2 (lift +y), which for
#: this geometry turns angle of attack into sideslip.  Matches
#: src/aeris/cfd/solvers/adflow/options_schema.py and the governed C03 canary.
LIFT_INDEX = 3

#: how far the realised freestream may sit from the requested one, in radians of
#: direction error.  This is a correctness check, not a tolerance to tune.
DIRECTION_TOLERANCE = 1.0e-9


def verify_flow_directions(solver, alpha_deg: float) -> dict:
    """Check that ADflow built the freestream this geometry actually asked for.

    Setting `liftIndex` is one line and one line can be dropped again.  This
    reads back what the solver *built* and refuses to spend the run if it does
    not match the analytic expectation for a span-+y, lift-+z wing:

        velDirFreeStream = ( cos a, 0, sin a )
        liftDirection    = (-sin a, 0, cos a )

    The check runs after `setAeroProblem` and before the solve, so a wrong
    setup costs seconds rather than hours.  It is fail-closed: if the arrays
    cannot be read, that is a failure, not a pass, because an unverifiable
    freestream is exactly the state this defect lived in for a day.
    """
    import numpy as np

    a = np.radians(alpha_deg)
    want_vel = np.array([np.cos(a), 0.0, np.sin(a)])
    want_lift = np.array([-np.sin(a), 0.0, np.cos(a)])
    try:
        physics = solver.adflow.inputphysics
        got_vel = np.array(physics.veldirfreestream, dtype=float).ravel()[:3]
        got_lift = np.array(physics.liftdirection, dtype=float).ravel()[:3]
        got_index = int(physics.liftindex)
    except Exception as exc:  # noqa: BLE001 - unverifiable is a failure
        raise SystemExit(
            f"cannot read back the freestream direction from ADflow ({exc}). "
            f"Refusing to run: an unverified freestream is what defect 14 was."
        ) from exc

    vel_error = float(np.linalg.norm(got_vel - want_vel))
    lift_error = float(np.linalg.norm(got_lift - want_lift))
    report = {
        "lift_index_requested": LIFT_INDEX,
        "lift_index_realised": got_index,
        "alpha_deg": float(alpha_deg),
        "velocity_direction_expected": want_vel.tolist(),
        "velocity_direction_realised": got_vel.tolist(),
        "velocity_direction_error": vel_error,
        "lift_direction_expected": want_lift.tolist(),
        "lift_direction_realised": got_lift.tolist(),
        "lift_direction_error": lift_error,
        "tolerance": DIRECTION_TOLERANCE,
    }
    if got_index != LIFT_INDEX or max(vel_error, lift_error) > DIRECTION_TOLERANCE:
        raise SystemExit(
            "freestream direction is not what this geometry asked for.\n"
            f"  liftIndex   requested {LIFT_INDEX}, realised {got_index}\n"
            f"  velDir      want {want_vel.round(9).tolist()} "
            f"got {got_vel.round(9).tolist()}  error {vel_error:.3e}\n"
            f"  liftDir     want {want_lift.round(9).tolist()} "
            f"got {got_lift.round(9).tolist()}  error {lift_error:.3e}\n"
            "A y-component in the velocity direction is SIDESLIP on this mesh, "
            "and the root symmetry plane forbids it. Not running."
        )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grid", type=Path, required=True)
    ap.add_argument("--alpha", type=float, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--area-ref", type=float, default=AREA_REF_M2,
                    help="solver half area in m2, from the study's reference contract")
    ap.add_argument("--time-limit", type=float, default=21600.0)
    ap.add_argument("--l2", type=float, default=1.0e-8)
    # 4000 was carried over from the canary policy and is far too small here:
    # it caps the CUMULATIVE linear-iteration counter, and both first runs hit
    # it at 4004 and 4028, stopping at 4.6e-6 and 1.5e-5 relative instead of the
    # 1e-8 asked for. ADflow exits cleanly when it does that, and
    # `routine_failed` stays false, so an unconverged run looks exactly like a
    # converged one unless the residual is checked.
    ap.add_argument("--n-cycles", type=int, default=30000)
    ap.add_argument("--i-have-authorization", action="store_true")
    args = ap.parse_args()

    if not args.i_have_authorization:
        raise SystemExit(
            "refusing to run: pass --i-have-authorization. The record for this "
            "run is POLICY.yaml heavy_work.exceptions.run-s8-first-point, "
            "policies/s8_oh_first_point_v1.yaml and ADR-0018."
        )

    from adflow import ADFLOW
    from baseclasses import AeroProblem

    args.out.mkdir(parents=True, exist_ok=True)
    solver = ADFLOW(options={
        "gridFile": str(args.grid),
        "outputDirectory": str(args.out),
        "equationType": "RANS",
        "turbulenceModel": "SA",
        # AERIS meshes span +y and lift +z, so alpha must rotate the freestream
        # in the x-z plane.  ADflow's own default is 2, which rotates it in x-y
        # -- into the SPANWISE direction, against a root symmetry plane that
        # forbids exactly that.  Omitting this line is defect 14; see
        # reports/s8_lift_index_defect_20260904.json.  The governed C03 canary
        # sets 3 (studies/canary/.../adflow_options.json) and this run is only
        # comparable with it if this run does too.
        "liftIndex": LIFT_INDEX,
        "MGCycle": "sg",
        "useANKSolver": True,
        "ANKSwitchTol": 1.0,
        "useNKSolver": True,
        # ADflow's default is 1e-5, which hands the flow to Newton-Krylov ten
        # times earlier than the governed policy asks.  The alpha 0 run switched
        # at a relative residual of 1.85e-5 on the default and converged; that
        # is not evidence the default is safe, only that one case survived it.
        "NKSwitchTol": 1.0e-6,
        "ANKSubspaceSize": 10,
        "NKSubspaceSize": 20,
        "ANKPCILUFill": 1,
        "NKPCILUFill": 1,
        "L2Convergence": args.l2,
        "nCycles": args.n_cycles,
        "timeLimit": args.time_limit,
        "storeConvHist": True,
        # A long run with no volume solution cannot be restarted, so hitting the
        # budget means starting over. Both first runs did exactly that.
        "writeVolumeSolution": True,
        "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resmom", "resrhoe", "resturb",
                             "cl", "cd", "cmy", "cdp", "cdv"],
        "surfaceVariables": ["cp", "cf", "yplus", "vx", "vy", "vz"],
    })
    problem = AeroProblem(
        name=f"s8_a{args.alpha:g}",
        alpha=args.alpha,
        beta=0.0,
        mach=MISSION["mach"],
        reynolds=MISSION["reynolds"],
        reynoldsLength=MISSION["reynolds_length_m"],
        T=MISSION["temperature_K"],
        areaRef=args.area_ref,
        chordRef=MISSION["chord_ref_m"],
        xRef=MOMENT_REF_XYZ[0],
        yRef=MOMENT_REF_XYZ[1],
        zRef=MOMENT_REF_XYZ[2],
        evalFuncs=["cl", "cd", "cmy", "cdp", "cdv"],
    )
    # Build the state, check it, and only then spend the run.
    solver.setAeroProblem(problem)
    directions = verify_flow_directions(solver, args.alpha)

    solver(problem)
    funcs: dict = {}
    solver.evalFunctions(problem, funcs)
    try:
        failed = bool(solver.adflow.killsignals.routinefailed)
    except Exception:  # noqa: BLE001 - reported, never assumed converged
        failed = None
    # Defect 16.  This read `iteration.totalr`, which does not exist -- ADflow's
    # own convergence check uses `totalrfinal` (pyADflow.py:2007,
    # `L2Conv = iterationModule.totalrfinal / iterationModule.totalr0`).  The
    # attribute error was caught and turned into None, and None made
    # `converged` False, so the first corrected alpha 0 run was recorded as not
    # converged when it had in fact reached 9.14e-9 against a 1e-8 target in 279
    # iterations.  Failing closed is right; failing closed on a typo is not,
    # because a wrongly-rejected run costs exactly as much machine time as a
    # wrongly-accepted one and looks like a real result to whoever reads it next.
    residual = None
    residual_source = None
    try:
        iteration = solver.adflow.iteration
        residual = float(iteration.totalrfinal / iteration.totalr0)
        residual_source = "adflow.iteration.totalrfinal/totalr0"
    except Exception as direct_error:  # noqa: BLE001 - fall through, then report
        try:
            history = solver.getConvergenceHistory()
            series = history.get("RSDRho") or history.get("Res rho")
            residual = float(series[-1] / series[0])
            residual_source = "getConvergenceHistory"
        except Exception as history_error:  # noqa: BLE001 - never assumed converged
            residual = None
            residual_source = (
                f"UNAVAILABLE: {type(direct_error).__name__}: {direct_error}; "
                f"fallback {type(history_error).__name__}: {history_error}"
            )
    result = {
        "converged": (residual is not None and residual <= args.l2),
        "relative_residual": residual,
        "residual_source": residual_source,
        "l2_target": args.l2,
        "n_cycles_budget": args.n_cycles,
        "grid": str(args.grid),
        "alpha_deg": args.alpha,
        "mission": MISSION,
        "area_ref_m2": args.area_ref,
        "moment_ref_xyz_m": list(MOMENT_REF_XYZ),
        "routine_failed": failed,
        "flow_directions": directions,
        "functions": {k: float(v) for k, v in funcs.items()},
    }
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
