from __future__ import annotations

from typing import Dict, Type

from aeris.aero.base import AeroSolver


_AERO_SOLVERS: Dict[str, Type[AeroSolver]] = {}


def register_aero_solver(solver_cls: Type[AeroSolver]) -> Type[AeroSolver]:
    """
    Class decorator for registering aero solvers.
    """
    solver_id = getattr(solver_cls, "SOLVER_ID", None)
    if not solver_id:
        raise ValueError(
            f"Cannot register aero solver {solver_cls.__name__}: "
            "missing class attribute 'SOLVER_ID'."
        )

    if solver_id in _AERO_SOLVERS:
        raise ValueError(f"Aero solver '{solver_id}' is already registered.")

    _AERO_SOLVERS[solver_id] = solver_cls
    return solver_cls


def get_aero_solver(solver_id: str) -> AeroSolver:
    """
    Instantiate and return a registered aero solver by ID.
    """
    try:
        solver_cls = _AERO_SOLVERS[solver_id]
    except KeyError as exc:
        available = ", ".join(sorted(_AERO_SOLVERS)) or "<none>"
        raise KeyError(
            f"Unknown aero solver '{solver_id}'. "
            f"Available solvers: {available}"
        ) from exc

    return solver_cls()


def list_aero_solvers() -> list[str]:
    """
    Return sorted registered aero solver IDs.
    """
    return sorted(_AERO_SOLVERS.keys())