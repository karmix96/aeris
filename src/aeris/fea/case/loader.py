"""Safe YAML loader and fail-fast validation for ``aeris.fea.case.v1``."""

from __future__ import annotations

import math
from pathlib import Path

from aeris.common.config import load_yaml_config
from aeris.common.paths import get_project_root
from aeris.fea.case.spec import (
    CASE_SCHEMA_VERSION,
    AnalysisSpec,
    BucklingAnalysisSpec,
    CaseSpec,
    CutoutSpec,
    GeometryInput,
    LoadCaseSpec,
    MaterialSpec,
    MeshSpec,
    MissionSpec,
    ModalAnalysisSpec,
    NonlinearAnalysisSpec,
    OpenAeroStructValidationSpec,
    SectionSpec,
    SolverSpec,
    VerificationSpec,
    WingboxSpec,
)


def _mapping(raw: object, name: str, *, required: bool = False) -> dict[str, object]:
    if raw is None:
        if required:
            raise ValueError(f"case.{name} is required")
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"case.{name} must be a mapping, got {type(raw).__name__}")
    return dict(raw)


def _number(
    raw: dict[str, object], key: str, section: str, *, default: float | None = None
) -> float:
    value = raw.get(key, default)
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            pass
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"case.{section}.{key} must be a finite number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"case.{section}.{key} must be finite, got {value!r}")
    return result


def _positive(raw: dict[str, object], key: str, section: str, *, default=None) -> float:
    value = _number(raw, key, section, default=default)
    if value <= 0.0:
        raise ValueError(f"case.{section}.{key} must be > 0, got {value}")
    return value


def _positive_int(raw: dict[str, object], key: str, section: str, *, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"case.{section}.{key} must be a positive int, got {value!r}")
    return value


def _string(raw: dict[str, object], key: str, section: str, *, default: str | None = None) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"case.{section}.{key} must be a non-empty string, got {value!r}")
    return value.strip()


def _optional_positive(raw: dict[str, object], key: str, section: str) -> float | None:
    if raw.get(key) is None:
        return None
    return _positive(raw, key, section)


def _fraction(value: object, name: str, *, allow_zero: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"case.{name} must be numeric")
    result = float(value)
    lower_ok = result >= 0.0 if allow_zero else result > 0.0
    if not lower_ok or result > 1.0:
        bracket = "[0, 1]" if allow_zero else "(0, 1]"
        raise ValueError(f"case.{name} must be in {bracket}")
    return result


def _optional_section_thickness(raw: dict[str, object], key: str) -> float | None:
    return None if raw.get(key) is None else _positive(raw, key, "section")


def _analyses(case: dict[str, object], load_names: set[str]) -> AnalysisSpec:
    raw = _mapping(case.get("analyses"), "analyses")
    modal_raw = _mapping(raw.get("modal"), "analyses.modal")
    buckling_raw = _mapping(raw.get("buckling"), "analyses.buckling")
    nonlinear_raw = _mapping(raw.get("nonlinear"), "analyses.nonlinear")
    for section_name, section in (
        ("modal", modal_raw),
        ("buckling", buckling_raw),
        ("nonlinear", nonlinear_raw),
    ):
        if not isinstance(section.get("enabled", False), bool):
            raise ValueError(f"case.analyses.{section_name}.enabled must be a bool")
    modal_enabled = bool(modal_raw.get("enabled", False))
    buckling_enabled = bool(buckling_raw.get("enabled", False))
    nonlinear_enabled = bool(nonlinear_raw.get("enabled", False))
    buckling_load = buckling_raw.get("load_case")
    if buckling_enabled and (
        not isinstance(buckling_load, str) or buckling_load not in load_names
    ):
        raise ValueError("enabled buckling analysis requires a valid load_case")
    nonlinear_loads = nonlinear_raw.get("load_cases", [])
    if not isinstance(nonlinear_loads, list) or not all(
        isinstance(name, str) for name in nonlinear_loads
    ):
        raise ValueError("case.analyses.nonlinear.load_cases must be a string list")
    unknown = sorted(set(nonlinear_loads) - load_names)
    if unknown:
        raise ValueError(f"nonlinear analysis references unknown load cases: {unknown}")
    if nonlinear_enabled and not nonlinear_loads:
        raise ValueError("enabled nonlinear analysis requires at least one load case")
    return AnalysisSpec(
        modal=ModalAnalysisSpec(
            enabled=modal_enabled,
            modes=_positive_int(modal_raw, "modes", "analyses.modal", default=8),
            minimum_first_frequency_hz=_number(
                modal_raw,
                "minimum_first_frequency_hz",
                "analyses.modal",
                default=0.0,
            ),
        ),
        buckling=BucklingAnalysisSpec(
            enabled=buckling_enabled,
            modes=_positive_int(buckling_raw, "modes", "analyses.buckling", default=5),
            load_case=buckling_load if isinstance(buckling_load, str) else None,
            minimum_load_factor=_positive(
                buckling_raw, "minimum_load_factor", "analyses.buckling", default=1.0
            ),
        ),
        nonlinear=NonlinearAnalysisSpec(
            enabled=nonlinear_enabled,
            load_cases=tuple(nonlinear_loads),
            maximum_linear_displacement_difference=_positive(
                nonlinear_raw,
                "maximum_linear_displacement_difference",
                "analyses.nonlinear",
                default=0.10,
            ),
        ),
        reduced_topology_for_advanced=bool(raw.get("reduced_topology_for_advanced", True)),
    )


def _workspace_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (get_project_root() / path).resolve()


def _geometry(case: dict[str, object]) -> GeometryInput:
    raw = _mapping(case.get("geometry"), "geometry", required=True)
    aeris_config = raw.get("aeris_config")
    stations_file = raw.get("stations_file")
    for key, value in (("aeris_config", aeris_config), ("stations_file", stations_file)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"case.geometry.{key} must be a non-empty path string")
    if (aeris_config is None) == (stations_file is None):
        raise ValueError("case.geometry must set exactly one of 'aeris_config' or 'stations_file'")
    wing_index = raw.get("wing_index", 0)
    if isinstance(wing_index, bool) or not isinstance(wing_index, int) or wing_index < 0:
        raise ValueError("case.geometry.wing_index must be a non-negative int")
    seed = raw.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError("case.geometry.seed must be an int")
    design_matrix_file = raw.get("design_matrix_file")
    design_set = raw.get("design_set")
    design_index = raw.get("design_index")
    freeze_authority_file = raw.get("freeze_authority_file")
    holdout_authorized = raw.get("holdout_authorized", False)
    if design_matrix_file is not None and (
        not isinstance(design_matrix_file, str) or not design_matrix_file.strip()
    ):
        raise ValueError("case.geometry.design_matrix_file must be a non-empty path string")
    if design_set is not None and (not isinstance(design_set, str) or not design_set.strip()):
        raise ValueError("case.geometry.design_set must be a non-empty string")
    if design_index is not None and (
        isinstance(design_index, bool) or not isinstance(design_index, int) or design_index < 0
    ):
        raise ValueError("case.geometry.design_index must be a non-negative int")
    if freeze_authority_file is not None and (
        not isinstance(freeze_authority_file, str) or not freeze_authority_file.strip()
    ):
        raise ValueError("case.geometry.freeze_authority_file must be a non-empty path string")
    if not isinstance(holdout_authorized, bool):
        raise ValueError("case.geometry.holdout_authorized must be a bool")
    locked = (design_matrix_file, design_set, design_index)
    if any(value is not None for value in locked) and not all(
        value is not None for value in locked
    ):
        raise ValueError(
            "case.geometry design_matrix_file, design_set, and design_index must be set together"
        )
    if design_matrix_file is not None and aeris_config is None:
        raise ValueError("case.geometry.design_matrix_file requires aeris_config")
    if design_matrix_file is not None and seed is not None:
        raise ValueError("case.geometry must not mix a locked design row with seed sampling")
    return GeometryInput(
        aeris_config=_workspace_path(aeris_config) if aeris_config else None,
        stations_file=_workspace_path(stations_file) if stations_file else None,
        wing_index=wing_index,
        seed=seed,
        design_matrix_file=_workspace_path(design_matrix_file) if design_matrix_file else None,
        design_set=design_set.strip() if isinstance(design_set, str) else None,
        design_index=design_index,
        freeze_authority_file=(
            _workspace_path(freeze_authority_file) if freeze_authority_file else None
        ),
        holdout_authorized=holdout_authorized,
    )


def _mission(case: dict[str, object]) -> MissionSpec | None:
    if case.get("mission") is None:
        return None
    raw = _mapping(case.get("mission"), "mission", required=True)
    path = _string(raw, "authority_file", "mission")
    return MissionSpec(authority_file=_workspace_path(path))


def _oas_validation(case: dict[str, object]) -> OpenAeroStructValidationSpec:
    raw = _mapping(case.get("openaerostruct_validation"), "openaerostruct_validation")
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("case.openaerostruct_validation.enabled must be a bool")
    dataset = raw.get("cfd_dataset")
    geometry_set = raw.get("geometry_set")
    geometry_index = raw.get("geometry_index")
    if enabled:
        if not isinstance(dataset, str) or not dataset.strip():
            raise ValueError("enabled OpenAeroStruct validation requires cfd_dataset")
        if not isinstance(geometry_set, str) or not geometry_set.strip():
            raise ValueError("enabled OpenAeroStruct validation requires geometry_set")
        if isinstance(geometry_index, bool) or not isinstance(geometry_index, int):
            raise ValueError("enabled OpenAeroStruct validation requires integer geometry_index")
    chordwise_nodes = _positive_int(raw, "chordwise_nodes", "openaerostruct_validation", default=5)
    if chordwise_nodes < 3 or chordwise_nodes % 2 == 0:
        raise ValueError("case.openaerostruct_validation.chordwise_nodes must be odd and >= 3")
    return OpenAeroStructValidationSpec(
        enabled=enabled,
        cfd_dataset=_workspace_path(dataset) if isinstance(dataset, str) else None,
        geometry_set=geometry_set.strip() if isinstance(geometry_set, str) else None,
        geometry_index=geometry_index if isinstance(geometry_index, int) else None,
        grid_level=_string(raw, "grid_level", "openaerostruct_validation", default="gci_C"),
        chordwise_nodes=chordwise_nodes,
        max_abs_cl_error=_positive(
            raw, "max_abs_cl_error", "openaerostruct_validation", default=0.08
        ),
        max_lift_curve_slope_relative_error=_positive(
            raw,
            "max_lift_curve_slope_relative_error",
            "openaerostruct_validation",
            default=0.15,
        ),
        max_reference_area_relative_error=_positive(
            raw,
            "max_reference_area_relative_error",
            "openaerostruct_validation",
            default=0.01,
        ),
    )


def case_spec_from_mapping(raw: dict[str, object], *, source_path: Path | None = None) -> CaseSpec:
    if raw.get("schema") != CASE_SCHEMA_VERSION:
        raise ValueError(f"case schema must be {CASE_SCHEMA_VERSION!r}, got {raw.get('schema')!r}")
    case = _mapping(raw.get("case"), "case", required=True)
    name = _string(case, "name", "case")

    wingbox_raw = _mapping(case.get("wingbox"), "wingbox")
    ribs_raw = wingbox_raw.get("rib_span_fractions", [])
    if not isinstance(ribs_raw, list):
        raise ValueError("case.wingbox.rib_span_fractions must be a list")
    ribs = tuple(
        _fraction(value, f"wingbox.rib_span_fractions[{index}]", allow_zero=False)
        for index, value in enumerate(ribs_raw)
    )
    if tuple(sorted(set(ribs))) != ribs or any(value >= 1.0 for value in ribs):
        raise ValueError("case.wingbox.rib_span_fractions must be unique, sorted, and inside (0,1)")
    cutouts_raw = wingbox_raw.get("cutouts", [])
    if not isinstance(cutouts_raw, list):
        raise ValueError("case.wingbox.cutouts must be a list")
    cutouts: list[CutoutSpec] = []
    hinge_from_design = wingbox_raw.get("hinge_from_design_vector", False)
    if not isinstance(hinge_from_design, bool):
        raise ValueError("case.wingbox.hinge_from_design_vector must be a bool")
    for index, value in enumerate(cutouts_raw):
        item = _mapping(value, f"wingbox.cutouts[{index}]")
        surface = _string(item, "surface", f"wingbox.cutouts[{index}]")
        if surface not in {"top", "bottom"}:
            raise ValueError(f"case.wingbox.cutouts[{index}].surface must be top or bottom")
        cutout = CutoutSpec(
            surface=surface,
            span_start_fraction=_fraction(
                item.get("span_start_fraction"),
                f"wingbox.cutouts[{index}].span_start_fraction",
            ),
            span_end_fraction=_fraction(
                item.get("span_end_fraction"), f"wingbox.cutouts[{index}].span_end_fraction"
            ),
            chord_start_fraction=_fraction(
                item.get("chord_start_fraction"),
                f"wingbox.cutouts[{index}].chord_start_fraction",
            ),
            chord_end_fraction=_fraction(
                item.get("chord_end_fraction"), f"wingbox.cutouts[{index}].chord_end_fraction"
            ),
        )
        if cutout.span_start_fraction >= cutout.span_end_fraction or (
            cutout.chord_start_fraction >= cutout.chord_end_fraction
        ):
            raise ValueError(f"case.wingbox.cutouts[{index}] start must be below end")
        cutouts.append(cutout)
    wingbox = WingboxSpec(
        front_spar_fraction=_number(wingbox_raw, "front_spar_fraction", "wingbox", default=0.15),
        rear_spar_fraction=_number(wingbox_raw, "rear_spar_fraction", "wingbox", default=0.65),
        depth_ratio=_positive(wingbox_raw, "depth_ratio", "wingbox", default=0.12),
        minimum_depth_m=_positive(wingbox_raw, "minimum_depth_m", "wingbox", default=0.01),
        rib_span_fractions=ribs,
        root_doubler_span_fraction=_fraction(
            wingbox_raw.get("root_doubler_span_fraction", 0.0),
            "wingbox.root_doubler_span_fraction",
        ),
        hinge_span_start_fraction=_fraction(
            wingbox_raw.get("hinge_span_start_fraction", 0.0),
            "wingbox.hinge_span_start_fraction",
        ),
        hinge_span_end_fraction=_fraction(
            wingbox_raw.get("hinge_span_end_fraction", 0.0),
            "wingbox.hinge_span_end_fraction",
        ),
        hinge_from_design_vector=hinge_from_design,
        cutouts=tuple(cutouts),
    )
    if not 0.0 <= wingbox.front_spar_fraction < wingbox.rear_spar_fraction <= 1.0:
        raise ValueError(
            "case.wingbox spar fractions must satisfy "
            "0 <= front_spar_fraction < rear_spar_fraction <= 1"
        )
    if wingbox.hinge_span_start_fraction > wingbox.hinge_span_end_fraction:
        raise ValueError("case.wingbox hinge span start must not exceed end")
    if wingbox.hinge_from_design_vector and (
        wingbox.hinge_span_start_fraction != 0.0 or wingbox.hinge_span_end_fraction != 0.0
    ):
        raise ValueError("design-vector hinge bounds cannot be combined with explicit hinge bounds")
    for index, cutout in enumerate(wingbox.cutouts):
        if not (
            wingbox.front_spar_fraction < cutout.chord_start_fraction
            < cutout.chord_end_fraction
            < wingbox.rear_spar_fraction
        ):
            raise ValueError(f"case.wingbox.cutouts[{index}] must lie between the spars")

    mesh_raw = _mapping(case.get("mesh"), "mesh")
    mesh = MeshSpec(
        target_size_m=_positive(mesh_raw, "target_size_m", "mesh", default=0.08),
        chordwise_elements=_positive_int(mesh_raw, "chordwise_elements", "mesh", default=8),
        depth_elements=_positive_int(mesh_raw, "depth_elements", "mesh", default=2),
        max_aspect_ratio=_positive(mesh_raw, "max_aspect_ratio", "mesh", default=25.0),
        min_corner_angle_deg=_positive(mesh_raw, "min_corner_angle_deg", "mesh", default=15.0),
    )
    if mesh.min_corner_angle_deg >= 90.0:
        raise ValueError("case.mesh.min_corner_angle_deg must be < 90")

    material_raw = _mapping(case.get("material"), "material", required=True)
    material = MaterialSpec(
        name=_string(material_raw, "name", "material"),
        youngs_modulus_pa=_positive(material_raw, "youngs_modulus_pa", "material"),
        poisson_ratio=_number(material_raw, "poisson_ratio", "material"),
        density_kg_m3=_positive(material_raw, "density_kg_m3", "material"),
        yield_strength_pa=_positive(material_raw, "yield_strength_pa", "material"),
    )
    if not -0.99 < material.poisson_ratio < 0.5:
        raise ValueError("case.material.poisson_ratio must be in (-0.99, 0.5)")

    section_raw = _mapping(case.get("section"), "section", required=True)
    section = SectionSpec(
        skin_thickness_m=_positive(section_raw, "skin_thickness_m", "section"),
        spar_thickness_m=_positive(section_raw, "spar_thickness_m", "section"),
        rib_thickness_m=_optional_section_thickness(section_raw, "rib_thickness_m"),
        root_doubler_thickness_m=_optional_section_thickness(
            section_raw, "root_doubler_thickness_m"
        ),
        hinge_reinforcement_thickness_m=_optional_section_thickness(
            section_raw, "hinge_reinforcement_thickness_m"
        ),
        cutout_reinforcement_thickness_m=_optional_section_thickness(
            section_raw, "cutout_reinforcement_thickness_m"
        ),
    )

    loads_raw = case.get("loads")
    if not isinstance(loads_raw, list) or not loads_raw:
        raise ValueError("case.loads must be a non-empty list")
    loads: list[LoadCaseSpec] = []
    seen: set[str] = set()
    for index, value in enumerate(loads_raw):
        item = _mapping(value, f"loads[{index}]", required=True)
        load_name = _string(item, "name", f"loads[{index}]")
        if load_name in seen:
            raise ValueError(f"case.loads contains duplicate name {load_name!r}")
        seen.add(load_name)
        distribution = _string(item, "distribution", f"loads[{index}]", default="elliptical")
        source = _string(item, "source", f"loads[{index}]", default="pressure")
        if source not in {"pressure", "openaerostruct"}:
            raise ValueError(f"case.loads[{index}].source must be 'pressure' or 'openaerostruct'")
        if distribution not in {"uniform", "elliptical", "openaerostruct"}:
            raise ValueError(
                f"case.loads[{index}].distribution must be uniform, elliptical, or openaerostruct"
            )
        pressure = None
        alpha = None
        aircraft_mass = None
        direction = _number(item, "direction", f"loads[{index}]", default=1.0)
        if direction not in {-1.0, 1.0}:
            raise ValueError(f"case.loads[{index}].direction must be -1 or 1")
        if source == "pressure":
            pressure = _number(item, "pressure_pa", f"loads[{index}]")
        else:
            if distribution != "openaerostruct":
                raise ValueError(
                    f"case.loads[{index}] with OpenAeroStruct source requires "
                    "distribution: openaerostruct"
                )
            alpha = _number(item, "alpha_deg", f"loads[{index}]")
            aircraft_mass = _positive(item, "aircraft_mass_kg", f"loads[{index}]")
        loads.append(
            LoadCaseSpec(
                name=load_name,
                pressure_pa=pressure,
                distribution=distribution,
                load_factor=_positive(item, "load_factor", f"loads[{index}]", default=1.0),
                source=source,
                alpha_deg=alpha,
                aircraft_mass_kg=aircraft_mass,
                direction=direction,
            )
        )

    solver_raw = _mapping(case.get("solver"), "solver")
    solver_name = _string(solver_raw, "name", "solver", default="calculix")
    if solver_name != "calculix":
        raise ValueError(
            f"case.solver.name must be 'calculix' (open-source policy), got {solver_name!r}"
        )
    solver = SolverSpec(
        solver=solver_name,
        executable=_string(solver_raw, "executable", "solver", default="ccx"),
    )

    verify_raw = _mapping(case.get("verification"), "verification")
    verification = VerificationSpec(
        minimum_safety_factor=_positive(
            verify_raw, "minimum_safety_factor", "verification", default=1.0
        ),
        maximum_displacement_m=_optional_positive(
            verify_raw, "maximum_displacement_m", "verification"
        ),
        maximum_mass_kg=_optional_positive(verify_raw, "maximum_mass_kg", "verification"),
    )

    mission = _mission(case)
    oas_validation = _oas_validation(case)
    has_oas_load = any(load.source == "openaerostruct" for load in loads)
    if has_oas_load and not oas_validation.enabled:
        raise ValueError("OpenAeroStruct loads require enabled openaerostruct_validation")
    if (oas_validation.enabled or has_oas_load) and mission is None:
        raise ValueError("OpenAeroStruct validation/loads require case.mission.authority_file")

    analyses = _analyses(case, {load.name for load in loads})
    governance = _mapping(case.get("governance"), "governance")
    authority = governance.get("structural_authority_file")
    evidence = governance.get("validation_evidence_file")
    for key, value in (
        ("structural_authority_file", authority),
        ("validation_evidence_file", evidence),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"case.governance.{key} must be a non-empty path string")

    return CaseSpec(
        name=name,
        geometry=_geometry(case),
        wingbox=wingbox,
        mesh=mesh,
        material=material,
        section=section,
        loads=tuple(loads),
        solver=solver,
        verification=verification,
        mission=mission,
        openaerostruct_validation=oas_validation,
        analyses=analyses,
        structural_authority_file=(
            _workspace_path(authority) if isinstance(authority, str) else None
        ),
        validation_evidence_file=_workspace_path(evidence) if isinstance(evidence, str) else None,
        source_path=source_path,
    )


def load_case_spec(config_path: str | Path) -> CaseSpec:
    path = Path(config_path).expanduser().resolve()
    return case_spec_from_mapping(load_yaml_config(path), source_path=path)
