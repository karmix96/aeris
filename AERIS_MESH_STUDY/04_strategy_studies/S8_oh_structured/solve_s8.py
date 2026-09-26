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
import math
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
#: A run that reports convergence after fewer iterations than this did not
#: converge; it failed in a way that flattered the residual ratio.
MIN_ITERATIONS = 10
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
    # 1e-6, not 1e-8, and the reason is measured rather than assumed.
    #
    # Replaying the four gci_C runs and reading the forces off at the iteration
    # where the relative residual first crossed 1e-6, against their final values:
    #
    #     alpha   1e-6 at    of run     dCL        dCD        dCMy
    #      -2     it 187      88 %    +3.3e-08   +1.3e-06   -1.0e-07
    #       0     it 165      60 %    -2.0e-05   +1.2e-05   +1.4e-08
    #       4     it 158      12 %    -3.1e-07   +1.1e-05   +8.5e-08
    #       8     it 136      11 %    -5.0e-05   +1.2e-05   +2.1e-06
    #
    # Everything after 1e-6 moves the forces in the fifth decimal. The sweep
    # cost 308 minutes and would have cost 63 -- a 4.9x saving -- for changes of
    # order 1e-5 relative, against a GRID-to-grid discretization difference of
    # order 1e-2 on CD. Iterative error three orders below the signal being
    # measured is the condition PLAN 0.6 asks for, and 1e-6 meets it.
    #
    # It was also never being achieved: alpha 4 and alpha 8 never reached even
    # 1e-7, so 1e-8 was aspirational and those runs stopped on other grounds
    # after grinding through ~1180 useless iterations.
    #
    # This is the STOPPING rule. Acceptance is convergence_gate.py -- five orders
    # of residual drop AND settled forces AND a healthy residual history. The two
    # are stated together in policies/s8_campaign_v1.yaml because the previous
    # split (gate relaxed to five orders, solver still driving to 1e-8) is how
    # they drifted apart.
    #
    # Caveat worth keeping visible: stopping at 1e-6 means alpha 4 halts while
    # still healthy and is graded ACCEPTED rather than ACCEPTED_SOLVER_FROZEN.
    # The stall only became visible because the run continued 1180 iterations
    # past the useful point. Diagnosing solver weak spots is now a deliberate
    # investigation with --l2 tightened, not something a campaign run surfaces
    # for free.
    ap.add_argument("--l2", type=float, default=1.0e-6)
    # 4000 was carried over from the canary policy and is far too small here:
    # it caps the CUMULATIVE linear-iteration counter, and both first runs hit
    # it at 4004 and 4028, stopping at 4.6e-6 and 1.5e-5 relative instead of the
    # 1e-8 asked for. ADflow exits cleanly when it does that, and
    # `routine_failed` stays false, so an unconverged run looks exactly like a
    # converged one unless the residual is checked.
    ap.add_argument("--n-cycles", type=int, default=30000)
    # PLAN 0.5 territory: these change the solver, so they default to the
    # governed values and every use is recorded in result.json.
    #
    # Why --no-nk exists. On gci_M (1,111,152 cells) ANK converged cleanly to
    # 3.3e-05 by iteration 300, NK took over at 302, and the residual went UP to
    # 2.8e-04 and froze there for 450 iterations with `Step 0.01` and
    # `LinRes 1.000` -- the Krylov solve achieving no reduction at all -- while
    # the forces sat still to THIRTEEN significant figures. That is PLAN 0.6's
    # signature, and on a mesh where alpha -2 converged in 212 iterations at
    # gci_C, so refinement made it worse (PLAN 0.8).
    #
    # The likely cause is the preconditioner. This project runs NKSubspaceSize
    # 20 and NKPCILUFill 1 against ADflow's defaults of 60 and 2, about 3x
    # leaner on Krylov memory, chosen because gci_M peaks at 12.7 GiB against
    # 12.8 available. Restoring the defaults would not fit. So on this host the
    # finer mesh can be held in memory or converged by NK, not both -- and
    # ANK alone, which needs no Krylov subspace, is the way out rather than a
    # compromise.
    ap.add_argument("--no-nk", action="store_true",
                    help="disable the Newton-Krylov stage and converge with ANK "
                         "alone. Uses LESS memory. Changes the solver relative to "
                         "the governed setup, so it is recorded in result.json and "
                         "must be stated wherever the result is used.")
    ap.add_argument("--nk-switch-tol", type=float, default=None,
                    help="override NKSwitchTol (governed value 1e-6)")
    # Solver-sensitivity studies from the pre-cloud checklist (2026-09-11). Each
    # changes the solver, so each defaults to the governed value and every use
    # is recorded in result.json alongside --no-nk.
    ap.add_argument("--turbulence-model", default=None,
                    choices=["SA", "SA-Edwards", "Menter SST", "k-omega Wilcox"],
                    help="override turbulenceModel (governed value SA)")
    ap.add_argument("--mg-cycle", default=None,
                    help="override MGCycle (governed 'sg'), e.g. 2w or 3w")
    ap.add_argument("--smoother", default=None, choices=["DADI", "Runge-Kutta"],
                    help="multigrid smoother, used before the ANK switch")
    ap.add_argument("--ank-switch-tol", type=float, default=None,
                    help="override ANKSwitchTol (governed 1.0: ANK from the start)")
    ap.add_argument("--n-cycles-coarse", type=int, default=None,
                    help="override nCyclesCoarse, the coarse-grid start budget")
    # ADflow's default freestream eddy-viscosity ratio, 0.009, is SA chi ~1.3; the
    # TMR prescribes chi = 3 (ratio 0.21) so the ft2 term cannot hold a boundary
    # layer laminar. Every S8 run so far used the default.
    ap.add_argument("--eddy-vis-inf-ratio", type=float, default=None,
                    help="override eddyVisInfRatio (ADflow default 0.009)")
    # SA's ft2 term damps production where chi is small; with the default freestream
    # it is the suspected route by which part of the boundary layer stays laminar.
    ap.add_argument("--no-ft2", action="store_true",
                    help="SA without the ft2 term (useft2SA False; default True)")
    # ADflow ships residual scalings for SA (1e4) and Menter SST ([1e3, 1e-6]) only.
    # Every other model raises "does not have default values specified for
    # turbresscale" -- on ONE rank, which leaves the other five waiting forever,
    # so the run neither fails nor honours its time limit. SA-Edwards is an SA
    # variant and takes SA's value; a two-equation model takes SST's pair.
    # ADflow carries a low-speed preconditioner and the campaign has it OFF -- the
    # default, never chosen. At M 0.0837 a central scheme's artificial dissipation
    # scales with the acoustic speed, not the flow speed, so it is roughly 1/M
    # times larger than the physics it is damping. This is the standard low-Mach
    # accuracy problem and the preconditioner is the standard answer to it.
    # A general escape hatch for the settings this audit keeps turning up. Every use
    # lands in solver_overrides like any other, so a row still says what it ran.
    ap.add_argument("--set-option", action="append", default=[], metavar="KEY=VALUE",
                    help="any other ADflow option, e.g. vis4=0.0078")
    ap.add_argument("--low-speed-preconditioner", action="store_true",
                    help="ADflow's low-speed preconditioner (default off)")
    ap.add_argument("--turb-res-scale", type=float, nargs="+", default=None,
                    help="turbResScale; required for any model but SA and Menter SST")
    ap.add_argument("--turbulence-order", default=None,
                    choices=["first order", "second order"],
                    help="advection order of the SA variable (ADflow default first)")
    # OPERATING POINT. The mission is governed and these default to it, so a run
    # that does not pass them is bit-identical to before. They exist because a
    # validation case is flown at the EXPERIMENT's condition, not at ours: RIBES
    # T40 measures 39.83 m/s at 25.7 C, which is Mach 0.11494 and Re 1.329e6 on
    # its 0.5153 m mean aerodynamic chord. Every override is recorded in
    # result.json under solver_overrides, exactly as --no-nk is.
    ap.add_argument("--mach", type=float, default=None,
                    help="free-stream Mach; default is the governed mission value")
    ap.add_argument("--reynolds", type=float, default=None)
    ap.add_argument("--reynolds-length", type=float, default=None,
                    help="length the Reynolds number is formed on, metres")
    ap.add_argument("--temperature", type=float, default=None, help="free-stream T, kelvin")
    ap.add_argument("--chord-ref", type=float, default=None,
                    help="moment reference chord, metres")
    ap.add_argument("--i-have-authorization", action="store_true")
    args = ap.parse_args()

    if not args.i_have_authorization:
        raise SystemExit(
            "refusing to run: pass --i-have-authorization. The record for this "
            "run is POLICY.yaml heavy_work.exceptions.run-s8-first-point, "
            "policies/s8_oh_first_point_v1.yaml and ADR-0018."
        )

    # Turbulence model and multigrid cycle size ADflow's allocation, so they
    # enter the options at construction rather than through setOption.
    init_overrides = {key: getattr(args, flag) for flag, key in (
        ("turbulence_model", "turbulenceModel"), ("mg_cycle", "MGCycle"),
        ("smoother", "smoother"), ("ank_switch_tol", "ANKSwitchTol"),
        ("n_cycles_coarse", "nCyclesCoarse"),
        ("eddy_vis_inf_ratio", "eddyVisInfRatio"),
        ("turbulence_order", "turbulenceOrder")) if getattr(args, flag) is not None}
    if args.turb_res_scale:
        init_overrides["turbResScale"] = (args.turb_res_scale[0] if len(args.turb_res_scale) == 1
                                          else list(args.turb_res_scale))
    if args.no_ft2:
        init_overrides["useft2SA"] = False
    if args.low_speed_preconditioner:
        init_overrides["lowSpeedPreconditioner"] = True
    for item in args.set_option:
        key, _, value = item.partition("=")
        try:
            init_overrides[key] = json.loads(value)
        except json.JSONDecodeError:
            init_overrides[key] = value

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
        **init_overrides,
    })
    # Solver overrides, applied AFTER the governed dict above so that the
    # governed values remain the literal defaults in this file and a reader can
    # see exactly what was changed and why.
    overrides: dict = {}
    # NOT into `overrides`: that dict is handed to ADflow as SOLVER options, and
    # mach, reynolds and the rest are AeroProblem parameters. Putting them there
    # got "Option mach is not a valid ADFLOW option" on all four RIBES runs.
    # They are already wired into the AeroProblem above; this only records them.
    mission_overrides = {k: v for k, v in (
        ("mach", args.mach), ("reynolds", args.reynolds),
        ("reynolds_length_m", args.reynolds_length),
        ("temperature_K", args.temperature), ("chord_ref_m", args.chord_ref))
        if v is not None}
    if args.no_nk:
        overrides["useNKSolver"] = False
    if args.nk_switch_tol is not None:
        overrides["NKSwitchTol"] = args.nk_switch_tol
    for key, value in overrides.items():
        solver.setOption(key, value)

    problem = AeroProblem(
        name=f"s8_a{args.alpha:g}",
        alpha=args.alpha,
        beta=0.0,
        mach=args.mach if args.mach is not None else MISSION["mach"],
        reynolds=args.reynolds if args.reynolds is not None else MISSION["reynolds"],
        reynoldsLength=(args.reynolds_length if args.reynolds_length is not None
                        else MISSION["reynolds_length_m"]),
        T=args.temperature if args.temperature is not None else MISSION["temperature_K"],
        areaRef=args.area_ref,
        chordRef=args.chord_ref if args.chord_ref is not None else MISSION["chord_ref_m"],
        xRef=MOMENT_REF_XYZ[0],
        yRef=MOMENT_REF_XYZ[1],
        zRef=MOMENT_REF_XYZ[2],
        # cmx and cmz are here for the dataset schema (PLAN 4.4), not for the
        # aerodynamics: on a half model at zero sideslip they are half-model
        # quantities, and CMy is the one that carries the stability result.
        # Adding them changes no solver setting and cannot change the solution
        # -- evalFunctions integrates a solution that has already converged --
        # so it is safe to add mid-campaign, which almost nothing else here is.
        # The regression anchor gci_C_a0 ran before this line existed and
        # therefore carries no CMx/CMz; dataset_row.py records that as an
        # explicit absence rather than a blank.
        evalFuncs=["cl", "cd", "cmy", "cdp", "cdv", "cmx", "cmz"],
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
    # A run that stops after one iteration can still report a tiny residual
    # ratio. Menter SST did exactly that here: one DADI iteration, ratio 9e-9,
    # CL -1.17 and CD 2.21 written out as "converged". Forces no wing at this
    # mission can produce are not a result, whatever the residual says.
    coefficients = {k.split("_")[-1]: float(v) for k, v in funcs.items()}
    BOUNDS = {"cl": (-3.0, 3.0), "cd": (0.0, 0.5), "cdp": (-0.05, 0.5),
              "cdv": (0.0, 0.1), "cmy": (-3.0, 3.0), "cmx": (-3.0, 3.0),
              "cmz": (-3.0, 3.0)}
    # A NaN fails every comparison, so a plain range test lets it through.
    implausible = {k: v for k, v in coefficients.items()
                   if k in BOUNDS and not (math.isfinite(v)
                                           and BOUNDS[k][0] <= v <= BOUNDS[k][1])}
    if implausible:
        print(f"IMPLAUSIBLE FORCES {implausible} -- not recording this as converged")
    # Every governed setting that actually reached the solver, read back FROM it.
    # A row that claims the governed configuration should be able to prove it,
    # and a defaulted option nobody chose (eddyVisInfRatio) should be visible.
    effective = {}
    for key in ("equationType", "turbulenceModel", "turbulenceOrder", "useft2SA",
                "eddyVisInfRatio", "liftIndex", "MGCycle", "smoother",
                "useANKSolver", "ANKSwitchTol", "useNKSolver", "NKSwitchTol",
                "ANKSubspaceSize", "NKSubspaceSize", "ANKPCILUFill", "NKPCILUFill",
                "L2Convergence", "nCycles", "useWallFunctions", "useQCR"):
        try:
            effective[key] = solver.getOption(key)
        except Exception:  # noqa: BLE001 - an option this build does not carry
            pass
    try:
        completed = int(solver.adflow.iteration.itertot)
    except Exception:  # noqa: BLE001 - reported, never assumed
        completed = None
    # Menter SST stopped after ONE iteration with a residual ratio of 9e-9 and
    # wrote CL -1.17, CD 2.21 as converged: its initial residual was meaningless,
    # so the ratio was too. No flow reaches a converged state in one step.
    too_few = completed is not None and completed < MIN_ITERATIONS
    if too_few:
        print(f"ONLY {completed} ITERATIONS -- not recording this as converged")

    result = {
        "converged": (((residual is not None and residual <= args.l2)) and not implausible) and not too_few,
        "iterations_completed": completed,
        "too_few_iterations": too_few,
        "solver_options_effective": effective,
        "implausible_forces": implausible or None,
        "relative_residual": residual,
        "residual_source": residual_source,
        "l2_target": args.l2,
        "n_cycles_budget": args.n_cycles,
        "grid": str(args.grid),
        "alpha_deg": args.alpha,
        "mission": MISSION,
        "mission_overrides": mission_overrides,
        "mission_effective": {**MISSION, **{
            "mach": args.mach if args.mach is not None else MISSION["mach"],
            "reynolds": args.reynolds if args.reynolds is not None else MISSION["reynolds"],
            "reynolds_length_m": (args.reynolds_length if args.reynolds_length is not None
                                  else MISSION["reynolds_length_m"]),
            "temperature_K": (args.temperature if args.temperature is not None
                              else MISSION["temperature_K"]),
            "chord_ref_m": (args.chord_ref if args.chord_ref is not None
                            else MISSION["chord_ref_m"])}},
        "area_ref_m2": args.area_ref,
        "moment_ref_xyz_m": list(MOMENT_REF_XYZ),
        "routine_failed": failed,
        "flow_directions": directions,
        # Empty unless a flag was passed. Recorded either way, so a row that
        # used the governed setup says so positively rather than by omission.
        "solver_overrides": {**init_overrides, **overrides},
        "solver_is_governed_configuration": not (init_overrides or overrides),
        "functions": {k: float(v) for k, v in funcs.items()},
    }
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
