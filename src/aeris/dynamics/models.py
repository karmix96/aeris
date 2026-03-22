from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InertiaPlaceholders:
    ixx_kg_m2: float | None = None
    iyy_kg_m2: float | None = None
    izz_kg_m2: float | None = None
    ixy_kg_m2: float | None = None
    ixz_kg_m2: float | None = None
    iyz_kg_m2: float | None = None
    reference_axes: str = "body"


@dataclass(frozen=True)
class MassProperties:
    mass_kg: float
    x_cg_m: float
    y_cg_m: float = 0.0
    z_cg_m: float = 0.0
    reference_frame: str = "geometry_body_axes"
    source: str = "manual"
    notes: str | None = None
    inertia: InertiaPlaceholders = field(default_factory=InertiaPlaceholders)


@dataclass(frozen=True)
class TrimDefinition:
    enabled: bool = False
    objective: str = "force_moment_balance"
    fixed_variables: dict[str, float] = field(default_factory=dict)
    solve_variables: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class StabilityMetrics:
    x_np_m: float | None
    x_cg_m: float
    mac_m: float | None
    static_margin: float | None
    static_margin_percent_mac: float | None
    cma: float | None = None
    cma_consistent_with_static_margin: bool | None = None
    spiral_metric: float | None = None
    longitudinal_interpretation: str | None = None


@dataclass(frozen=True)
class StateSpacePreparation:
    mass_available: bool
    cg_available: bool
    inertia_available: bool
    xnp_available: bool
    mac_available: bool
    longitudinal_derivatives_available: bool
    lateral_derivatives_available: bool
    ready_for_trim_solver: bool
    ready_for_eigenanalysis: bool
    missing_items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DynamicsFoundationResult:
    schema_version: str
    source_run_dir: str
    source_solver_id: str | None
    operating_point_snapshot: dict[str, Any]
    mass_properties: MassProperties
    trim_definition: TrimDefinition
    stability_metrics: StabilityMetrics
    state_space_preparation: StateSpacePreparation
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)