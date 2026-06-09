"""
Typed domain models for the AERIS aero layer.

These models define the canonical input/output contract between geometry views,
solver adapters, sweep orchestration, validation, and result persistence.
The current v1 geometry carrier is an AeroGeometryView that wraps an
AeroSandbox airplane object, but the view type is intentionally designed to
allow future geometry representations without changing solver-facing contracts.
"""

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
    control_input_deg_values: list[float] = field(default_factory=list)
    diff_input_deg_values: list[float] = field(default_factory=list)
    # diff_input_deg_values: independent differential-elevon sweep.
    # Each value is one delta_a_diff_deg run with delta_e_sym_deg = 0.
    # Not combined with control_input_deg_values (independent, not product).


@dataclass(slots=True)
class AeroSweepCaseInput:
    flight_condition: FlightCondition
    control_input_deg: float | None = None
    diff_input_deg: float | None = None
    sweep_type: str = 'sym'  # 'sym' | 'diff'


@dataclass(slots=True)
class AeroSweepResult:
    cases: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class AeroGeometryView:
    """
    Solver-ready geometry view for the aero layer.

    Current contract:
    - `airplane` must be an AeroSandbox-compatible airplane object.
    - It must provide, at minimum:
        - wings
        - s_ref
        - b_ref
        - c_ref
    - This view is the geometry/aero boundary object.
    - Solver adapters should depend on this view, not on geometry generator internals.

    Additional control-surface contract:
    - `has_control_surfaces` is the explicit geometry-level truth used by the aero layer.
    - `control_surface_names` carries the unique declared/discovered control names.
    - `metadata` may include reconstruction/native provenance plus
      `control_surface_summary` when available.

    Notes:
    - The `airplane` field remains typed as `Any` for now to avoid premature hard
      coupling, but the intended runtime contract is explicit.
    """

    view_id: str
    airplane: Any
    source_generator: str
    source_geometry_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    has_control_surfaces: bool = False
    control_surface_names: tuple[str, ...] = ()


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