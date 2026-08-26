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
import queue
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

from .environment import REPO_ROOT, S7_DIR, STRATEGY_DIR, conda_python, worker_env

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR), str(S7_DIR.parent)):
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


# Measured on this machine: ADflow was OOM-killed at iteration 0 on a 1 621 504
# cell mesh with two ranks and 9.9 GiB available, having survived preprocessing.
# Every rank reads the whole grid before partitioning, so cost scales with ranks
# rather than being divided by them, and the ANK solver allocates again on the
# first real iteration.  9.9 GiB / 1.62 M cells / 2 ranks is about 3.1 KiB per
# cell per rank at the point it died, so this is a floor rather than a fit.
ADFLOW_BYTES_PER_CELL_PER_RANK = 3300
ADFLOW_MEMORY_FRACTION = 0.80


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

    status: str = "idle"          # idle | running | converged | diverged | failed | stopped
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
                    self.state.status = "converged"
                    self.state.message = "solver exited cleanly"
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
        for name, cell in zip(self._columns, cells):
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
            for name, cell in zip(headers, row):
                try:
                    out[name].append(float(cell))
                except ValueError:
                    pass
        return {k: v for k, v in out.items() if v}


# --------------------------------------------------------------------------- #
# ADflow                                                                        #
# --------------------------------------------------------------------------- #

_ADFLOW_ROW = re.compile(r"^\s*\d+\s+\d+\s+\d+")

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
            "name": "workbench",
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
        for name, value in zip(names, values[3:]):
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
              output_dir: Path, *, cells: int = 0) -> Path:
        if cells:
            forecast = self.memory_forecast(cells, settings.processes)
            if not forecast["fits"]:
                raise MemoryError(
                    f"ADflow needs about {forecast['estimated_gib']} GiB for "
                    f"{forecast['cells']:,} cells on {forecast['ranks']} rank(s), "
                    f"and only {forecast['budget_gib']} GiB of the "
                    f"{forecast['available_gib']} GiB free is safe to use. "
                    "Mesh a coarser volume level (L4 or L3 coarsen the surface "
                    "fourfold) or drop to one rank - every rank holds its own "
                    "copy of the grid, so more ranks need more memory, not less."
                )
        runner = self.write_case(grid_file, flow, settings, output_dir)
        command = ["mpirun", "-n", str(max(1, settings.processes)),
                   str(conda_python()), runner.name]
        self._columns = []
        self._launch(command, cwd=Path(output_dir), env=worker_env(),
                     parser=self._parse, log_path=Path(output_dir) / "adflow_stdout.log")
        return runner

    @staticmethod
    def read_result(output_dir: Path) -> dict[str, Any]:
        path = Path(output_dir) / "adflow_result.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}


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
