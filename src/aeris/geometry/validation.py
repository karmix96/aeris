from __future__ import annotations

import math

import numpy as np

from aeris.geometry.params import BWBGeneratorConfig, RangeConfig
from aeris.geometry.planform import PlanformResult
from aeris.geometry.sections import SectionGeometryResult


def _ensure_min_less_than_max(name: str, bounds: RangeConfig) -> None:
    if bounds.min >= bounds.max:
        raise ValueError(f"{name}.min must be < {name}.max")


def validate_bwb_generator_config(config: BWBGeneratorConfig) -> None:
    if config.generator.family != "bwb_segmented":
        raise ValueError("geometry.generator.family must be 'bwb_segmented'")

    if not config.generator.version.strip():
        raise ValueError("geometry.generator.version must not be empty")

    ctrl = config.controls
    pb = config.planform_bounds
    sb = config.section_bounds

    if ctrl.n_points < 4:
        raise ValueError("geometry.controls.n_points must be >= 4")

    if ctrl.n_spline_inboard < 2:
        raise ValueError("geometry.controls.n_spline_inboard must be >= 2")

    if ctrl.n_spline_outboard < 2:
        raise ValueError("geometry.controls.n_spline_outboard must be >= 2")

    if not (0.0 < ctrl.spline_split_ratio < 1.0):
        raise ValueError("geometry.controls.spline_split_ratio must be in the range (0, 1)")

    if ctrl.curvature_strength < 0.0:
        raise ValueError("geometry.controls.curvature_strength must be >= 0")

    if ctrl.segment_length_variation < 0.0:
        raise ValueError("geometry.controls.segment_length_variation must be >= 0")

    if ctrl.sweep_variation < 0.0:
        raise ValueError("geometry.controls.sweep_variation must be >= 0")

    _ensure_min_less_than_max("geometry.planform_bounds.c1_m", pb.c1_m)
    _ensure_min_less_than_max("geometry.planform_bounds.c2_ratio", pb.c2_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.c3_ratio", pb.c3_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.c4_ratio", pb.c4_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.b_total_m", pb.b_total_m)
    _ensure_min_less_than_max("geometry.planform_bounds.b3_ratio", pb.b3_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.split_ratio", pb.split_ratio)
    _ensure_min_less_than_max("geometry.planform_bounds.sw1_deg", pb.sw1_deg)
    _ensure_min_less_than_max("geometry.planform_bounds.sw2_deg", pb.sw2_deg)
    _ensure_min_less_than_max("geometry.planform_bounds.sw3_deg", pb.sw3_deg)

    if not (0.0 < pb.b3_ratio.min < 1.0 and 0.0 < pb.b3_ratio.max < 1.0):
        raise ValueError("geometry.planform_bounds.b3_ratio bounds must lie in (0, 1)")

    if not (0.0 < pb.split_ratio.min < 1.0 and 0.0 < pb.split_ratio.max < 1.0):
        raise ValueError("geometry.planform_bounds.split_ratio bounds must lie in (0, 1)")

    if not sb.airfoil_name.strip():
        raise ValueError("geometry.section_bounds.airfoil_name must not be empty")

    _ensure_min_less_than_max("geometry.section_bounds.twist_b0_deg", sb.twist_b0_deg)
    _ensure_min_less_than_max("geometry.section_bounds.twist_b1_deg", sb.twist_b1_deg)
    _ensure_min_less_than_max("geometry.section_bounds.twist_b2_deg", sb.twist_b2_deg)
    _ensure_min_less_than_max("geometry.section_bounds.twist_b3_deg", sb.twist_b3_deg)
    _ensure_min_less_than_max("geometry.section_bounds.dihedral_b1_deg", sb.dihedral_b1_deg)
    _ensure_min_less_than_max("geometry.section_bounds.dihedral_b2_deg", sb.dihedral_b2_deg)
    _ensure_min_less_than_max("geometry.section_bounds.dihedral_b3_deg", sb.dihedral_b3_deg)


def validate_planform_result(planform: PlanformResult) -> None:
    if planform.x_le.size != planform.y_le.size:
        raise ValueError("x_le and y_le must have the same length")

    if planform.x_te.size != planform.y_te.size:
        raise ValueError("x_te and y_te must have the same length")

    if planform.x_le.size != planform.chords.size:
        raise ValueError("control-point chord array length mismatch")

    if planform.front_x_fine.size != planform.front_y_fine.size:
        raise ValueError("front fine arrays length mismatch")

    if planform.rear_x_fine.size != planform.rear_y_fine.size:
        raise ValueError("rear fine arrays length mismatch")

    if planform.front_x_mirrored.size != planform.front_y_mirrored.size:
        raise ValueError("mirrored front arrays length mismatch")

    if planform.rear_x_mirrored.size != planform.rear_y_mirrored.size:
        raise ValueError("mirrored rear arrays length mismatch")

    if not np.all(np.isfinite(planform.x_le)):
        raise ValueError("x_le contains non-finite values")

    if not np.all(np.isfinite(planform.y_le)):
        raise ValueError("y_le contains non-finite values")

    if not np.all(np.isfinite(planform.x_te)):
        raise ValueError("x_te contains non-finite values")

    if not np.all(np.isfinite(planform.y_te)):
        raise ValueError("y_te contains non-finite values")

    if not np.all(np.isfinite(planform.front_x_fine)):
        raise ValueError("front_x_fine contains non-finite values")

    if not np.all(np.isfinite(planform.front_y_fine)):
        raise ValueError("front_y_fine contains non-finite values")

    if not np.all(np.isfinite(planform.rear_x_fine)):
        raise ValueError("rear_x_fine contains non-finite values")

    if not np.all(np.isfinite(planform.rear_y_fine)):
        raise ValueError("rear_y_fine contains non-finite values")

    if not np.all(np.diff(planform.y_le) >= 0.0):
        raise ValueError("y_le must be monotonically nondecreasing")

    if not np.all(np.diff(planform.front_y_fine) >= -1e-12):
        raise ValueError("front_y_fine must be monotonically nondecreasing")

    if not np.all(np.diff(planform.rear_y_fine) >= -1e-12):
        raise ValueError("rear_y_fine must be monotonically nondecreasing")

    local_chords = planform.rear_x_fine - planform.front_x_fine
    if not np.all(local_chords > 0.0):
        raise ValueError("fine-section local chords must all be > 0")

    if planform.num_sections != planform.front_y_fine.size:
        raise ValueError("num_sections does not match front fine array length")

    if planform.num_sections != planform.rear_y_fine.size:
        raise ValueError("num_sections does not match rear fine array length")

    if min(planform.N1, planform.N2, planform.N3) < 1:
        raise ValueError("N1, N2, N3 must all be >= 1")

    if planform.N1 + planform.N2 + planform.N3 != planform.n_points - 1:
        raise ValueError("N1 + N2 + N3 must equal n_points - 1")

    if planform.group_boundary_y.size != 4:
        raise ValueError("group_boundary_y must contain exactly 4 entries")

    if not np.all(np.isfinite(planform.group_boundary_y)):
        raise ValueError("group_boundary_y contains non-finite values")

    if not np.all(np.diff(planform.group_boundary_y) >= 0.0):
        raise ValueError("group_boundary_y must be monotonically nondecreasing")

    if not math.isfinite(planform.semi_span_m) or planform.semi_span_m <= 0.0:
        raise ValueError("semi_span_m must be finite and > 0")

    if not math.isfinite(planform.full_span_m) or planform.full_span_m <= 0.0:
        raise ValueError("full_span_m must be finite and > 0")

    if not math.isfinite(planform.approx_area_m2) or planform.approx_area_m2 <= 0.0:
        raise ValueError("approx_area_m2 must be finite and > 0")

    if not math.isfinite(planform.approx_aspect_ratio) or planform.approx_aspect_ratio <= 0.0:
        raise ValueError("approx_aspect_ratio must be finite and > 0")


def validate_section_geometry(section_geometry: SectionGeometryResult) -> None:
    if len(section_geometry.sections) == 0:
        raise ValueError("no section records were generated")

    if section_geometry.twist_boundaries_deg.size != 4:
        raise ValueError("twist_boundaries_deg must have length 4")

    if section_geometry.dihedral_boundaries_deg.size != 4:
        raise ValueError("dihedral_boundaries_deg must have length 4")

    if section_geometry.group_boundary_y.size != 4:
        raise ValueError("group_boundary_y must have length 4")

    if section_geometry.twist_array_deg.size != len(section_geometry.sections):
        raise ValueError("twist array length mismatch")

    if section_geometry.dihedral_array_deg.size != len(section_geometry.sections):
        raise ValueError("dihedral array length mismatch")

    if not np.all(np.isfinite(section_geometry.twist_boundaries_deg)):
        raise ValueError("twist_boundaries_deg contains non-finite values")

    if not np.all(np.isfinite(section_geometry.dihedral_boundaries_deg)):
        raise ValueError("dihedral_boundaries_deg contains non-finite values")

    if not np.all(np.isfinite(section_geometry.twist_array_deg)):
        raise ValueError("twist_array_deg contains non-finite values")

    if not np.all(np.isfinite(section_geometry.dihedral_array_deg)):
        raise ValueError("dihedral_array_deg contains non-finite values")

    for record in section_geometry.sections:
        if record.chord_m <= 0.0:
            raise ValueError("all section chords must be > 0")

        if not math.isfinite(record.x_le_m):
            raise ValueError("section x_le_m must be finite")

        if not math.isfinite(record.y_m):
            raise ValueError("section y_m must be finite")

        if not math.isfinite(record.z_le_m):
            raise ValueError("section z_le_m must be finite")

        if not math.isfinite(record.twist_deg):
            raise ValueError("section twist_deg must be finite")

        if not math.isfinite(record.dihedral_deg):
            raise ValueError("section dihedral_deg must be finite")

        if not record.airfoil_name.strip():
            raise ValueError("section airfoil_name must not be empty")