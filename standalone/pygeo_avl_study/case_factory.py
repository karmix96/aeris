"""Read-only construction of production and intended Paper-1 BWB cases."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import (
    AeroSandboxGeometryResult,
    build_aerosandbox_geometry,
)
from aeris.generators.bwb_segmented_v1.generator import BwbSegmentedV1Generator
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.planform import (
    PlanformResult,
    generate_bwb_planform_from_sample,
)
from aeris.generators.bwb_segmented_v1.sections import (
    SectionGeometryResult,
    build_section_geometry_from_sample,
)

from standalone.pygeo_avl_study.geometry_bridge import (
    StationDefinition,
    stations_from_records,
)


@dataclass
class StudyCase:
    config_path: Path
    raw_config: dict[str, Any]
    config: BWBGeneratorConfig
    sample: BWBDesignSample
    planform: PlanformResult
    production_sections: SectionGeometryResult
    intended_sections: SectionGeometryResult
    production_asb: AeroSandboxGeometryResult
    intended_asb: AeroSandboxGeometryResult
    pygeo_stations: list[StationDefinition]
    prescribed_airfoil_names: tuple[str, str, str, str]
    production_unique_airfoils: tuple[str, ...]
    prescribed_airfoils_applied_in_production: bool


def _prescribed_name_at_y(
    y_m: float,
    boundaries: np.ndarray,
    names: tuple[str, str, str, str],
) -> str:
    eps = 1.0e-9
    if y_m >= float(boundaries[3]) - eps:
        return names[3]
    if y_m >= float(boundaries[2]) - eps:
        return names[2]
    if y_m >= float(boundaries[1]) - eps:
        return names[1]
    return names[0]


def apply_prescribed_station_airfoils(
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
) -> SectionGeometryResult:
    """Apply the four configured station airfoils in the standalone case only."""
    spec = config.section_bounds.station_airfoils
    if spec is None:
        return section_geometry
    names = (spec.b0, spec.b1, spec.b2, spec.b3)
    boundaries = np.asarray(section_geometry.group_boundary_y, dtype=float)
    records = [
        replace(
            record,
            airfoil_name=_prescribed_name_at_y(record.y_m, boundaries, names),
        )
        for record in section_geometry.sections
    ]
    return replace(section_geometry, sections=records)


def build_study_case(
    config_path: Path,
    *,
    airfoil_database: Path,
    seed: int | None = None,
) -> StudyCase:
    """Build both the repository's actual case and the configured intent."""
    config_path = Path(config_path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    generator = BwbSegmentedV1Generator()
    config = generator.build_config(raw)
    sample = generator.sample_one(config, seed=seed)
    planform = generate_bwb_planform_from_sample(sample, config)
    production_sections = build_section_geometry_from_sample(planform, sample, config)
    intended_sections = apply_prescribed_station_airfoils(production_sections, config)
    production_asb = build_aerosandbox_geometry(production_sections, config)
    intended_asb = build_aerosandbox_geometry(intended_sections, config)
    stations = stations_from_records(intended_sections.sections, airfoil_database)

    spec = config.section_bounds.station_airfoils
    prescribed = (
        (spec.b0, spec.b1, spec.b2, spec.b3)
        if spec is not None
        else (config.section_bounds.airfoil_name,) * 4
    )
    production_unique = tuple(
        sorted({record.airfoil_name for record in production_sections.sections})
    )
    intended_unique = {
        record.airfoil_name for record in intended_sections.sections
    }
    return StudyCase(
        config_path=config_path,
        raw_config=raw,
        config=config,
        sample=sample,
        planform=planform,
        production_sections=production_sections,
        intended_sections=intended_sections,
        production_asb=production_asb,
        intended_asb=intended_asb,
        pygeo_stations=stations,
        prescribed_airfoil_names=prescribed,
        production_unique_airfoils=production_unique,
        prescribed_airfoils_applied_in_production=(
            intended_unique == set(production_unique)
            and all(
                a.airfoil_name == b.airfoil_name
                for a, b in zip(
                    production_sections.sections,
                    intended_sections.sections,
                )
            )
        ),
    )
