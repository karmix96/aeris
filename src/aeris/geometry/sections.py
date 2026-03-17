from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aeris.geometry.params import BWBDesignSample, BWBGeneratorConfig
from aeris.geometry.planform import PlanformResult


@dataclass(frozen=True)
class SectionRecord:
    index: int
    x_le_m: float
    y_m: float
    z_le_m: float
    chord_m: float
    twist_deg: float
    dihedral_deg: float
    airfoil_name: str


@dataclass(frozen=True)
class SectionGeometryResult:
    sections: list[SectionRecord]

    twist_b0_deg: float
    twist_b1_deg: float
    twist_b2_deg: float
    twist_b3_deg: float

    dihedral_b0_deg: float
    dihedral_b1_deg: float
    dihedral_b2_deg: float
    dihedral_b3_deg: float

    twist_boundaries_deg: np.ndarray
    dihedral_boundaries_deg: np.ndarray

    twist_array_deg: np.ndarray
    dihedral_array_deg: np.ndarray

    group_boundary_y: np.ndarray


def build_section_geometry_from_sample(
    planform: PlanformResult,
    sample: BWBDesignSample,
    config: BWBGeneratorConfig,
) -> SectionGeometryResult:
    sb = config.section_bounds

    twist_b0_deg = sample.twist_b0_deg
    twist_b1_deg = sample.twist_b1_deg
    twist_b2_deg = sample.twist_b2_deg
    twist_b3_deg = sample.twist_b3_deg

    dihedral_b0_deg = float(sb.dihedral_root_deg)
    dihedral_b1_deg = sample.dihedral_b1_deg
    dihedral_b2_deg = sample.dihedral_b2_deg
    dihedral_b3_deg = sample.dihedral_b3_deg

    twist_boundaries_deg = np.array(
        [twist_b0_deg, twist_b1_deg, twist_b2_deg, twist_b3_deg],
        dtype=float,
    )
    dihedral_boundaries_deg = np.array(
        [dihedral_b0_deg, dihedral_b1_deg, dihedral_b2_deg, dihedral_b3_deg],
        dtype=float,
    )

    twist_array_deg = np.interp(
        planform.front_y_fine,
        planform.group_boundary_y,
        twist_boundaries_deg,
    )
    dihedral_array_deg = np.interp(
        planform.front_y_fine,
        planform.group_boundary_y,
        dihedral_boundaries_deg,
    )

    sections: list[SectionRecord] = []
    for i in range(planform.num_sections):
        x_le_m = float(planform.front_x_fine[i])
        y_m = float(planform.front_y_fine[i])
        chord_m = float(planform.rear_x_fine[i] - planform.front_x_fine[i])

        dihedral_deg = float(dihedral_array_deg[i])
        z_le_m = float(y_m * np.tan(np.radians(dihedral_deg)))

        sections.append(
            SectionRecord(
                index=i,
                x_le_m=x_le_m,
                y_m=y_m,
                z_le_m=z_le_m,
                chord_m=chord_m,
                twist_deg=float(twist_array_deg[i]),
                dihedral_deg=dihedral_deg,
                airfoil_name=sb.airfoil_name,
            )
        )

    return SectionGeometryResult(
        sections=sections,
        twist_b0_deg=float(twist_b0_deg),
        twist_b1_deg=float(twist_b1_deg),
        twist_b2_deg=float(twist_b2_deg),
        twist_b3_deg=float(twist_b3_deg),
        dihedral_b0_deg=float(dihedral_b0_deg),
        dihedral_b1_deg=float(dihedral_b1_deg),
        dihedral_b2_deg=float(dihedral_b2_deg),
        dihedral_b3_deg=float(dihedral_b3_deg),
        twist_boundaries_deg=twist_boundaries_deg,
        dihedral_boundaries_deg=dihedral_boundaries_deg,
        twist_array_deg=np.asarray(twist_array_deg, dtype=float),
        dihedral_array_deg=np.asarray(dihedral_array_deg, dtype=float),
        group_boundary_y=planform.group_boundary_y.copy(),
    )

