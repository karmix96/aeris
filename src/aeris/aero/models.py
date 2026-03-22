from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AeroStatus(str, Enum):
    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    SOLVER_FAILED = "solver_failed"
    INVALID_OUTPUT = "invalid_output"


@dataclass(slots=True)
class FlightCondition:
    alpha_deg: float
    beta_deg: float = 0.0
    mach: float = 0.0
    velocity_mps: float = 28.0
    altitude_m: float = 0.0
    p_rad_s: float = 0.0
    q_rad_s: float = 0.0
    r_rad_s: float = 0.0

@dataclass(slots=True)
class FlightConditionSweep:
    alpha_deg_values: list[float] = field(default_factory=list)
    beta_deg_values: list[float] = field(default_factory=list)
    velocity_mps_values: list[float] = field(default_factory=list)
    altitude_m_values: list[float] = field(default_factory=list)
    p_rad_s_values: list[float] = field(default_factory=list)
    q_rad_s_values: list[float] = field(default_factory=list)
    r_rad_s_values: list[float] = field(default_factory=list)


@dataclass(slots=True)
class AeroSweepResult:
    cases: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class AeroGeometryView:
    """
    Canonical v1 geometry input to the aero layer.

    This is intentionally a typed AERIS geometry view that currently wraps an
    AeroSandbox airplane object. Later, other view kinds can coexist without
    changing the solver contract.
    """
    view_id: str
    airplane: Any
    source_generator: str | None = None
    source_geometry_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AeroSolverSettings:
    """
    Common settings + solver-specific options bag.
    """
    avl_command: str | None = None
    timeout_sec: int = 180
    verbose: bool = False
    solver_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AeroInput:
    geometry: AeroGeometryView
    flight_condition: FlightCondition
    settings: AeroSolverSettings
    case_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AeroFailure:
    status: AeroStatus
    reason: str
    message: str
    exception_type: str | None = None


@dataclass(slots=True)
class AeroResult:
    status: AeroStatus
    solver_id: str

    cl: float | None = None
    cd: float | None = None
    cm: float | None = None
    l_over_d: float | None = None

    cy: float | None = None
    cl_roll: float | None = None
    cn: float | None = None

    cd_ind: float | None = None
    cd_ff: float | None = None
    span_efficiency: float | None = None
    x_np: float | None = None


    # NEW: explicit derivative-family separation
    stability_axis_derivatives: dict[str, float | None] = field(default_factory=dict)
    body_axis_derivatives: dict[str, float | None] = field(default_factory=dict)

    # NEW: derived scalar metrics computed from the correct family only
    derived_metrics: dict[str, float | None] = field(default_factory=dict)

    runtime_sec: float | None = None

    warnings: list[str] = field(default_factory=list)

    artifact_paths: dict[str, str | None] = field(default_factory=dict)
    raw_outputs: dict[str, Any] = field(default_factory=dict)
    solver_metadata: dict[str, Any] = field(default_factory=dict)

    failure: AeroFailure | None = None

    def is_success(self) -> bool:
        return self.status == AeroStatus.SUCCESS