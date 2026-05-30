"""
AeroSandbox conversion adapter for bwb_segmented_v1 geometry.

Transforms section-level geometry into AeroSandbox Wing and Airplane objects
and extracts derived wing metadata for downstream reporting and analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aerosandbox as asb
import numpy as np

from aeris.generators.bwb_segmented_v1.params import (
    BWBGeneratorConfig,
    ControlSurfaceConfig,
)
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult


@dataclass(frozen=True)
class AppliedControlSurfaceRecord:
    name: str
    family: str
    hinge_point: float
    symmetric: bool
    side: str | None
    start_frac: float
    end_frac: float
    applied_xsec_indices: tuple[int, ...]


@dataclass(frozen=True)
class AeroSandboxGeometryResult:
    aspect_ratio: float
    airfoil_name: str
    n_xsecs: int
    reference_values: dict[str, Any]
    mean_angles_deg: dict[str, Any]
    aerodynamic_center: dict[str, Any]
    sectional_metrics: dict[str, Any]
    geometry_info: dict[str, Any]
    wing: asb.Wing
    airplane: asb.Airplane
    metadata: dict[str, Any]


def _xyz_dict(vec: Any) -> dict[str, float]:
    return {
        "x_m": float(vec[0]),
        "y_m": float(vec[1]),
        "z_m": float(vec[2]),
    }


def _normalized_semispan_fractions(y_stations: np.ndarray) -> np.ndarray:
    if len(y_stations) == 0:
        raise ValueError("Cannot compute span fractions for empty y_stations.")

    y_abs = np.abs(np.asarray(y_stations, dtype=float))
    y_max = float(np.max(y_abs))

    if y_max <= 0.0:
        return np.zeros_like(y_abs)

    return y_abs / y_max


def _control_surface_to_asb(spec: ControlSurfaceConfig) -> asb.ControlSurface:
    if spec.family != "trailing_edge":
        raise ValueError(
            f"Unsupported control surface family {spec.family!r}. "
            "Only 'trailing_edge' is supported in v1."
        )

    return asb.ControlSurface(
        name=spec.name,
        trailing_edge=True,
        hinge_point=spec.hinge_point,
        deflection=0.0,
        symmetric=spec.symmetric,
    )


def _xsec_is_in_control_region(
    frac: float,
    *,
    start_frac: float,
    end_frac: float,
    is_last_xsec: bool,
) -> bool:
    # Do not attach control to the final tip xsec.
    if is_last_xsec:
        return False
    return start_frac <= frac <= end_frac


def _build_control_surface_assignment(
    *,
    y_stations: np.ndarray,
    config: BWBGeneratorConfig,
) -> tuple[dict[int, list[asb.ControlSurface]], list[AppliedControlSurfaceRecord]]:
    assignments: dict[int, list[asb.ControlSurface]] = {}
    records: list[AppliedControlSurfaceRecord] = []

    control_cfg = config.control_surfaces
    if not control_cfg.enabled or len(control_cfg.surfaces) == 0:
        return assignments, records

    span_fracs = _normalized_semispan_fractions(y_stations)
    n = len(y_stations)

    for spec in control_cfg.surfaces:
        applied_indices: list[int] = []

        for i, frac in enumerate(span_fracs):
            if _xsec_is_in_control_region(
                float(frac),
                start_frac=spec.spanwise.start_frac,
                end_frac=spec.spanwise.end_frac,
                is_last_xsec=(i == n - 1),
            ):
                assignments.setdefault(i, []).append(_control_surface_to_asb(spec))
                applied_indices.append(i)

        records.append(
            AppliedControlSurfaceRecord(
                name=spec.name,
                family=spec.family,
                hinge_point=spec.hinge_point,
                symmetric=spec.symmetric,
                side=spec.side,
                start_frac=spec.spanwise.start_frac,
                end_frac=spec.spanwise.end_frac,
                applied_xsec_indices=tuple(applied_indices),
            )
        )

    return assignments, records


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
        },
    }


def build_aerosandbox_geometry(
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
) -> AeroSandboxGeometryResult:
    airfoil_name = config.section_bounds.airfoil_name

    y_stations = np.asarray([section.y_m for section in section_geometry.sections], dtype=float)
    control_assignments, control_records = _build_control_surface_assignment(
        y_stations=y_stations,
        config=config,
    )

    wing_xsecs: list[asb.WingXSec] = []
    for i, section in enumerate(section_geometry.sections):
        airfoil = asb.Airfoil(section.airfoil_name or airfoil_name)
        control_surfaces_here = list(control_assignments.get(i, []))

        wing_xsecs.append(
            asb.WingXSec(
                xyz_le=[section.x_le_m, section.y_m, section.z_le_m],
                chord=section.chord_m,
                twist=section.twist_deg,
                airfoil=airfoil,
                control_surfaces=control_surfaces_here,
            )
        )

    wing = asb.Wing(
        name="BWB",
        symmetric=True,
        xsecs=wing_xsecs,
    )

    # 2D.2 — Explicit reference values are required for AVL normalization.
    # AeroSandbox computes s_ref/c_ref/b_ref lazily when not provided, which
    # works for geometry inspection but causes silent incorrect CL/CD/Cm
    # normalization in AVL runs. Always bake them in from the wing object.
    airplane = asb.Airplane(
        name=config.name,
        xyz_ref=[0.0, 0.0, 0.0],
        wings=[wing],
        s_ref=float(wing.area()),
        c_ref=float(wing.mean_aerodynamic_chord()),
        b_ref=float(wing.span()),
    )

    wing_meta = extract_wing_metadata(wing)

    metadata = {
        "has_control_surfaces": any(len(v) > 0 for v in control_assignments.values()),
        "control_surface_count": len(config.control_surfaces.surfaces)
        if config.control_surfaces.enabled
        else 0,
        "applied_control_surfaces": [
            {
                "name": r.name,
                "family": r.family,
                "hinge_point": r.hinge_point,
                "symmetric": r.symmetric,
                "side": r.side,
                "start_frac": r.start_frac,
                "end_frac": r.end_frac,
                "applied_xsec_indices": list(r.applied_xsec_indices),
            }
            for r in control_records
        ],
    }

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
        metadata=metadata,
    )