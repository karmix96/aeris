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
DEFAULT_EVAL_FUNCS = ("cl", "cd", "cmy")

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
        reynoldsLength=case["chord_ref"],
        T=case["temperature"],
        areaRef=case["area_ref"],
        chordRef=case["chord_ref"],
        evalFuncs=case["eval_funcs"],
    )
    solver = ADFLOW(options=options)
    solver(ap)

    funcs = {}
    solver.evalFunctions(ap, funcs)
    solver.checkSolutionFailure(ap, funcs)

    if MPI.COMM_WORLD.rank == 0:
        report = {
            "schema": "aeris.cfd.adflow_run.v1",
            "solve_failed": bool(funcs.get("fail", False)),
            "functions": {k: float(v) for k, v in funcs.items() if k != "fail"},
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
                refs={"area_ref": case["area_ref"], "chord_ref": case["chord_ref"]},
                convergence=convergence,
                artifacts={"log": str(log_path)},
            )
            write_solve_report(workdir, report)
            return report

        run = json.loads(run_json.read_text(encoding="utf-8"))
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
            refs={"area_ref": case["area_ref"], "chord_ref": case["chord_ref"]},
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
