"""
Hard validation checks for bwb_segmented_v1 configuration and geometry outputs.

These checks enforce conditions that should fail execution, such as invalid
bounds, malformed arrays, non-finite values, non-positive chord lengths, and
inconsistent geometry dimensions.

Design notes
------------
* ``validate_bwb_generator_config`` — called once at pipeline start; catches
  bad YAML before any geometry work begins.
* ``validate_planform_controls`` — extracted from planform.py (2C.4) so there
  is a single source of truth.  planform.py imports and calls this function
  rather than duplicating the checks.
* ``validate_planform_result`` — called after planform generation; catches
  degenerate geometry (non-finite arrays, zero chords, broken span ordering).
* ``validate_section_geometry`` — called after section building; catches empty
  section lists and array-length mismatches (2C.5).

Sweep sign convention
---------------------
YAML stores sweep magnitudes as **positive** values (e.g. sw1_deg min=10,
max=40).  The sampler negates them at draw time so that BWBDesignSample
stores aft sweep as **negative** degrees internally.  Validation of the YAML
bounds uses ``_ensure_min_less_than_max`` on the positive magnitudes, which is
correct — it is NOT a bug that sw bounds are validated as positive ranges.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from aeris.generators.bwb_segmented_v1.params import BWBGeneratorConfig, RangeConfig

if TYPE_CHECKING:
    # Imported only for type annotations — not at runtime.
    # This breaks the circular import:
    #   planform.py imports validation.py (for validate_planform_controls)
    #   validation.py would import planform.py (for PlanformResult) — circular.
    # with TYPE_CHECKING=False at runtime, these imports never execute.
    from aeris.generators.bwb_segmented_v1.planform import PlanformResult
    from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_min_less_than_max(name: str, bounds: RangeConfig) -> None:
    if bounds.min >= bounds.max:
        raise ValueError(f"{name}.min must be < {name}.max")


# ---------------------------------------------------------------------------
# Config validators
# ---------------------------------------------------------------------------


def validate_planform_controls(config: BWBGeneratorConfig) -> None:
    """
    Validate the controls block of a BWBGeneratorConfig.

    This is the single source of truth for controls validation.
    planform.py imports and calls this rather than duplicating the checks.

    Raises
    ------
    ValueError
        If any controls parameter is out of range.
    """
    ctrl = config.controls

    if ctrl.n_points < 4:
        raise ValueError(f"geometry.controls.n_points must be >= 4, got {ctrl.n_points}")
    if ctrl.n_spline_inboard < 2:
        raise ValueError("geometry.controls.n_spline_inboard must be >= 2")
    if ctrl.n_spline_outboard < 2:
        raise ValueError("geometry.controls.n_spline_outboard must be >= 2")
    if not (0.0 < ctrl.spline_split_ratio < 1.0):
        raise ValueError(
            f"geometry.controls.spline_split_ratio must be in (0, 1), got {ctrl.spline_split_ratio}"
        )
    if ctrl.curvature_strength < 0.0:
        raise ValueError("geometry.controls.curvature_strength must be >= 0")
    if ctrl.segment_length_variation < 0.0:
        raise ValueError("geometry.controls.segment_length_variation must be >= 0")
    # AERIS_PATCH_BATCH2_SWEEP_VARIATION_UPPER_BOUND
    if not (0.0 <= ctrl.sweep_variation < 1.0):
        raise ValueError(
            f"geometry.controls.sweep_variation must be in [0, 1), got {ctrl.sweep_variation}"
        )


def validate_bwb_generator_config(config: BWBGeneratorConfig) -> None:
    """
    Full validation of a BWBGeneratorConfig before any geometry work begins.

    Raises
    ------
    ValueError
        On any invalid bound, inconsistent ratio, or missing required field.
    """
    if config.generator.family != "bwb_segmented":
        raise ValueError("geometry.generator.family must be 'bwb_segmented'")

    if not config.generator.version.strip():
        raise ValueError("geometry.generator.version must not be empty")

    validate_planform_controls(config)

    pb = config.planform_bounds
    sb = config.section_bounds

    # --- Planform bounds ---
    _ensure_min_less_than_max("geometry.planform_bounds.c1_m", pb.c1_m)
    _ensure_min_less_than_max("geometry.planform_bounds.c2_ratio", pb.c2_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.c3_ratio", pb.c3_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.c4_ratio", pb.c4_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.b_total_m", pb.b_total_m)
    _ensure_min_less_than_max("geometry.planform_bounds.b3_ratio", pb.b3_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.split_ratio", pb.split_ratio)

    # AERIS_PATCH_BATCH2_POSITIVE_PLANFORM_BOUNDS
    if pb.c1_m.min <= 0.0:
        raise ValueError("geometry.planform_bounds.c1_m.min must be > 0")
    if pb.b_total_m.min <= 0.0:
        raise ValueError("geometry.planform_bounds.b_total_m.min must be > 0")
    for _name, _bounds in [
        ("c2_ratio", pb.c2_ratio),
        ("c3_ratio", pb.c3_ratio),
        ("c4_ratio", pb.c4_ratio),
    ]:
        if not (0.0 < _bounds.min < _bounds.max <= 1.0):
            raise ValueError(
                f"geometry.planform_bounds.{_name} bounds must satisfy "
                f"0 < min < max <= 1.0, got min={_bounds.min}, max={_bounds.max}"
            )

    # Sweep bounds are positive magnitudes in YAML; sampler negates at draw time.
    # Validate that the magnitude range is sensible (min < max, both positive).
    _ensure_min_less_than_max("geometry.planform_bounds.sw1_deg", pb.sw1_deg)
    _ensure_min_less_than_max("geometry.planform_bounds.sw2_deg", pb.sw2_deg)
    _ensure_min_less_than_max("geometry.planform_bounds.sw3_deg", pb.sw3_deg)

    if pb.sw1_deg.min < 0.0:
        raise ValueError(
            "geometry.planform_bounds.sw1_deg.min must be >= 0 "
            "(YAML stores positive sweep magnitudes; sampler negates internally)"
        )
    if pb.sw2_deg.min < 0.0:
        raise ValueError(
            "geometry.planform_bounds.sw2_deg.min must be >= 0 "
            "(YAML stores positive sweep magnitudes; sampler negates internally)"
        )
    if pb.sw3_deg.min < 0.0:
        raise ValueError(
            "geometry.planform_bounds.sw3_deg.min must be >= 0 "
            "(YAML stores positive sweep magnitudes; sampler negates internally)"
        )

    if not (0.0 < pb.b3_ratio.min < 1.0 and 0.0 < pb.b3_ratio.max < 1.0):
        raise ValueError("geometry.planform_bounds.b3_ratio bounds must lie in (0, 1)")

    if not (0.0 < pb.split_ratio.min < 1.0 and 0.0 < pb.split_ratio.max < 1.0):
        raise ValueError("geometry.planform_bounds.split_ratio bounds must lie in (0, 1)")

    # --- Section bounds ---
    if not sb.airfoil_name.strip():
        raise ValueError("geometry.section_bounds.airfoil_name must not be empty")

    _ensure_min_less_than_max("geometry.section_bounds.twist_b0_deg", sb.twist_b0_deg)
    _ensure_min_less_than_max("geometry.section_bounds.twist_b1_deg", sb.twist_b1_deg)
    _ensure_min_less_than_max("geometry.section_bounds.twist_b2_deg", sb.twist_b2_deg)
    _ensure_min_less_than_max("geometry.section_bounds.twist_b3_deg", sb.twist_b3_deg)
    if config.pygeo.enabled and config.pygeo.enforce_flat_root_panel:
        if abs(sb.dihedral_root_deg) > 1.0e-12:
            raise ValueError(
                "pyGeo requires geometry.section_bounds.dihedral_root_deg = 0.0 "
                "so mirrored finite-thickness halves do not penetrate at the root"
            )
        if abs(sb.dihedral_b1_deg.min) > 1.0e-12 or abs(sb.dihedral_b1_deg.max) > 1.0e-12:
            raise ValueError(
                "pyGeo enforce_flat_root_panel requires "
                "geometry.section_bounds.dihedral_b1_deg min=max=0.0"
            )
    else:
        _ensure_min_less_than_max("geometry.section_bounds.dihedral_b1_deg", sb.dihedral_b1_deg)
    _ensure_min_less_than_max("geometry.section_bounds.dihedral_b2_deg", sb.dihedral_b2_deg)
    _ensure_min_less_than_max("geometry.section_bounds.dihedral_b3_deg", sb.dihedral_b3_deg)

    if config.pygeo.enabled and config.pygeo.physical_cad.enabled:
        if not config.control_surfaces.enabled or not config.control_surfaces.surfaces:
            raise ValueError(
                "geometry.pygeo.physical_cad.enabled requires an enabled "
                "geometry.control_surfaces definition"
            )
        if len(config.control_surfaces.surfaces) != 1:
            raise ValueError(
                "The frozen pyGeo split-control CAD implementation currently "
                "supports exactly one spanwise control-surface definition"
            )
        if not config.control_surfaces.surfaces[0].symmetric:
            raise ValueError(
                "The frozen pyGeo split-control CAD implementation requires "
                "a symmetric control-surface definition"
            )

    # --- Elevon bounds (v3+, optional) ---  AERIS_PATCH_G5_APPLIED
    eb = config.elevon_bounds
    if eb is not None:
        for fname, rc in [
            ("elevon_bounds.elevon_start_frac", eb.elevon_start_frac),
            ("elevon_bounds.elevon_end_frac", eb.elevon_end_frac),
            ("elevon_bounds.elevon_hinge_frac", eb.elevon_hinge_frac),
        ]:
            if not (0.0 <= rc.min <= 1.0 and 0.0 <= rc.max <= 1.0):
                raise ValueError(
                    f"geometry.{fname} bounds must lie in [0, 1], got min={rc.min}, max={rc.max}."
                )
            _ensure_min_less_than_max(f"geometry.{fname}", rc)
        if eb.elevon_start_frac.max >= eb.elevon_end_frac.min:
            raise ValueError(
                "geometry.elevon_bounds: elevon_start_frac.max must be < "
                "elevon_end_frac.min to guarantee start < end after sampling. "
                f"Got start_frac.max={eb.elevon_start_frac.max}, "
                f"end_frac.min={eb.elevon_end_frac.min}."
            )
        if not (0.0 < eb.elevon_hinge_frac.min and eb.elevon_hinge_frac.max < 1.0):
            raise ValueError(
                "geometry.elevon_bounds.elevon_hinge_frac bounds must satisfy "
                "0 < min and max < 1 (hinge point must be strictly inside the chord). "
                f"Got min={eb.elevon_hinge_frac.min}, max={eb.elevon_hinge_frac.max}."
            )


# ---------------------------------------------------------------------------
# Geometry output validators
# ---------------------------------------------------------------------------


def validate_planform_result(planform: PlanformResult) -> None:
    """
    Hard checks on a PlanformResult after generation.

    Raises ValueError on any condition that would cause downstream failures.
    """
    # --- Array size consistency ---
    if planform.x_le.size != planform.y_le.size:
        raise ValueError("x_le and y_le must have the same length")
    if planform.x_te.size != planform.y_te.size:
        raise ValueError("x_te and y_te must have the same length")

    # --- Non-finite values ---
    for name, arr in [
        ("x_le", planform.x_le),
        ("y_le", planform.y_le),
        ("x_te", planform.x_te),
        ("y_te", planform.y_te),
        ("front_x_fine", planform.front_x_fine),
        ("front_y_fine", planform.front_y_fine),
        ("rear_x_fine", planform.rear_x_fine),
        ("rear_y_fine", planform.rear_y_fine),
        ("chords", planform.chords),
    ]:
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"planform.{name} contains non-finite values")

    # --- Spanwise monotonicity of control points ---
    if planform.y_le.size > 1 and np.any(np.diff(planform.y_le) < 0):
        raise ValueError("planform.y_le is not monotonically nondecreasing")
    if planform.y_te.size > 1 and np.any(np.diff(planform.y_te) < 0):
        raise ValueError("planform.y_te is not monotonically nondecreasing")

    # --- Local chord positivity (fine grid) ---
    local_chords = planform.rear_x_fine - planform.front_x_fine
    if not np.all(local_chords > 0.0):
        raise ValueError(
            f"fine-section local chords must all be > 0 (min={float(np.min(local_chords)):.6e})"
        )

    # --- Fine array length consistency ---
    if planform.num_sections != planform.front_y_fine.size:
        raise ValueError("num_sections does not match front fine array length")
    if planform.num_sections != planform.rear_y_fine.size:
        raise ValueError("num_sections does not match rear fine array length")

    # --- Segment counts ---
    if min(planform.N1, planform.N2, planform.N3) < 1:
        raise ValueError("N1, N2, N3 must all be >= 1")
    if planform.N1 + planform.N2 + planform.N3 != planform.n_points - 1:
        raise ValueError("N1 + N2 + N3 must equal n_points - 1")

    # --- Group boundary array ---
    if planform.group_boundary_y.size != 4:
        raise ValueError("group_boundary_y must contain exactly 4 entries")
    if not np.all(np.isfinite(planform.group_boundary_y)):
        raise ValueError("group_boundary_y contains non-finite values")
    if not np.all(np.diff(planform.group_boundary_y) >= 0.0):
        raise ValueError("group_boundary_y must be monotonically nondecreasing")

    # --- Scalar summary values ---
    if not math.isfinite(planform.semi_span_m) or planform.semi_span_m <= 0.0:
        raise ValueError("semi_span_m must be finite and > 0")
    if not math.isfinite(planform.full_span_m) or planform.full_span_m <= 0.0:
        raise ValueError("full_span_m must be finite and > 0")
    if not math.isfinite(planform.approx_area_m2) or planform.approx_area_m2 <= 0.0:
        raise ValueError("approx_area_m2 must be finite and > 0")
    if not math.isfinite(planform.approx_aspect_ratio) or planform.approx_aspect_ratio <= 0.0:
        raise ValueError("approx_aspect_ratio must be finite and > 0")


def validate_section_geometry(section_geometry: SectionGeometryResult) -> None:
    """
    Hard checks on a SectionGeometryResult after generation.

    Raises ValueError on empty sections or array-length mismatches.

    2C.5 — array-length check added: twist_array_deg and dihedral_array_deg
    must match len(sections).  This is implicitly guaranteed by _cumulative_z
    after the D21 fix, but we enforce it explicitly so any future refactor
    that breaks the invariant fails loudly here rather than silently producing
    wrong z-values downstream.
    """
    if len(section_geometry.sections) == 0:
        raise ValueError("no section records — section_geometry.sections is empty")

    n = len(section_geometry.sections)

    if section_geometry.twist_array_deg.size != n:
        raise ValueError(
            f"twist_array_deg length ({section_geometry.twist_array_deg.size}) "
            f"does not match section count ({n})"
        )

    if section_geometry.dihedral_array_deg.size != n:
        raise ValueError(
            f"dihedral_array_deg length ({section_geometry.dihedral_array_deg.size}) "
            f"does not match section count ({n})"
        )

    if not np.all(np.isfinite(section_geometry.twist_array_deg)):
        raise ValueError("twist_array_deg contains non-finite values")

    if not np.all(np.isfinite(section_geometry.dihedral_array_deg)):
        raise ValueError("dihedral_array_deg contains non-finite values")

    # Spanwise positions must be strictly increasing
    y_vals = np.array([s.y_m for s in section_geometry.sections], dtype=float)
    if y_vals.size > 1 and not np.all(np.diff(y_vals) > 0.0):
        raise ValueError("section y_m positions are not strictly increasing")

    # All section chords must be positive
    chords = np.array([s.chord_m for s in section_geometry.sections], dtype=float)
    if not np.all(chords > 0.0):
        raise ValueError(f"section chord_m must all be > 0 (min={float(np.min(chords)):.6e})")
