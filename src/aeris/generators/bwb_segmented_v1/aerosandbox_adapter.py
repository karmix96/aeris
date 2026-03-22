from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aerosandbox as asb

from aeris.generators.bwb_segmented_v1.params import BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult




@dataclass(frozen=True)
class AeroSandboxGeometryResult:
    aspect_ratio: float
    airfoil_name: str
    n_xsecs: int
    reference_values: dict[str, float]
    mean_angles_deg: dict[str, float]
    aerodynamic_center: dict[str, float]
    sectional_metrics: dict[str, list[float] | list[list[float]]]
    geometry_info: dict[str, Any]
    wing: asb.Wing
    airplane: asb.Airplane


def _xyz_dict(vec) -> dict[str, float]:
    return {
        "x_m": float(vec[0]),
        "y_m": float(vec[1]),
        "z_m": float(vec[2]),
    }


def extract_wing_metadata(wing: asb.Wing) -> dict[str, Any]:
    ac = wing.aerodynamic_center(chord_fraction=0.25)
    sectional_acs = wing.aerodynamic_center(chord_fraction=0.25, _sectional=True)

    return {
        "reference_values": {
            "span_m": float(wing.span()),
            "area_m2": float(wing.area()),
            "aspect_ratio": float(wing.aspect_ratio()),
            "mean_geometric_chord_m": float(wing.mean_geometric_chord()),
            "mean_aerodynamic_chord_m": float(wing.mean_aerodynamic_chord()),
            "taper_ratio": float(wing.taper_ratio()),
            "volume_m3": float(wing.volume()),
        },
        "mean_angles_deg": {
            "twist_deg": float(wing.mean_twist_angle()),
            "sweep_le_deg": float(wing.mean_sweep_angle(x_nondim=0.0)),
            "sweep_c4_deg": float(wing.mean_sweep_angle(x_nondim=0.25)),
            "sweep_te_deg": float(wing.mean_sweep_angle(x_nondim=1.0)),
            "dihedral_c4_deg": float(wing.mean_dihedral_angle(x_nondim=0.25)),
        },
        "aerodynamic_center": _xyz_dict(ac),
        "sectional_metrics": {
            "section_spans_m": [float(v) for v in wing.span(type="yz", _sectional=True)],
            "section_areas_m2": [float(v) for v in wing.area(type="planform", _sectional=True)],
            "section_ac_xyz_m": [
                [float(v[0]), float(v[1]), float(v[2])] for v in sectional_acs
            ],
        },
        "geometry_info": {
        "wing_name": wing.name,
        "n_xsecs": len(wing.xsecs),
        "symmetric": bool(wing.symmetric),
        }
    }


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

    wing_meta = extract_wing_metadata(wing)

    return AeroSandboxGeometryResult(
        aspect_ratio=float(wing.aspect_ratio()),
        airfoil_name=airfoil_name,
        n_xsecs=len(wing_xsecs),
        reference_values=wing_meta["reference_values"],
        mean_angles_deg=wing_meta["mean_angles_deg"],
        aerodynamic_center=wing_meta["aerodynamic_center"],
        sectional_metrics=wing_meta["sectional_metrics"],
        geometry_info=wing_meta["geometry_info"],
        wing=wing,
        airplane=airplane,
    )