"""
ADflow solver adapter: prepare/run/parse against the mach-aero environment.

The runner script is static — it bakes in nothing and reads two JSON files
(``adflow_options.json``: the resolved solver options with provenance in
``adflow_effective_options.json``; ``adflow_case.json``: the AeroProblem
definition).  Execution is ``mpirun -np N <mach-aero python> run_adflow.py``.
The prepared triple (runner + two JSONs) is standalone re-runnable on a
cluster without AERIS installed.
"""

from __future__ import annotations

import json
from pathlib import Path

from aeris.cfd.case.spec import SolveSpec
from aeris.cfd.env import mach_aero_mpirun, mach_aero_python
from aeris.cfd.options.layers import OptionLayer
from aeris.cfd.options.manifest import write_effective_options_manifest
from aeris.cfd.presets.registry import get_preset
from aeris.cfd.solvers.adflow.options_schema import build_adflow_options
from aeris.cfd.solvers.adflow.parse import parse_monitor_history
from aeris.cfd.solvers.base import (
    PreparedRun,
    SolverAdapter,
    SolveReport,
    write_solve_report,
)

DEFAULT_SOLVER_PRESET = "rans_ank_nk_v1"
DEFAULT_EVAL_FUNCS = ("cl", "cd", "cmy", "cdp", "cdv")

OPTIONS_JSON_NAME = "adflow_options.json"
CASE_JSON_NAME = "adflow_case.json"
MANIFEST_NAME = "adflow_effective_options.json"
RUNNER_NAME = "run_adflow.py"
RUN_LOG_NAME = "adflow_run.log"
RUN_JSON_NAME = "adflow_run.json"

_RUNNER_TEMPLATE = '''\
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
    residual_cancellation_ratio = abs(global_rho_sum) / max(global_rho_abs, 1.0e-300)

    # Governed conservation metric: signed net boundary mass flux over gross
    # boundary mass flux.  ADflow integrates rho*(V.n)*dA over a family with its
    # native `mdot` cost function, so let the solver do the integration rather
    # than reconstructing face normals here.  Every CGNS boundary family is
    # measured, including walls and symmetry planes, whose mdot must be ~0.
    boundary_families = [
        name
        for name in solver.families
        if name.lower() not in (solver.allFamilies.lower(), solver.allWallsGroup.lower())
    ]
    boundary_families.sort()
    flux_handles = {}
    for family in boundary_families:
        flux_handles[family] = {
            "mdot": "aeris_mdot_%s" % family,
            "area": "aeris_area_%s" % family,
        }
        solver.addFunction("mdot", family, name=flux_handles[family]["mdot"])
        solver.addFunction("area", family, name=flux_handles[family]["area"])

    flux_raw = {}
    boundary_flux_error = None
    if flux_handles:
        requested = [h[k] for h in flux_handles.values() for k in ("mdot", "area")]
        try:
            solver.evalFunctions(ap, flux_raw, evalFuncs=requested)
        except Exception as exc:  # fail closed: record, never silently pass
            boundary_flux_error = "%s: %s" % (type(exc).__name__, exc)

    def _flux_value(handle):
        # evalFunctions lower-cases names and prefixes the AeroProblem name.
        for key in ("%s_%s" % (ap.name, handle.lower()), handle.lower(), handle):
            if key in flux_raw:
                return float(flux_raw[key])
        return None

    per_family_flux = {}
    signed_net = 0.0
    gross = 0.0
    complete = boundary_flux_error is None and bool(flux_handles)
    for family, handles in flux_handles.items():
        mdot = _flux_value(handles["mdot"])
        area = _flux_value(handles["area"])
        per_family_flux[family] = {"mdot": mdot, "area": area}
        if mdot is None or not numpy.isfinite(mdot):
            complete = False
            continue
        signed_net += mdot
        gross += abs(mdot)

    if complete and gross > 0.0:
        mass_imbalance_normalized = abs(signed_net) / gross
    else:
        mass_imbalance_normalized = None

    boundary_mass_flux = {
        "definition": "signed_net_boundary_mass_flux_over_gross_boundary_mass_flux",
        "signed_net": signed_net if complete else None,
        "gross": gross if complete else None,
        "normalized": mass_imbalance_normalized,
        "per_family": per_family_flux,
        "family_count": len(flux_handles),
        "complete": complete,
        "error": boundary_flux_error,
        "granularity_note": (
            "Gross flux is summed as the absolute per-CGNS-boundary-family mdot. "
            "Inflow and outflow that cancel inside a single family shrink the "
            "denominator, so this normalized value is an upper bound on the true "
            "boundary imbalance and the gate is therefore conservative."
        ),
    }

    funcs = {}
    solver.evalFunctions(ap, funcs, evalFuncs=list(case["eval_funcs"]))
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
            "boundary_mass_flux": boundary_mass_flux,
            "mass_imbalance_normalized": (
                None
                if mass_imbalance_normalized is None
                else float(mass_imbalance_normalized)
            ),
            "mass_imbalance_definition": boundary_mass_flux["definition"],
            "residual_cancellation_ratio_diagnostic": float(residual_cancellation_ratio),
            "residual_cancellation_ratio_definition": (
                "abs(sum continuity residual)/sum(abs continuity residual); retained "
                "as a diagnostic only and never used for acceptance"
            ),
            "elapsed_seconds": time.time() - t0,
        }
        (here / "adflow_run.json").write_text(json.dumps(report, indent=2))
        print("[run_adflow] " + json.dumps(report["functions"]))
        print(f"[run_adflow] solve_failed = {report['solve_failed']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


class AdflowAdapter(SolverAdapter):
    SOLVER_ID = "adflow"

    def prepare(self, solve: SolveSpec, mesh_cgns: Path, workdir: Path) -> PreparedRun:
        if solve.flow is None:
            raise ValueError("solve.flow (alpha/mach/reynolds) is required for ADflow")
        if solve.area_ref is None or solve.chord_ref is None:
            raise ValueError(
                "solve.area_ref and solve.chord_ref are required (HALF-model "
                "reference area for symmetry-plane meshes; mean aerodynamic chord)."
            )
        if solve.reynolds_length_ref is not None and solve.reynolds_length_ref <= 0.0:
            raise ValueError("solve.reynolds_length_ref must be positive")
        for name, reference in (
            ("moment_reference", solve.moment_reference),
            ("secondary_moment_reference", solve.secondary_moment_reference),
        ):
            if reference is not None and len(reference) != 3:
                raise ValueError(f"solve.{name} must contain exactly three coordinates")
        if solve.secondary_moment_reference is not None and solve.moment_reference is None:
            raise ValueError(
                "solve.moment_reference is required when secondary_moment_reference is set"
            )
        workdir = workdir.expanduser().resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        mesh_cgns = mesh_cgns.expanduser().resolve()
        if not mesh_cgns.is_file():
            raise FileNotFoundError(f"volume mesh not found: {mesh_cgns}")

        extra_layers: list[OptionLayer] = []
        preset_name = solve.preset or DEFAULT_SOLVER_PRESET
        preset = get_preset(preset_name)
        if preset.solver:
            extra_layers.append(OptionLayer(f"preset:{preset.name}", dict(preset.solver)))
        if solve.overrides:
            extra_layers.append(OptionLayer("config", dict(solve.overrides)))

        effective = build_adflow_options(
            mesh_cgns,
            workdir,
            extra_layers=extra_layers,
            adflow_options=solve.raw_options or None,
        )

        (workdir / OPTIONS_JSON_NAME).write_text(
            json.dumps(effective.values, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_effective_options_manifest(
            workdir / MANIFEST_NAME,
            effective=effective,
            input_files={"volume_mesh": mesh_cgns},
            extra={"solver_preset": preset_name},
        )
        case_payload = {
            "name": "aeris_cfd",
            "alpha": solve.flow.alpha,
            "mach": solve.flow.mach,
            "reynolds": solve.flow.reynolds,
            "temperature": solve.flow.temperature,
            "area_ref": solve.area_ref,
            "chord_ref": solve.chord_ref,
            "reynolds_length_ref": (
                solve.reynolds_length_ref
                if solve.reynolds_length_ref is not None
                else solve.chord_ref
            ),
            "moment_reference": (
                list(solve.moment_reference) if solve.moment_reference is not None else None
            ),
            "secondary_moment_reference": (
                list(solve.secondary_moment_reference)
                if solve.secondary_moment_reference is not None
                else None
            ),
            "eval_funcs": list(DEFAULT_EVAL_FUNCS),
        }
        (workdir / CASE_JSON_NAME).write_text(
            json.dumps(case_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        runner = workdir / RUNNER_NAME
        runner.write_text(_RUNNER_TEMPLATE, encoding="utf-8")

        command = (
            str(mach_aero_mpirun()),
            "-np",
            str(solve.mpi_np),
            str(mach_aero_python()),
            str(runner),
        )
        return PreparedRun(
            solver_id=self.SOLVER_ID,
            workdir=workdir,
            command=command,
            log_name=RUN_LOG_NAME,
            artifacts={
                "options": str(workdir / OPTIONS_JSON_NAME),
                "case": str(workdir / CASE_JSON_NAME),
                "effective_options": str(workdir / MANIFEST_NAME),
                "runner": str(runner),
            },
        )

    def parse(self, workdir: Path) -> SolveReport:
        workdir = workdir.expanduser().resolve()
        run_json = workdir / RUN_JSON_NAME
        log_path = workdir / RUN_LOG_NAME
        case = json.loads((workdir / CASE_JSON_NAME).read_text(encoding="utf-8"))

        convergence: dict[str, object] = {}
        if log_path.is_file():
            convergence = parse_monitor_history(log_path.read_text(encoding="utf-8"))

        if not run_json.is_file():
            report = SolveReport(
                solver_id=self.SOLVER_ID,
                status="failed",
                flow={
                    "alpha": case["alpha"],
                    "mach": case["mach"],
                    "reynolds": case["reynolds"],
                    "temperature": case["temperature"],
                },
                refs={
                    "area_ref": case["area_ref"],
                    "chord_ref": case["chord_ref"],
                    "reynolds_length_ref": case["reynolds_length_ref"],
                    "moment_reference": case.get("moment_reference"),
                    "secondary_moment_reference": case.get("secondary_moment_reference"),
                },
                convergence=convergence,
                artifacts={"log": str(log_path)},
            )
            write_solve_report(workdir, report)
            return report

        run = json.loads(run_json.read_text(encoding="utf-8"))
        convergence["residual_components_final"] = run.get("residual_components_final", {})
        convergence["residual_component_monitor_final"] = run.get(
            "residual_component_monitor_final", {}
        )
        convergence["residual_components_definition"] = run.get("residual_components_definition")
        convergence["residual_vector_component_l2_diagnostic"] = run.get(
            "residual_vector_component_l2_diagnostic", {}
        )
        convergence["native_history"] = run.get("convergence_history", {})
        convergence["mass_imbalance_normalized"] = run.get("mass_imbalance_normalized")
        convergence["mass_imbalance_definition"] = run.get("mass_imbalance_definition")
        convergence["boundary_mass_flux"] = run.get("boundary_mass_flux", {})
        convergence["residual_cancellation_ratio_diagnostic"] = run.get(
            "residual_cancellation_ratio_diagnostic"
        )
        status = "failed" if run.get("solve_failed") else "converged"
        # ADflow keys evalFunctions as "<AeroProblem name>_<func>"; normalize
        # to bare coefficient names for the solve_report/dataset schema.
        functions = {
            (key.split("_")[-1] if "_" in key else key): float(value)
            for key, value in run.get("functions", {}).items()
        }
        report = SolveReport(
            solver_id=self.SOLVER_ID,
            status=status,
            flow={
                "alpha": case["alpha"],
                "mach": case["mach"],
                "reynolds": case["reynolds"],
                "temperature": case["temperature"],
            },
            refs={
                "area_ref": case["area_ref"],
                "chord_ref": case["chord_ref"],
                "reynolds_length_ref": case["reynolds_length_ref"],
                "moment_reference": case.get("moment_reference"),
                "secondary_moment_reference": case.get("secondary_moment_reference"),
            },
            forces=functions,
            convergence=convergence,
            artifacts={
                "log": str(log_path),
                "run_json": str(run_json),
                "effective_options": str(workdir / MANIFEST_NAME),
            },
            elapsed_seconds=run.get("elapsed_seconds"),
        )
        write_solve_report(workdir, report)
        return report
