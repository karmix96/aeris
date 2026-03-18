from __future__ import annotations

from dataclasses import dataclass

import aerosandbox as asb

from aeris.generators.bwb_segmented_v1.params import BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult


@dataclass(frozen=True)
class AeroSandboxGeometryResult:
    aspect_ratio: float
    airfoil_name: str
    n_xsecs: int
    wing: asb.Wing
    airplane: asb.Airplane


def build_aerosandbox_geometry(
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
) -> AeroSandboxGeometryResult:
    airfoil_name = config.section_bounds.airfoil_name
    airfoil = asb.Airfoil(airfoil_name)

    wing_xsecs = [
        asb.WingXSec(
            xyz_le=[section.x_le_m, section.y_m, section.z_le_m],
            chord=section.chord_m,
            twist=section.twist_deg,
            airfoil=airfoil,
        )
        for section in section_geometry.sections
    ]

    wing = asb.Wing(
        name="BWB",
        symmetric=True,
        xsecs=wing_xsecs,
    )

    airplane = asb.Airplane(
        name=config.name,
        xyz_ref=[0.0, 0.0, 0.0],
        wings=[wing],
    )

    aspect_ratio = float(wing.aspect_ratio())

    return AeroSandboxGeometryResult(
        aspect_ratio=aspect_ratio,
        airfoil_name=airfoil_name,
        n_xsecs=len(wing_xsecs),
        wing=wing,
        airplane=airplane,
    )