"""Run SU2 and ADflow as managed subprocesses, streaming residuals as they land.

A workbench must never run a solver inside its own process.  A CFD run holds the
CPU for minutes to hours, and an in-process solver freezes the interface and
takes the session down with it when it diverges.  Both solvers here are launched
as children, their output is parsed line by line on a reader thread, and the UI
polls a snapshot.  That is also what makes the live residual plot possible.

SU2 is a binary in the project venv.  ADflow is a Python module in the conda
`mach-aero` interpreter, so it is driven through a generated runner script - the
same shape as the pyHyp path in `meshing.py`.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import runs
from .environment import REPO_ROOT, S6_DIR, S7_DIR, STRATEGY_DIR, conda_python, worker_env

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR), str(S7_DIR.parent), str(S6_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


SU2_TURBULENCE = {
    "SA": "Spalart-Allmaras, one equation",
    "SA_NEG": "Spalart-Allmaras, negative form",
    "SST": "Menter k-omega SST, two equation",
    "SST_SUST": "Menter SST with sustaining terms",
    "NONE": "Laminar / Euler",
}
SU2_CONVECTIVE = ("ROE", "AUSM", "HLLC", "JST", "SLAU", "AUSMPLUSUP2")
SU2_LIMITERS = ("VENKATAKRISHNAN", "BARTH_JESPERSEN", "VAN_ALBADA_EDGE", "NONE")
SU2_LINEAR_PREC = ("LU_SGS", "ILU", "JACOBI", "LINELET")

ADFLOW_TURBULENCE = {
    "SA": "Spalart-Allmaras",
    "SA (noft2)": "Spalart-Allmaras without ft2",
    "SST": "Menter k-omega SST",
    "k omega wilcox": "Wilcox k-omega",
    "k omega modified": "Modified k-omega",
    "v2f": "v2-f four equation",
}
ADFLOW_SMOOTHERS = ("DADI", "Runge-Kutta")
ADFLOW_EQUATIONS = ("RANS", "Euler", "laminar NS")


@dataclass
class FlowConditions:
    mach: float = 0.20
    alpha_deg: float = 2.0
    beta_deg: float = 0.0
    reynolds: float = 1.0e6
    temperature_k: float = 288.15
    area_ref_m2: float = 1.0
    chord_ref_m: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SU2Settings:
    turbulence: str = "SA"
    convective: str = "ROE"
    limiter: str = "VENKATAKRISHNAN"
    venkat_coefficient: float = 0.5
    muscl: bool = True
    cfl: float = 10.0
    cfl_adaptive: bool = True
    cfl_min_factor: float = 0.1
    cfl_max_factor: float = 2.0
    cfl_ceiling: float = 100.0
    linear_preconditioner: str = "LU_SGS"
    linear_iterations: int = 10
    newton_krylov: bool = False
    multigrid_levels: int = 0
    iterations: int = 2000
    stop_residual: float = -9.0
    processes: int = 1

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# MEASURED, not extrapolated.  The earlier figure of 8000 was inferred from two
# out-of-memory kills; it has since been checked by sampling RSS during real
# ADflow start-ups on this machine, with volume and surface output disabled so
# the writer could not be blamed:
#
#     912 768 cells, 1 rank   -> 9.47 GiB, COMPLETED (11138 B/cell)
#   1 216 128 cells, 1 rank   -> over 10.55 GiB, killed (9319 B/cell and rising)
#   1 621 504 cells, 1 rank   -> over 9.04 GiB, killed
#   1 621 504 cells, 4 ranks  -> over 9.11 GiB total, killed, same peak sooner
#
# Three conclusions, all load-bearing.  The per-cell cost is around 11 KiB, so
# the old 8000 was OPTIMISTIC rather than pessimistic.  Extra MPI ranks do not
# reduce the total - they partition the work, not the footprint - so "use more
# ranks" is not a way out of a memory ceiling.  And the per-cell figure RISES as
# the mesh shrinks (11.1 KiB at 913 k against 9.3 KiB at 1.22 M), which says a
# meaningful part of the footprint is fixed overhead rather than per-cell
# storage; the linear model below therefore over-predicts small meshes slightly,
# which is the safe direction.
#
# Calibrated so the one configuration measured to COMPLETE is allowed and both
# configurations measured to die are refused:
#
#   913 k cells -> 9.6 GiB predicted against a 10.0 GiB budget   ALLOW (ran at 9.47)
#   1.22 M      -> 12.8 GiB predicted                            REFUSE (died)
#   1.62 M      -> 17.0 GiB predicted                            REFUSE (died)
#
# 9.3 KiB is high for structured RANS, and the likely reason is this topology:
# S6's nose and base blocks are two cells across, and ADflow stores two halo
# layers on each side, so those blocks cost roughly three times what their
# interior alone would suggest.  It is a property of the mesh, not a
# misconfiguration.
#
# The allocation arrives in two steps - one at the end of preprocessing, one at
# iteration 0 - which is why a run that has printed its first iteration line has
# NOT yet proved it will survive.
ADFLOW_BYTES_PER_CELL_PER_RANK = 11000
# 0.75 was too strict once the per-cell figure was corrected: the 913 k run
# genuinely used 80% of available memory and completed.
ADFLOW_MEMORY_FRACTION = 0.85


@dataclass
class ADflowSettings:
    equation: str = "RANS"
    turbulence: str = "SA"
    smoother: str = "DADI"
    cfl: float = 1.5
    cfl_coarse: float = 1.25
    multigrid_cycle: str = "sg"
    iterations: int = 1000
    n_subiterations: int = 3
    monitor_variables: tuple[str, ...] = ("resrho", "resturb", "cl", "cd", "cmy", "yplus")
    l2_convergence: float = 1e-8
    # One rank by default.  More ranks means more copies of the grid, not
    # fewer, so raising this makes an out-of-memory kill MORE likely.
    processes: int = 1

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["monitor_variables"] = list(self.monitor_variables)
        return out


# --------------------------------------------------------------------------- #
# Live run state                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class RunState:
    """What the UI polls while a solve is in flight."""

    # A PROCESS state, never a physics one.  "completed" is what a zero exit
    # code entitles the workbench to say; whether the solution converged is
    # decided afterwards by the CFD gates, and is reported separately.
    status: str = "idle"          # idle | running | completed | failed | stopped
    iteration: int = 0
    started_at: float = 0.0
    wall_seconds: float = 0.0
    message: str = ""
    return_code: int | None = None
    history: dict[str, list[float]] = field(default_factory=dict)
    log_tail: list[str] = field(default_factory=list)
    output_dir: str = ""

    def snapshot(self, *, log_lines: int = 220) -> dict[str, Any]:
        return {
            "status": self.status,
            "iteration": self.iteration,
            "wall_seconds": round(self.wall_seconds, 1),
            "message": self.message,
            "return_code": self.return_code,
            "history": {k: list(v) for k, v in self.history.items()},
            "log_tail": self.log_tail[-log_lines:],
            "output_dir": self.output_dir,
        }


class SolverRun:
    """One solver process, with its output parsed on a reader thread."""

    def __init__(self, name: str):
        self.name = name
        self.state = RunState()
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # -- lifecycle ------------------------------------------------------- #

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        """Ask the solver to stop; escalate if it will not."""
        self._stop.set()
        process = self._process
        if process is None or process.poll() is not None:
            return
        with self._lock:
            self.state.message = "stopping"
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
        with self._lock:
            self.state.status = "stopped"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self.running:
                self.state.wall_seconds = time.time() - self.state.started_at
            return self.state.snapshot()

    # -- internals ------------------------------------------------------- #

    def _record(self, field_values: dict[str, float]) -> None:
        with self._lock:
            for key, value in field_values.items():
                self.state.history.setdefault(key, []).append(float(value))
            if "iteration" in field_values:
                self.state.iteration = int(field_values["iteration"])

    def _log(self, line: str) -> None:
        with self._lock:
            self.state.log_tail.append(line)
            if len(self.state.log_tail) > 4000:
                del self.state.log_tail[:2000]

    def _launch(self, command: list[str], *, cwd: Path, env: dict[str, str],
                parser: Callable[[str], dict[str, float] | None],
                log_path: Path,
                on_finish: Callable[[int], None] | None = None) -> None:
        self.state = RunState(status="running", started_at=time.time(), output_dir=str(cwd))
        self._stop.clear()
        self._log("$ " + " ".join(command))

        def worker() -> None:
            try:
                with log_path.open("w", encoding="utf-8") as handle:
                    self._process = subprocess.Popen(
                        command, cwd=str(cwd), stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
                    for line in self._process.stdout:  # type: ignore[union-attr]
                        handle.write(line)
                        text = line.rstrip("\n")
                        self._log(text)
                        try:
                            parsed = parser(text)
                        except Exception:  # noqa: BLE001 - a bad line must not kill the run
                            parsed = None
                        if parsed:
                            self._record(parsed)
                    code = self._process.wait()
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self.state.status = "failed"
                    self.state.message = f"{type(exc).__name__}: {exc}"
                return
            with self._lock:
                self.state.return_code = code
                self.state.wall_seconds = time.time() - self.state.started_at
                if self._stop.is_set():
                    self.state.status = "stopped"
                elif code == 0:
                    # NOT "converged".  A solver that limit-cycles for a
                    # thousand iterations and then hits its cycle cap exits
                    # zero, and the old workbench reported that as convergence.
                    self.state.status = "completed"
                    self.state.message = ("process exited cleanly; convergence is "
                                          "decided by the CFD gates")
                else:
                    self.state.status = "failed"
                    self.state.message = f"exit code {code}"
            if on_finish:
                try:
                    on_finish(code)
                except Exception:  # noqa: BLE001
                    pass

        self._thread = threading.Thread(target=worker, daemon=True, name=f"{self.name}-reader")
        self._thread.start()


# --------------------------------------------------------------------------- #
# SU2                                                                           #
# --------------------------------------------------------------------------- #

_SU2_HEADER = re.compile(r"\|\s*Inner_Iter\s*\|")
_SU2_NUMBER = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


class SU2Runner(SolverRun):
    """SU2 8.5, driven from the study's own fixed configuration."""

    def __init__(self) -> None:
        super().__init__("SU2")
        self._columns: list[str] = []

    def write_config(self, mesh_path: Path, flow: FlowConditions,
                     settings: SU2Settings, output_dir: Path) -> Path:
        from S7_unstructured_gmsh_su2 import su2_pipeline as su2

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        options = su2.fixed_su2_options(
            Path(mesh_path),
            flow={"mach": flow.mach, "alpha": flow.alpha_deg,
                  "reynolds": flow.reynolds, "temperature": flow.temperature_k},
            references={"area_ref": flow.area_ref_m2, "chord_ref": flow.chord_ref_m},
            iterations=int(settings.iterations),
            restart=False,
        )
        # The workbench's own solver choices, applied on top of the frozen block.
        options.update({
            "KIND_TURB_MODEL": settings.turbulence,
            "CONV_NUM_METHOD_FLOW": settings.convective,
            "MUSCL_FLOW": "YES" if settings.muscl else "NO",
            "SLOPE_LIMITER_FLOW": settings.limiter,
            "VENKAT_LIMITER_COEFF": settings.venkat_coefficient,
            "CFL_NUMBER": settings.cfl,
            "CFL_ADAPT": "YES" if settings.cfl_adaptive else "NO",
            "CFL_ADAPT_PARAM": (f"( {settings.cfl_min_factor}, {settings.cfl_max_factor}, "
                                f"1.0, {settings.cfl_ceiling} )"),
            "LINEAR_SOLVER_PREC": settings.linear_preconditioner,
            "LINEAR_SOLVER_ITER": int(settings.linear_iterations),
            "CONV_RESIDUAL_MINVAL": float(settings.stop_residual),
        })
        # Turning the turbulence model off means this is no longer a RANS solve;
        # leaving SOLVER= RANS with KIND_TURB_MODEL= NONE is rejected by SU2.
        if settings.turbulence == "NONE":
            options["SOLVER"] = "NAVIER_STOKES"
            options.pop("KIND_TURB_MODEL", None)
            for key in ("CONV_NUM_METHOD_TURB", "MUSCL_TURB", "SLOPE_LIMITER_TURB",
                        "TIME_DISCRE_TURB", "CFL_REDUCTION_TURB"):
                options.pop(key, None)
        if settings.newton_krylov:
            options["NEWTON_KRYLOV"] = "YES"
        if settings.multigrid_levels > 0:
            options.update({
                "MGLEVEL": int(settings.multigrid_levels),
                "MGCYCLE": "V_CYCLE",
                "MG_PRE_SMOOTH": "( 1, 2, 3, 3 )",
                "MG_POST_SMOOTH": "( 0, 0, 0, 0 )",
                "MG_CORRECTION_SMOOTH": "( 0, 0, 0, 0 )",
                "MG_DAMP_RESTRICTION": 0.75,
                "MG_DAMP_PROLONGATION": 0.75,
            })
        else:
            options["MGLEVEL"] = 0

        # SU2 prints a short default screen table that carries neither the forces
        # nor the turbulence residual, so a live plot built from it would show a
        # flat zero for CL and CD.  Ask for the channels the workbench charts.
        # Verified against SU2 8.5: an unknown screen field is dropped SILENTLY,
        # so a wrong name here shows as a channel that is simply never plotted
        # rather than as an error.  These four were confirmed by running the
        # solver and reading back the header it printed.
        turbulence_fields = {
            "SA": ["RMS_NU_TILDE"], "SA_NEG": ["RMS_NU_TILDE"],
            "SST": ["RMS_TKE", "RMS_DISSIPATION"],
            "SST_SUST": ["RMS_TKE", "RMS_DISSIPATION"],
            "NONE": [],
        }.get(settings.turbulence, [])
        screen = (["INNER_ITER", "RMS_DENSITY", "RMS_MOMENTUM-X", "RMS_ENERGY"]
                  + turbulence_fields + ["LIFT", "DRAG", "MOMENT_Y"])
        options["SCREEN_OUTPUT"] = "( " + ", ".join(screen) + " )"
        # The study only needs the surface; a workbench has to be able to slice
        # the field, so ask for the volume in Paraview form too.
        options["OUTPUT_FILES"] = "( RESTART, SURFACE_CSV, SURFACE_PARAVIEW_ASCII, PARAVIEW_ASCII )"
        options["VOLUME_FILENAME"] = "volume_flow"
        options["VOLUME_OUTPUT"] = "( COORDINATES, SOLUTION, PRIMITIVE )"
        options["SCREEN_WRT_FREQ_INNER"] = 1
        options["HISTORY_OUTPUT"] = "( ITER, RMS_RES, AERO_COEFF )"

        config = output_dir / "case.cfg"
        config.write_text("\n".join(f"{k}= {v}" for k, v in options.items()) + "\n",
                          encoding="utf-8")
        (output_dir / "workbench_solver.json").write_text(
            json.dumps({"flow": flow.as_dict(), "settings": settings.as_dict()}, indent=2),
            encoding="utf-8")
        return config

    def _parse(self, line: str) -> dict[str, float] | None:
        """Read SU2's screen table without assuming a fixed column order."""
        if _SU2_HEADER.search(line):
            self._columns = [c.strip() for c in line.strip().strip("|").split("|")]
            return None
        if not self._columns or not line.startswith("|"):
            return None
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(self._columns):
            return None
        out: dict[str, float] = {}
        for name, cell in zip(self._columns, cells, strict=True):
            if not _SU2_NUMBER.fullmatch(cell.replace(" ", "")):
                return None
            key = {"Inner_Iter": "iteration", "Inner_Iter ": "iteration", "rms[Rho]": "rms_rho",
                   "rms[RhoU]": "rms_rhou", "rms[RhoV]": "rms_rhov",
                   "rms[RhoW]": "rms_rhow", "rms[RhoE]": "rms_rhoe",
                   "rms[nu]": "rms_nu", "rms[k]": "rms_k", "rms[w]": "rms_omega",
                   "CL": "CL", "CD": "CD", "CMy": "CMy", "CMx": "CMx", "CMz": "CMz",
                   "CFx": "CFx", "CFy": "CFy", "CFz": "CFz"}.get(name, name)
            try:
                out[key] = float(cell)
            except ValueError:
                return None
        return out or None

    def start(self, mesh_path: Path, flow: FlowConditions, settings: SU2Settings,
              output_dir: Path) -> Path:
        config = self.write_config(mesh_path, flow, settings, output_dir)
        binary = shutil.which("SU2_CFD")
        if binary is None:
            raise RuntimeError("SU2_CFD is not on PATH")
        command = ([binary, config.name] if settings.processes <= 1
                   else ["mpirun", "-n", str(settings.processes), binary, config.name])
        self._columns = []
        self._launch(command, cwd=Path(output_dir), env=worker_env(),
                     parser=self._parse, log_path=Path(output_dir) / "su2_stdout.log")
        return config

    @staticmethod
    def read_history(output_dir: Path) -> dict[str, list[float]]:
        path = Path(output_dir) / "history.csv"
        if not path.is_file():
            return {}
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        if len(rows) < 2:
            return {}
        headers = [h.strip().strip('"') for h in rows[0]]
        out: dict[str, list[float]] = {h: [] for h in headers}
        for row in rows[1:]:
            if len(row) != len(headers):
                continue
            for name, cell in zip(headers, row, strict=True):
                try:
                    out[name].append(float(cell))
                except ValueError:
                    pass
        return {k: v for k, v in out.items() if v}


# --------------------------------------------------------------------------- #
# ADflow                                                                        #
# --------------------------------------------------------------------------- #

_ADFLOW_ROW = re.compile(r"^\s*\d+\s+\d+\s+\d+")

#: The AeroProblem name, and therefore the stem ADflow gives its surface
#: solution.  S6 globs `aeris_cfd*_surf.cgns`, so this is what makes its wall-y+
#: gate applicable to a workbench run.
ADFLOW_PROBLEM_NAME = "aeris_cfd_workbench"
ADFLOW_RESULT_NAME = "adflow_result.json"

ADFLOW_RUNNER = '''"""Generated by the AERIS workbench - one ADflow solve."""
import json, sys
from pathlib import Path
from mpi4py import MPI
from adflow import ADFLOW
from baseclasses import AeroProblem

spec = json.loads(Path("adflow_case.json").read_text())
options = dict(spec["options"])
options["gridFile"] = spec["grid_file"]
options["outputDirectory"] = "."

solver = ADFLOW(options=options, comm=MPI.COMM_WORLD)
flow = spec["flow"]
problem = AeroProblem(
    name=spec["name"],
    mach=flow["mach"],
    alpha=flow["alpha_deg"],
    beta=flow["beta_deg"],
    reynolds=flow["reynolds"],
    reynoldsLength=flow["chord_ref_m"],
    T=flow["temperature_k"],
    areaRef=flow["area_ref_m2"],
    chordRef=flow["chord_ref_m"],
    evalFuncs=["cl", "cd", "cmy"],
)
solver(problem)
funcs = {}
solver.evalFunctions(problem, funcs)
if MPI.COMM_WORLD.rank == 0:
    Path("adflow_result.json").write_text(json.dumps(
        {k: (float(v) if isinstance(v, (int, float)) else str(v)) for k, v in funcs.items()},
        indent=2))
    print("ADFLOW_RESULT " + json.dumps({k: str(v) for k, v in funcs.items()}))
'''


class ADflowRunner(SolverRun):
    """ADflow, launched in the conda interpreter under MPI."""

    def __init__(self) -> None:
        super().__init__("ADflow")
        self._columns: list[str] = []

    def write_case(self, grid_file: Path, flow: FlowConditions,
                   settings: ADflowSettings, output_dir: Path) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        options = {
            "equationType": settings.equation,
            "turbulenceModel": settings.turbulence,
            "smoother": settings.smoother,
            "CFL": settings.cfl,
            "CFLCoarse": settings.cfl_coarse,
            "MGCycle": settings.multigrid_cycle,
            "nCycles": int(settings.iterations),
            "nSubiterTurb": int(settings.n_subiterations),
            "monitorvariables": list(settings.monitor_variables),
            "L2Convergence": settings.l2_convergence,
            "useNKSolver": False,
            "printIterations": True,
            "writeVolumeSolution": True,
            "writeSurfaceSolution": True,
            "volumeVariables": ["cp", "mach", "rmach", "resrho"],
            "surfaceVariables": ["cp", "yplus", "cf", "vx", "vy", "vz"],
        }
        spec = {
            # The generated runner passes this straight to `AeroProblem(name=)`,
            # and ADflow names its surface solution after it.  `aeris_cfd_*` is
            # what S6's own wall-y+ gate globs for
            # (`campaign._wall_yplus_gate`: `aeris_cfd*_surf.cgns`), so naming
            # the problem this way lets the workbench reuse that gate rather
            # than reimplement the y+ limits with its own CGNS reader.
            "name": ADFLOW_PROBLEM_NAME,
            "grid_file": str(Path(grid_file).resolve()),
            "options": options,
            "flow": flow.as_dict(),
            "settings": settings.as_dict(),
        }
        (output_dir / "adflow_case.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        runner = output_dir / "adflow_runner.py"
        runner.write_text(ADFLOW_RUNNER, encoding="utf-8")
        return runner

    def _parse(self, line: str) -> dict[str, float] | None:
        """ADflow prints a fixed-width iteration table; take it positionally."""
        if "Iter" in line and "Res rho" in line.replace("  ", " "):
            self._columns = [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]
            return None
        if not _ADFLOW_ROW.match(line):
            return None
        cells = line.split()
        if len(cells) < 5:
            return None
        try:
            values = [float(c) for c in cells]
        except ValueError:
            return None
        # Grid / Iter / Iter_Tot / Iter_Type ... then the monitored variables.
        out: dict[str, float] = {"iteration": values[1]}
        names = ["rms_rho", "rms_turb", "CL", "CD", "CMy", "yplus"]
        for name, value in zip(names, values[3:], strict=False):
            out[name] = value
        return out

    @staticmethod
    def memory_forecast(cells: int, ranks: int) -> dict[str, Any]:
        """Will this fit? Answer before mpirun, not after the OOM killer does."""
        from .environment import available_memory_gib

        need = cells * ADFLOW_BYTES_PER_CELL_PER_RANK * max(1, ranks) / (1024 ** 3)
        have = available_memory_gib()
        budget = have * ADFLOW_MEMORY_FRACTION
        return {
            "cells": int(cells),
            "ranks": int(max(1, ranks)),
            "estimated_gib": round(need, 2),
            "available_gib": round(have, 2),
            "budget_gib": round(budget, 2),
            "fits": need <= budget,
        }

    def start(self, grid_file: Path, flow: FlowConditions, settings: ADflowSettings,
              output_dir: Path, *, cells: int = 0, allow_over_budget: bool = False) -> Path:
        # The forecast is ADVISORY.  `ADFLOW_BYTES_PER_CELL_PER_RANK` is a lower
        # bound recovered from two OOM kills, not a measured peak, and published
        # ADflow RANS runs sit nearer 1-3 KiB per cell - so this over-predicts
        # far more often than it under-predicts.  Refusing outright on that
        # basis takes a decision away from the person whose machine it is.  The
        # default still declines, loudly, and `allow_over_budget` lets the user
        # say "run it anyway" for their own hardware.
        if cells and not allow_over_budget:
            forecast = self.memory_forecast(cells, settings.processes)
            if not forecast["fits"]:
                raise MemoryError(
                    f"ADflow needs about {forecast['estimated_gib']} GiB for "
                    f"{forecast['cells']:,} cells on {forecast['ranks']} rank(s), "
                    f"and only {forecast['budget_gib']} GiB of the "
                    f"{forecast['available_gib']} GiB free is safe to use. "
                    "Reduce the CELL COUNT, which is the surface quad count "
                    "times the wall-normal layers. Both halves are reachable in "
                    "experimental mode, and the wall-normal count is usually the "
                    "better one to cut first - it shrinks the volume without "
                    "coarsening the surface that carries tip-cap quality. Note "
                    "that dropping below about N97 costs quality: the same "
                    "march distance over fewer layers stretches every cell.\n\n"
                    "Adding MPI ranks will NOT help - measured on this machine, "
                    "1 rank and 4 ranks peak at the same total. L3 and L4 are "
                    "not the answer either: they ask pyHyp to coarsen fourfold, "
                    "which S6's surface cannot survive.\n\n"
                    "This figure is a MEASURED peak, not a guess, and it was "
                    "still climbing when sampling stopped - so overriding it is "
                    "unlikely to end well."
                )
        runner = self.write_case(grid_file, flow, settings, output_dir)
        command = ["mpirun", "-n", str(max(1, settings.processes)),
                   str(conda_python()), runner.name]
        self._columns = []
        self._launch(command, cwd=Path(output_dir), env=worker_env(),
                     parser=self._parse, log_path=Path(output_dir) / "adflow_stdout.log")
        return runner

    @staticmethod
    def read_result(output_dir: Path, *, produced_after: float | None = None) -> dict[str, Any]:
        """This run's forces, or nothing.

        `produced_after` is the moment the solve was launched.  Without it a
        failed rerun in a reused directory handed back the PREVIOUS run's
        `adflow_result.json` and the interface showed those forces as current.
        Unique run directories make that impossible by construction; this is the
        second lock on the same door, for any caller that reuses a directory.
        """
        path = Path(output_dir) / ADFLOW_RESULT_NAME
        if not path.is_file():
            return {}
        if produced_after is not None:
            artifact = runs.claim_output(path, produced_after=produced_after)
            if not artifact.fresh:
                return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}


# --------------------------------------------------------------------------- #
# CFD acceptance                                                                #
# --------------------------------------------------------------------------- #
#
# A solver process returning zero means the process finished.  It says nothing
# about whether the answer is worth having: ADflow exits cleanly after hitting
# its cycle cap while limit-cycling, and it exits cleanly having produced nan
# forces on a grid with negative volumes.  The old workbench called both of
# those "converged".
#
# S6 already decides this question, in `campaign.solve_case`, with five gates.
# Every one of them is REUSED here rather than reimplemented - `_force_tail_gate`,
# `_force_plausibility_gate` and `_wall_yplus_gate` are the study's functions,
# and the residual threshold is its 6.0 orders.  A second implementation of a
# gate is a second opinion, and the study's is the one that counts.

CFD_RESIDUAL_ORDERS_MIN = 6.0
CFD_FORCE_TAIL_RELATIVE_RANGE_MAX = 0.001


def adflow_cfd_verdict(output_dir: Path, *, return_code: int | None,
                       started_at: float | None = None,
                       log_name: str = "adflow_stdout.log") -> dict[str, Any]:
    """Apply S6's CFD acceptance gates to a workbench ADflow run."""
    import campaign  # noqa: PLC0415

    from aeris.cfd.solvers.adflow.parse import parse_monitor_history  # noqa: PLC0415

    output_dir = Path(output_dir)
    log_path = output_dir / log_name
    raw = ADflowRunner.read_result(output_dir, produced_after=started_at)
    # ADflow keys evalFunctions as "<problem>_<func>"; S6's gates want bare
    # coefficient names, and this is the same normalisation its adapter does.
    forces = {
        (key.split("_")[-1] if "_" in key else key).lower(): float(value)
        for key, value in raw.items() if isinstance(value, (int, float))
    }

    convergence: dict[str, Any] = {}
    if log_path.is_file():
        convergence = dict(parse_monitor_history(log_path.read_text(encoding="utf-8")))
    orders = convergence.get("orders_dropped")
    residual_passed = orders is not None and float(orders) >= CFD_RESIDUAL_ORDERS_MIN

    plausibility = campaign._force_plausibility_gate(forces)
    if log_path.is_file():
        force_tail = campaign._force_tail_gate(
            log_path, relative_range_max=CFD_FORCE_TAIL_RELATIVE_RANGE_MAX)
    else:
        force_tail = {"passed": False, "reason": "no solver log"}
    yplus, _surface = campaign._wall_yplus_gate(output_dir)

    finite_forces = not plausibility["missing"] and not plausibility["nonfinite"]
    rows = [
        _cfd_row("solver return code", return_code, "0", return_code == 0),
        _cfd_row("forces recorded", sorted(forces) or "none",
                 "cl, cd, cmy present", not plausibility["missing"]),
        _cfd_row("finite forces", plausibility["nonfinite"] or "all finite",
                 "no nan or inf", finite_forces),
        _cfd_row("positive drag", forces.get("cd"), "> 0",
                 bool(plausibility["positive_drag"])),
        _cfd_row("residual reduction", orders,
                 f">= {CFD_RESIDUAL_ORDERS_MIN:g} orders", bool(residual_passed)),
        _cfd_row("force tail stability", force_tail.get("relative_ranges"),
                 f"relative range <= {CFD_FORCE_TAIL_RELATIVE_RANGE_MAX:g}",
                 bool(force_tail.get("passed"))),
        _cfd_row("wall y+", yplus.get("percentiles"),
                 "p95 <= 1, p99 <= 2, max <= 5", bool(yplus.get("passed"))),
    ]
    failed = [row["gate"] for row in rows if not row["passed"]]
    accepted = not failed
    return {
        "mode": "experimental",
        "state": "CFD_ACCEPTED" if accepted else "CFD_REJECTED",
        "accepted": accepted,
        "return_code": return_code,
        "forces": forces,
        "residual_orders_dropped": orders,
        "residual_gate_passed": bool(residual_passed),
        "finite_forces": finite_forces,
        "force_plausibility_gate": plausibility,
        "force_tail_gate": force_tail,
        "wall_yplus_gate": yplus,
        "rows": rows,
        "failed": failed,
    }


def _cfd_row(name: str, actual: Any, limit: str, passed: bool) -> dict[str, Any]:
    if isinstance(actual, float):
        shown = f"{actual:.6g}"
    elif isinstance(actual, dict):
        shown = ", ".join(f"{k} {v:.3g}" if isinstance(v, float) else f"{k} {v}"
                          for k, v in list(actual.items())[:3]) or "none"
    elif isinstance(actual, (list, tuple)):
        shown = ", ".join(str(v) for v in actual[:4]) or "none"
    else:
        shown = "-" if actual is None else str(actual)
    return {"gate": name, "actual": shown, "limit": limit, "passed": bool(passed)}


RESIDUAL_LABELS = {
    "rms_rho": "Density",
    "rms_rhou": "X-momentum",
    "rms_rhov": "Y-momentum",
    "rms_rhow": "Z-momentum",
    "rms_rhoe": "Energy",
    "rms_nu": "Turbulence (SA)",
    "rms_k": "Turbulence k",
    "rms_omega": "Turbulence omega",
    "rms_turb": "Turbulence",
}
FORCE_LABELS = {"CL": "Lift", "CD": "Drag", "CMy": "Pitching moment",
                "CMx": "Rolling moment", "CMz": "Yawing moment", "yplus": "y+"}
