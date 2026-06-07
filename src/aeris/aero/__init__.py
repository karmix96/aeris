from .base import AeroSolver
from .models import (
    AeroFailure,
    AeroGeometryView,
    AeroInput,
    AeroResult,
    AeroSolverSettings,
    AeroStatus,
    FlightCondition,
)
from .registry import create_solver, get_solver_class, list_solvers, register_solver

# Force registration of built-in solvers when optional solver dependencies exist.
# Keep lightweight submodules such as aeris.aero.control_metadata importable even
# in environments that do not have AeroSandbox installed.
try:
    from .solvers.aerosandbox_avl import AeroSandboxAVLSolver
except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional env
    if exc.name != "aerosandbox":
        raise
    AeroSandboxAVLSolver = None  # type: ignore[assignment]

from .io import find_aero_result_json, load_aero_result, load_aero_result_from_run_dir


__all__ = [
    "AeroSolver",
    "AeroFailure",
    "AeroGeometryView",
    "AeroInput",
    "AeroResult",
    "AeroSolverSettings",
    "AeroStatus",
    "FlightCondition",
    "create_solver",
    "get_solver_class",
    "list_solvers",
    "register_solver",
    "AeroSandboxAVLSolver",
]
