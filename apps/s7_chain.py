#!/usr/bin/env python3
"""Run the whole S7 chain unattended and report every gate.

    python3 apps/s7_chain.py                      # defaults, 6000 iterations
    python3 apps/s7_chain.py --iterations 3000
    python3 apps/s7_chain.py --alpha 4.0 --mach 0.25

Geometry, mesh, mesh audit, solve, then the study's own residual, force and
y+ gates evaluated by the study's own code.  Everything lands in
apps/workspace/s7_chain/ with a JSON report beside it, so a run can be read
back after the fact rather than only watched.

This is the same path the workbench takes - the same defaults, the same
audit, the same solver - with no interface in the way.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aeris_workbench import geometry as geo  # noqa: E402
from aeris_workbench import meshing, solvers
from aeris_workbench import postprocess as post
from aeris_workbench.environment import S7_DIR, WORKSPACE, available_memory_gib  # noqa: E402

sys.path.insert(0, str(S7_DIR.parent))


def _rule(title: str) -> None:
    print(f"\n{'─' * 72}\n{title}\n{'─' * 72}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iterations", type=int, default=6000)
    parser.add_argument("--alpha", type=float, default=2.0)
    parser.add_argument("--mach", type=float, default=0.20)
    parser.add_argument("--reynolds", type=float, default=1.0e6)
    parser.add_argument("--level", default="laptop_smoke",
                        help="in-plane sizing tier; the wall spacing is set separately")
    parser.add_argument("--output", type=Path, default=WORKSPACE / "s7_chain")
    args = parser.parse_args()

    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"arguments": vars(args) | {"output": str(root)}}
    started = time.time()

    # ---- geometry -------------------------------------------------------- #
    _rule("1 / 4  GEOMETRY   pyGeo loft and surface tessellation")
    mark = time.time()
    case = geo.build_case({}, root / "geometry")
    surface = geo.build_surface(case, level=args.level, te_variant="te_1p0mm")
    planform = geo.planform_summary(case)
    stats = geo.surface_statistics(surface)
    print(f"  span {planform['span_m']:.4f} m   area {planform['area_m2']:.4f} m²   "
          f"MAC {planform['mac_m']:.4f} m", flush=True)
    print(f"  {stats['triangles']:,} triangles, wetted {stats['wetted_area_m2']:.4f} m²   "
          f"[{time.time() - mark:.1f}s]", flush=True)
    report["geometry"] = {"planform": {k: v for k, v in planform.items()
                                       if not isinstance(v, (list, dict))},
                          "surface": {k: v for k, v in stats.items()
                                      if not isinstance(v, (list, dict))}}

    # ---- mesh ------------------------------------------------------------ #
    _rule("2 / 4  MESH   Gmsh prisms and tetrahedra, then the study's audit")
    mark = time.time()
    settings = meshing.settings_from_policy(meshing.study_policy(), args.level)
    # The wall spacing that measured y+ p95 0.54; the tier default gives 40.6.
    settings.first_cell_height_over_L = 7.20e-6
    settings.prism_layers = 24
    settings.prism_growth_ratio = 1.25
    mesh_dir = root / "mesh"
    mesh_report = meshing.run_gmsh(surface, settings, mesh_dir,
                                   log=lambda m: print(f"  {m}", flush=True))
    dataset = meshing.read_volume_mesh(Path(mesh_report["mesh_msh"]))
    counts = meshing.summarize_mesh(dataset)
    validity = meshing.validity_report(dataset)
    print(f"  {counts['cells']:,} cells, {counts['points']:,} points   "
          f"[{time.time() - mark:.1f}s]", flush=True)
    print(f"  worst scaled Jacobian {validity['min_scaled_jacobian']}, "
          f"{validity['inverted_count']} inverted", flush=True)

    audit = meshing.audit_summary(
        meshing.audit_gmsh(surface, mesh_dir, settings,
                           log=lambda m: print(f"  {m}", flush=True)))
    print(f"  audit: {'ACCEPTED' if audit['accepted'] else 'REJECTED'} "
          f"at tier {audit['evidence_tier']}, "
          f"{len(audit['rows'])} gates, {len(audit['warnings'])} warnings", flush=True)
    report["mesh"] = {"counts": counts, "validity": validity,
                      "audit": {k: v for k, v in audit.items() if k != "rows"}}

    if not validity["valid"] or not audit["accepted"]:
        print("\n  STOPPING: the mesh is not acceptable, so a solve would prove nothing.",
              flush=True)
        (root / "chain_report.json").write_text(json.dumps(report, indent=2, default=str))
        return 1

    # ---- solve ----------------------------------------------------------- #
    _rule("3 / 4  SOLVE   SU2 RANS-SA, Newton-Krylov, live residuals")
    print(f"  {available_memory_gib():.1f} GiB free at launch", flush=True)
    mark = time.time()
    flow = solvers.FlowConditions(
        mach=args.mach, alpha_deg=args.alpha, reynolds=args.reynolds,
        area_ref_m2=float(planform["area_m2"]), chord_ref_m=float(planform["mac_m"]))
    su2_settings = solvers.SU2Settings(
        newton_krylov=True, linear_preconditioner="ILU", linear_iterations=25,
        cfl=25.0, cfl_ceiling=1000.0, multigrid_levels=0,
        stop_residual=-9.0, iterations=int(args.iterations))
    runner = solvers.SU2Runner()
    run_dir = root / "solve"
    runner.start(meshing.su2_mesh_path(mesh_report), flow, su2_settings, run_dir)

    shown = 0
    while True:
        time.sleep(10)
        snapshot = runner.snapshot()
        history = snapshot["history"]
        if snapshot["iteration"] >= shown + 250 and history.get("rms_rho"):
            shown = snapshot["iteration"]
            print(f"  iter {snapshot['iteration']:5d}  rms {history['rms_rho'][-1]:8.4f}  "
                  f"CL {history.get('CL', [0])[-1]:9.6f}  "
                  f"CD {history.get('CD', [0])[-1]:9.6f}  "
                  f"[{snapshot['wall_seconds']:.0f}s]", flush=True)
        if snapshot["status"] not in ("running", "idle"):
            break
    snapshot = runner.snapshot()
    print(f"  {snapshot['status']} after {snapshot['iteration']} iterations "
          f"[{time.time() - mark:.0f}s]", flush=True)
    report["solve"] = {"status": snapshot["status"], "iterations": snapshot["iteration"],
                       "wall_seconds": snapshot["wall_seconds"]}

    # ---- gates ----------------------------------------------------------- #
    _rule("4 / 4  GATES   the study's own acceptance criteria")
    from S7_unstructured_gmsh_su2 import su2_pipeline as su2  # noqa: PLC0415

    policy = yaml.safe_load((S7_DIR / "POLICY.yaml").read_text())
    history = su2.parse_su2_history(run_dir / "history.csv")
    residual = su2.residual_gate(history, policy)
    forces = su2.force_tail_gate(history, policy)

    print(f"  residual   drop {residual['orders_dropped']:.3f} of "
          f"{residual['minimum_orders_dropped']} required, "
          f"final {residual['final_log10']:.3f} of "
          f"{residual['maximum_final_log10']} allowed"
          f"   {'PASS' if residual['passed'] else 'FAIL ' + str(residual['failure_reasons'])}",
          flush=True)
    ranges = {k: (None if v is None else float(f"{v:.3g}"))
              for k, v in forces["relative_ranges"].items()}
    print(f"  force tail {ranges}"
          f"   {'PASS' if forces['passed'] else 'FAIL ' + str(forces['failure_reasons'])}",
          flush=True)

    yplus_pass = None
    surface_file = run_dir / "surface_flow.vtk"
    if surface_file.is_file():
        from vtk.util.numpy_support import vtk_to_numpy  # noqa: PLC0415

        solution = post.load(surface_file)
        array = solution.GetPointData().GetArray("Y_Plus")
        if array is not None:
            values = vtk_to_numpy(array)
            limits = policy["su2"]["wall_y_plus"]
            p95, top = float(np.percentile(values, 95)), float(values.max())
            yplus_pass = p95 <= limits["p95_max"] and top <= limits["max_max"]
            print(f"  y+         p50 {np.median(values):.2f}  p95 {p95:.2f} of "
                  f"{limits['p95_max']}  max {top:.2f} of {limits['max_max']}"
                  f"   {'PASS' if yplus_pass else 'FAIL'}", flush=True)
            report["y_plus"] = {"p50": float(np.median(values)), "p95": p95, "max": top,
                                "passed": yplus_pass}

    # A run too short for a force tail reports None rather than a number, and
    # formatting that as a float is how a diagnostic run ends in a traceback
    # instead of a verdict.
    final = forces["final_coefficients"]
    shown = "   ".join(
        f"{name} {value:.6f}" if isinstance(value, (int, float)) else f"{name} n/a"
        for name, value in (("CL", final.get("CL")), ("CD", final.get("CD")),
                            ("CMy", final.get("CMy"))))
    print(f"\n  {shown}", flush=True)

    accepted = bool(residual["passed"] and forces["passed"] and (yplus_pass is not False))
    report["gates"] = {"residual": residual, "forces": forces, "accepted": accepted}
    report["wall_seconds"] = round(time.time() - started, 1)
    (root / "chain_report.json").write_text(json.dumps(report, indent=2, default=str))

    _rule(f"{'ACCEPTED' if accepted else 'NOT ACCEPTED'}   "
          f"total {report['wall_seconds'] / 60:.1f} min   report in {root}/chain_report.json")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
