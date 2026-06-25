"""
3-D section geometry builder for bwb_segmented_v1.

Builds spanwise section records from a deterministic planform result and a
sampled set of twist/dihedral boundary values.

Dihedral convention (D21 — fixed)
----------------------------------
Each section's vertical (z) position is computed by **cumulative integration**
of the spanwise-varying dihedral angle:

    z(y_i) = z(y_{i-1}) + 0.5 * (tan(d_{i-1}) + tan(d_i)) * (y_i - y_{i-1})

This is the trapezoidal approximation of  ∫₀ʸ tan(d(y')) dy', which is the
geometrically correct formula for a surface whose tangent angle varies along
the span.

The previous formula  z = y * tan(d_local)  is only correct when dihedral is
**uniform** (same angle at every station).  For non-uniform dihedral it places
sections on independent rays from the origin rather than on a continuous
surface, producing z errors that grow quadratically with span and dihedral
variation.  For a small UAV at 5° tip dihedral over a 1.6 m semi-span the
error at the tip was ~45 mm — visible and AVL-significant.

Manufacturability
-----------------
Dihedral is interpolated with ``np.interp`` (piecewise **linear**) between the
four control-point values (b0–b3).  This produces flat ruled panels between
adjacent rib stations — no spanwise curvature, no "waves".  CubicSpline
interpolation is deliberately NOT used here for exactly this reason.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    BWBGeneratorConfig,
    SectionBoundsConfig,
)
from aeris.generators.bwb_segmented_v1.planform import PlanformResult


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

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
    airfoil_id: str | None = None  # library airfoil ID for polar bridge (None = no bridge)


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

    def __post_init__(self) -> None:
        # 2B.5 — freeze all numpy arrays stored in the frozen dataclass
        for field_name in self.__dataclass_fields__:
            arr = getattr(self, field_name)
            if isinstance(arr, np.ndarray):
                arr.flags.writeable = False


# ---------------------------------------------------------------------------
# Polar bridge helper
# ---------------------------------------------------------------------------

def _make_airfoil_id_resolver(sb: SectionBoundsConfig, semispan_m: float = 1.0):
    """Return a callable y_m → airfoil_id for the polar bridge, or None."""
    if sb.segment_airfoils:
        segs = sorted(sb.segment_airfoils, key=lambda s: s.y_frac_end)
        # Convert fractional boundaries to absolute y [m]
        y_boundaries = [s.y_frac_end * semispan_m for s in segs]
        ids = [s.airfoil_id for s in segs]
        return lambda y_m: _segment_lookup_abs(y_m, ids, y_boundaries)
    if sb.airfoil_library_id:
        _aid = sb.airfoil_library_id
        return lambda _y: _aid
    return None


def _segment_lookup_abs(y_m: float, ids: list, y_boundaries: list) -> str:
    """Return airfoil_id for the segment whose absolute y_end ≥ y_m."""
    for aid, y_end in zip(ids, y_boundaries):
        if y_m <= y_end + 1e-6:
            return aid
    return ids[-1]


# ---------------------------------------------------------------------------
# z-position helper (D21 fix)
# ---------------------------------------------------------------------------

def _cumulative_z(y_m: np.ndarray, dihedral_deg: np.ndarray) -> np.ndarray:
    """
    Compute section LE z-coordinates by cumulative trapezoidal integration.

    z(y_i) = z(y_{i-1}) + 0.5*(tan(d_{i-1}) + tan(d_i))*(y_i - y_{i-1})

    Parameters
    ----------
    y_m : ndarray, shape (N,)
        Spanwise positions, strictly increasing, starting at 0.
    dihedral_deg : ndarray, shape (N,)
        Local dihedral angle at each spanwise station [degrees].

    Returns
    -------
    z : ndarray, shape (N,)
        Vertical LE position at each station [m].  z[0] is always 0.0.
    """
    tan_d = np.tan(np.radians(dihedral_deg))
    z = np.zeros(len(y_m), dtype=float)
    for i in range(1, len(y_m)):
        dy = y_m[i] - y_m[i - 1]
        z[i] = z[i - 1] + 0.5 * (tan_d[i - 1] + tan_d[i]) * dy
    return z


# ---------------------------------------------------------------------------
# Main section builder
# ---------------------------------------------------------------------------

def _resolve_station_airfoil(y_m: float, group_boundary_y, station_airfoils) -> str:
    """Step-function airfoil resolver: each section gets the airfoil
    from its inboard group boundary (AVL/panel-method convention)."""
    y_b1 = float(group_boundary_y[1])
    y_b2 = float(group_boundary_y[2])
    y_b3 = float(group_boundary_y[3])
    eps = 1e-9
    if y_m >= y_b3 - eps: return station_airfoils.b3
    if y_m >= y_b2 - eps: return station_airfoils.b2
    if y_m >= y_b1 - eps: return station_airfoils.b1
    return station_airfoils.b0


def build_section_geometry_from_sample(
    planform: PlanformResult,
    sample: BWBDesignSample,
    config: BWBGeneratorConfig,
) -> SectionGeometryResult:
    """
    Build the full 3-D section geometry from a planform and a design sample.

    Parameters
    ----------
    planform : PlanformResult
        Output of ``generate_bwb_planform_from_sample``.
    sample : BWBDesignSample
        Sampled design vector containing twist and dihedral boundary values.
    config : BWBGeneratorConfig
        Generator configuration, used for ``section_bounds.airfoil_name``
        and the fixed root dihedral.

    Returns
    -------
    SectionGeometryResult
        Contains one ``SectionRecord`` per fine spanwise station, plus the
        boundary arrays and interpolated twist/dihedral distributions.

    Raises
    ------
    ValueError
        If ``planform.front_y_fine`` and ``planform.group_boundary_y`` are
        inconsistent (would silently produce wrong interpolation otherwise).
    """
    sb = config.section_bounds

    # 2B.10 — validate key array lengths before doing any work
    if len(planform.front_y_fine) == 0:
        raise ValueError("planform.front_y_fine is empty — cannot build sections")
    if len(planform.group_boundary_y) != 4:
        raise ValueError(
            f"planform.group_boundary_y must have 4 entries, "
            f"got {len(planform.group_boundary_y)}"
        )
    if planform.front_y_fine[0] < planform.group_boundary_y[0]:
        raise ValueError(
            "planform.front_y_fine starts before group_boundary_y[0] — "
            "extrapolation in np.interp would silently clamp values"
        )

    # --- Boundary values ---
    twist_b0_deg = sample.twist_b0_deg
    twist_b1_deg = sample.twist_b1_deg
    twist_b2_deg = sample.twist_b2_deg
    twist_b3_deg = sample.twist_b3_deg

    dihedral_b0_deg = float(sb.dihedral_root_deg)   # always fixed at root
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

    # --- Spanwise interpolation (piecewise linear — flat panels, no waves) ---
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

    # --- z-positions via cumulative integration (D21 fix) ---
    z_array_m = _cumulative_z(planform.front_y_fine, dihedral_array_deg)

    # --- Build section records ---
    airfoil_name = sb.airfoil_name
    # Pre-compute airfoil_id lookup for the polar bridge (optional)
    semispan_m = float(planform.front_y_fine[-1]) if len(planform.front_y_fine) > 0 else 1.0
    _bridge_id_resolver = _make_airfoil_id_resolver(sb, semispan_m=semispan_m)
    sections: list[SectionRecord] = []
    for i in range(planform.num_sections):
        y_m_i = float(planform.front_y_fine[i])
        sections.append(
            SectionRecord(
                index=i,
                x_le_m=float(planform.front_x_fine[i]),
                y_m=y_m_i,
                z_le_m=float(z_array_m[i]),
                chord_m=float(planform.rear_x_fine[i] - planform.front_x_fine[i]),
                twist_deg=float(twist_array_deg[i]),
                dihedral_deg=float(dihedral_array_deg[i]),
                airfoil_name=airfoil_name,
                airfoil_id=_bridge_id_resolver(y_m_i) if _bridge_id_resolver else None,
            )
        )

    return SectionGeometryResult(
        sections=sections,
        twist_b0_deg=twist_b0_deg,
        twist_b1_deg=twist_b1_deg,
        twist_b2_deg=twist_b2_deg,
        twist_b3_deg=twist_b3_deg,
        dihedral_b0_deg=dihedral_b0_deg,
        dihedral_b1_deg=dihedral_b1_deg,
        dihedral_b2_deg=dihedral_b2_deg,
        dihedral_b3_deg=dihedral_b3_deg,
        twist_boundaries_deg=twist_boundaries_deg,
        dihedral_boundaries_deg=dihedral_boundaries_deg,
        twist_array_deg=twist_array_deg,
        dihedral_array_deg=dihedral_array_deg,
        group_boundary_y=planform.group_boundary_y,
    )