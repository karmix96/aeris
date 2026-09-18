"""Typed schema for an auditable open-source structural analysis case."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CASE_SCHEMA_VERSION = "aeris.fea.case.v1"


@dataclass(frozen=True)
class GeometryInput:
    aeris_config: Path | None = None
    stations_file: Path | None = None
    wing_index: int = 0
    seed: int | None = None
    design_matrix_file: Path | None = None
    design_set: str | None = None
    design_index: int | None = None
    freeze_authority_file: Path | None = None
    holdout_authorized: bool = False


@dataclass(frozen=True)
class MissionSpec:
    authority_file: Path


@dataclass(frozen=True)
class OpenAeroStructValidationSpec:
    enabled: bool = False
    cfd_dataset: Path | None = None
    geometry_set: str | None = None
    geometry_index: int | None = None
    grid_level: str = "gci_C"
    chordwise_nodes: int = 5
    max_abs_cl_error: float = 0.08
    max_lift_curve_slope_relative_error: float = 0.15
    max_reference_area_relative_error: float = 0.01


@dataclass(frozen=True)
class WingboxSpec:
    front_spar_fraction: float = 0.15
    rear_spar_fraction: float = 0.65
    depth_ratio: float = 0.12
    minimum_depth_m: float = 0.01
    rib_span_fractions: tuple[float, ...] = ()
    root_doubler_span_fraction: float = 0.0
    hinge_span_start_fraction: float = 0.0
    hinge_span_end_fraction: float = 0.0
    hinge_from_design_vector: bool = False
    cutouts: tuple["CutoutSpec", ...] = ()


@dataclass(frozen=True)
class CutoutSpec:
    surface: str
    span_start_fraction: float
    span_end_fraction: float
    chord_start_fraction: float
    chord_end_fraction: float


@dataclass(frozen=True)
class MeshSpec:
    target_size_m: float = 0.08
    chordwise_elements: int = 8
    depth_elements: int = 2
    max_aspect_ratio: float = 25.0
    min_corner_angle_deg: float = 15.0


@dataclass(frozen=True)
class MaterialSpec:
    name: str
    youngs_modulus_pa: float
    poisson_ratio: float
    density_kg_m3: float
    yield_strength_pa: float


@dataclass(frozen=True)
class SectionSpec:
    skin_thickness_m: float
    spar_thickness_m: float
    rib_thickness_m: float | None = None
    root_doubler_thickness_m: float | None = None
    hinge_reinforcement_thickness_m: float | None = None
    cutout_reinforcement_thickness_m: float | None = None


@dataclass(frozen=True)
class LoadCaseSpec:
    name: str
    pressure_pa: float | None = None
    distribution: str = "elliptical"
    load_factor: float = 1.0
    source: str = "pressure"
    alpha_deg: float | None = None
    aircraft_mass_kg: float | None = None
    direction: float = 1.0


@dataclass(frozen=True)
class SolverSpec:
    solver: str = "calculix"
    executable: str = "ccx"


@dataclass(frozen=True)
class VerificationSpec:
    minimum_safety_factor: float = 1.0
    maximum_displacement_m: float | None = None
    maximum_mass_kg: float | None = None


@dataclass(frozen=True)
class ModalAnalysisSpec:
    enabled: bool = False
    modes: int = 8
    minimum_first_frequency_hz: float = 0.0


@dataclass(frozen=True)
class BucklingAnalysisSpec:
    enabled: bool = False
    modes: int = 5
    load_case: str | None = None
    minimum_load_factor: float = 1.0


@dataclass(frozen=True)
class NonlinearAnalysisSpec:
    enabled: bool = False
    load_cases: tuple[str, ...] = ()
    maximum_linear_displacement_difference: float = 0.10


@dataclass(frozen=True)
class AnalysisSpec:
    modal: ModalAnalysisSpec = field(default_factory=ModalAnalysisSpec)
    buckling: BucklingAnalysisSpec = field(default_factory=BucklingAnalysisSpec)
    nonlinear: NonlinearAnalysisSpec = field(default_factory=NonlinearAnalysisSpec)
    reduced_topology_for_advanced: bool = True


@dataclass(frozen=True)
class CaseSpec:
    name: str
    geometry: GeometryInput
    wingbox: WingboxSpec
    mesh: MeshSpec
    material: MaterialSpec
    section: SectionSpec
    loads: tuple[LoadCaseSpec, ...]
    solver: SolverSpec = field(default_factory=SolverSpec)
    verification: VerificationSpec = field(default_factory=VerificationSpec)
    mission: MissionSpec | None = None
    openaerostruct_validation: OpenAeroStructValidationSpec = field(
        default_factory=OpenAeroStructValidationSpec
    )
    analyses: AnalysisSpec = field(default_factory=AnalysisSpec)
    structural_authority_file: Path | None = None
    validation_evidence_file: Path | None = None
    source_path: Path | None = None
