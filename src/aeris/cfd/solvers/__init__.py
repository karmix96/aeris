"""Solver adapters: prepare/run/parse with one normalized SolveReport."""

from aeris.cfd.solvers.base import (
    SOLVE_REPORT_SCHEMA_VERSION,
    PreparedRun,
    SolverAdapter,
    SolveReport,
    get_solver_adapter,
    list_solver_ids,
)

__all__ = [
    "SOLVE_REPORT_SCHEMA_VERSION",
    "PreparedRun",
    "SolveReport",
    "SolverAdapter",
    "get_solver_adapter",
    "list_solver_ids",
]
