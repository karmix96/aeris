"""
Solver adapter contract: prepare → run → parse → normalized SolveReport.

Every solver (ADflow now, SU2 next, OpenFOAM on the roadmap) implements the
same three-step contract so grid-convergence studies and cross-solver
verification (ASME V&V 20 style: identical CGNS grids, different codes)
compare one normalized report schema instead of N solver-specific outputs.

``prepare`` is pure Python (no solver imports): it writes the resolved
options JSON, the provenance manifest, and a static runner script into the
work directory.  ``run`` launches the external process (MPI subprocess in
the solver's own environment) with optional line streaming for live CLI/GUI
residual displays.  ``parse`` turns whatever the solver wrote into a
``SolveReport`` (schema ``aeris.cfd.solve_report.v1``).
"""

from __future__ import annotations

import json
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aeris.cfd.case.spec import SolveSpec

SOLVE_REPORT_SCHEMA_VERSION = "aeris.cfd.solve_report.v1"


@dataclass(frozen=True)
class PreparedRun:
    """Everything needed to execute a solve; produced by prepare()."""

    solver_id: str
    workdir: Path
    command: tuple[str, ...]
    log_name: str = "solver_run.log"
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SolveReport:
    """Normalized solve outcome — one schema across all solvers."""

    solver_id: str
    status: str  # "converged" | "unconverged" | "failed"
    flow: dict[str, float] = field(default_factory=dict)
    refs: dict[str, float] = field(default_factory=dict)
    forces: dict[str, float] = field(default_factory=dict)
    convergence: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    solver_version: str | None = None
    elapsed_seconds: float | None = None


def write_solve_report(workdir: Path, report: SolveReport) -> Path:
    payload = {"schema": SOLVE_REPORT_SCHEMA_VERSION, **asdict(report)}
    path = workdir / "solve_report.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_solve_report(workdir: Path) -> SolveReport:
    payload = json.loads((workdir / "solve_report.json").read_text(encoding="utf-8"))
    payload.pop("schema", None)
    return SolveReport(**payload)


class SolverAdapter(ABC):
    """One external flow solver, driven through files + subprocess."""

    SOLVER_ID: str = ""

    @abstractmethod
    def prepare(self, solve: SolveSpec, mesh_cgns: Path, workdir: Path) -> PreparedRun:
        """Write runner script, options JSON, and provenance manifest."""

    def run(
        self,
        prepared: PreparedRun,
        *,
        stream: Callable[[str], None] | None = None,
        dry_run: bool = False,
    ) -> int:
        """Execute the prepared command, teeing output to the run log.

        Returns the process exit code (0 for a dry run, which executes
        nothing).  ``stream`` receives each output line for live residual
        display.
        """
        if dry_run:
            return 0
        log_path = prepared.workdir / prepared.log_name
        t0 = time.perf_counter()
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                list(prepared.command),
                cwd=str(prepared.workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                if stream is not None:
                    stream(line.rstrip("\n"))
            returncode = process.wait()
        elapsed = time.perf_counter() - t0
        (prepared.workdir / "run_meta.json").write_text(
            json.dumps({"returncode": returncode, "elapsed_seconds": elapsed}, indent=2),
            encoding="utf-8",
        )
        return returncode

    @abstractmethod
    def parse(self, workdir: Path) -> SolveReport:
        """Normalize solver outputs into a SolveReport (also written to disk)."""


def _adapters() -> dict[str, type[SolverAdapter]]:
    # local imports to avoid import cycles at module load
    from aeris.cfd.solvers.adflow.adapter import AdflowAdapter
    from aeris.cfd.solvers.su2.adapter import Su2Adapter

    return {
        AdflowAdapter.SOLVER_ID: AdflowAdapter,
        Su2Adapter.SOLVER_ID: Su2Adapter,
    }


def get_solver_adapter(solver_id: str) -> SolverAdapter:
    adapters = _adapters()
    if solver_id not in adapters:
        raise ValueError(f"Unknown solver {solver_id!r}. Available: {sorted(adapters)}")
    return adapters[solver_id]()


def list_solver_ids() -> list[str]:
    return sorted(_adapters())
