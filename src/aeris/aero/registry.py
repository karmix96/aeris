from __future__ import annotations

from typing import Type

from .base import AeroSolver

_SOLVER_REGISTRY: dict[str, Type[AeroSolver]] = {}


def register_solver(solver_cls: Type[AeroSolver]) -> Type[AeroSolver]:
    solver_id = getattr(solver_cls, "solver_id", None)
    if not solver_id:
        raise ValueError("Solver class must define a non-empty solver_id.")
    if solver_id in _SOLVER_REGISTRY:
        raise ValueError(f"Solver '{solver_id}' is already registered.")
    _SOLVER_REGISTRY[solver_id] = solver_cls
    return solver_cls


def get_solver_class(solver_id: str) -> Type[AeroSolver]:
    try:
        return _SOLVER_REGISTRY[solver_id]
    except KeyError as exc:
        available = ", ".join(sorted(_SOLVER_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown aero solver '{solver_id}'. Available: {available}") from exc


def create_solver(solver_id: str) -> AeroSolver:
    solver_cls = get_solver_class(solver_id)
    return solver_cls()


def list_solvers() -> list[str]:
    return sorted(_SOLVER_REGISTRY.keys())
