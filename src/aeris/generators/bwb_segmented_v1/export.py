"""
Artifact export helpers for bwb_segmented_v1 geometry cases.

Writes structured JSON and CSV outputs describing:
- control points
- discretized planform sections
- 3D section geometry
- overall geometry summary
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import AeroSandboxGeometryResult
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig  # AERIS_PATCH_G1_APPLIED
from aeris.generators.bwb_segmented_v1.planform import PlanformResult
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult


def _write_json(output_path: Path, payload: dict[str, Any]) -> None:  # AERIS_PATCH_G6_APPLIED
    """Atomic JSON write: temp-file + os.replace avoids corrupt output on crash."""
    import os
    import tempfile
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent, prefix=f".{output_path.name}.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _write_csv(output_path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_geometry_summary(
    config: BWBGeneratorConfig,
    planform: PlanformResult,
    section_geometry: SectionGeometryResult,
    aerosandbox_result: AeroSandboxGeometryResult | None,
    artifact_paths: dict[str, str],
    *,
    sample: BWBDesignSample | None = None,
) -> dict[str, Any]:
    generator_info = {
        "family": config.generator.family,
        "version": config.generator.version,
        "seed": config.generator.seed,
    }

    controls_info = {
        "n_points": config.controls.n_points,
        "n_spline_inboard": config.controls.n_spline_inboard,
        "n_spline_outboard": config.controls.n_spline_outboard,
        "curvature_strength": config.controls.curvature_strength,
        "spline_split_ratio": config.controls.spline_split_ratio,
        "segment_length_variation": config.controls.segment_length_variation,
        "sweep_variation": config.controls.sweep_variation,
    }

    sampled_planform = {
        "c1_m": planform.c1,
        "c2_ratio": planform.c2_ratio,
        "c3_ratio": planform.c3_ratio,
        "c4_ratio": planform.c4_ratio,
        "c2_m": planform.c2,
        "c3_m": planform.c3,
        "c4_m": planform.c4,
        "b_total_m": planform.b_total,
        "b3_ratio": planform.b3_ratio,
        "b1_m": planform.b1,
        "b2_m": planform.b2,
        "b3_m": planform.b3,
        "split_ratio": planform.split_ratio,
        "sw1_deg": planform.sw1_deg,
        "sw2_deg": planform.sw2_deg,
        "sw3_deg": planform.sw3_deg,
        "elevon_start_frac": getattr(sample, "elevon_start_frac", 0.60) if sample is not None else 0.60,
        "elevon_end_frac": getattr(sample, "elevon_end_frac",   0.95) if sample is not None else 0.95,
        "elevon_hinge_frac": getattr(sample, "elevon_hinge_frac", 0.75) if sample is not None else 0.75,
    }

    discretization = {
        "N1": planform.N1,
        "N2": planform.N2,
        "N3": planform.N3,
        "split_idx": planform.split_idx,
        "num_sections": planform.num_sections,
    }

    sampled_sections = {
        "airfoil_name": config.section_bounds.airfoil_name,
        "twist_b0_deg": section_geometry.twist_b0_deg,
        "twist_b1_deg": section_geometry.twist_b1_deg,
        "twist_b2_deg": section_geometry.twist_b2_deg,
        "twist_b3_deg": section_geometry.twist_b3_deg,
        "dihedral_b0_deg": section_geometry.dihedral_b0_deg,
        "dihedral_b1_deg": section_geometry.dihedral_b1_deg,
        "dihedral_b2_deg": section_geometry.dihedral_b2_deg,
        "dihedral_b3_deg": section_geometry.dihedral_b3_deg,
        "twist_boundaries_deg": None
        if section_geometry.twist_boundaries_deg is None
        else section_geometry.twist_boundaries_deg.tolist(),
        "dihedral_boundaries_deg": None
        if section_geometry.dihedral_boundaries_deg is None
        else section_geometry.dihedral_boundaries_deg.tolist(),
        "group_boundary_y_m": None
        if section_geometry.group_boundary_y is None
        else section_geometry.group_boundary_y.tolist(),
    }

    metrics = {
        "semi_span_m": planform.semi_span_m,
        "full_span_m": planform.full_span_m,
        "approx_area_m2": planform.approx_area_m2,
        "approx_aspect_ratio_planform": planform.approx_aspect_ratio,
        "aspect_ratio_aerosandbox": None if aerosandbox_result is None else aerosandbox_result.aspect_ratio,
        "n_xsecs_aerosandbox": None if aerosandbox_result is None else aerosandbox_result.n_xsecs,
    }

    reference_values = None if aerosandbox_result is None else aerosandbox_result.reference_values
    mean_angles_deg = None if aerosandbox_result is None else aerosandbox_result.mean_angles_deg
    aerodynamic_center = None if aerosandbox_result is None else aerosandbox_result.aerodynamic_center
    sectional_metrics = None if aerosandbox_result is None else aerosandbox_result.sectional_metrics
    geometry_info = None if aerosandbox_result is None else aerosandbox_result.geometry_info
    asb_metadata = {} if aerosandbox_result is None else dict(aerosandbox_result.metadata)

    configured_control_surfaces = {
        "enabled": config.control_surfaces.enabled,
        "count": len(config.control_surfaces.surfaces),
        "names": [surface.name for surface in config.control_surfaces.surfaces],
        "definitions": [
            {
                "name": surface.name,
                "family": surface.family,
                "hinge_point": surface.hinge_point,
                "symmetric": surface.symmetric,
                "side": surface.side,
                "start_frac": surface.spanwise.start_frac,
                "end_frac": surface.spanwise.end_frac,
                "deflection_sign": surface.deflection_sign,
                "required": surface.required,
            }
            for surface in config.control_surfaces.surfaces
        ],
    }

    control_surface_summary = {
        "configured": configured_control_surfaces,
        "applied": {
            "has_control_surfaces": bool(asb_metadata.get("has_control_surfaces", False)),
            "control_surface_count": int(asb_metadata.get("control_surface_count", 0)),
            "applied_control_surfaces": asb_metadata.get("applied_control_surfaces", []),
        },
    }

    return {  # AERIS_PATCH_G7_APPLIED
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "name": config.name,
        "generator": generator_info,
        "controls": controls_info,
        "config": config.to_dict(),
        "sampled_planform": sampled_planform,
        "sampled_sections": sampled_sections,
        "discretization": discretization,
        "metrics": metrics,
        "reference_values": reference_values,
        "mean_angles_deg": mean_angles_deg,
        "aerodynamic_center": aerodynamic_center,
        "sectional_metrics": sectional_metrics,
        "artifacts": artifact_paths,
        "geometry_info": geometry_info,
        "control_surface_summary": control_surface_summary,
        "reference_conventions": {
            "geometry_axes_origin": "aircraft geometry origin used to define section xyz_le coordinates",
            "moment_reference_point_xyz_m": [0.0, 0.0, 0.0],
            "x_axis_positive_direction": "aft",
            "reference_area_definition": "wing planform area from AeroSandbox wing.area()",
            "reference_span_definition": "wing span from AeroSandbox wing.span()",
            "reference_chord_definition": "mean aerodynamic chord from AeroSandbox wing.mean_aerodynamic_chord()",
        },
    }


def export_control_points_csv(planform: PlanformResult, output_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for i in range(planform.n_points):
        rows.append(
            {
                "index": i,
                "x_le_m": float(planform.x_le[i]),
                "y_le_m": float(planform.y_le[i]),
                "x_te_m": float(planform.x_te[i]),
                "y_te_m": float(planform.y_te[i]),
                "chord_m": float(planform.chords[i]),
            }
        )

    _write_csv(
        output_path,
        rows,
        fieldnames=["index", "x_le_m", "y_le_m", "x_te_m", "y_te_m", "chord_m"],
    )


def export_planform_sections_csv(planform: PlanformResult, output_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for i in range(planform.num_sections):
        rows.append(
            {
                "index": i,
                "front_x_m": float(planform.front_x_fine[i]),
                "front_y_m": float(planform.front_y_fine[i]),
                "rear_x_m": float(planform.rear_x_fine[i]),
                "rear_y_m": float(planform.rear_y_fine[i]),
                "chord_m": float(planform.rear_x_fine[i] - planform.front_x_fine[i]),
            }
        )

    _write_csv(
        output_path,
        rows,
        fieldnames=["index", "front_x_m", "front_y_m", "rear_x_m", "rear_y_m", "chord_m"],
    )


def export_section_3d_csv(section_geometry: SectionGeometryResult, output_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for section in section_geometry.sections:
        rows.append(
            {
                "index": section.index,
                "x_le_m": section.x_le_m,
                "y_m": section.y_m,
                "z_le_m": section.z_le_m,
                "chord_m": section.chord_m,
                "twist_deg": section.twist_deg,
                "dihedral_deg": section.dihedral_deg,
                "airfoil_name": section.airfoil_name,
            }
        )

    _write_csv(
        output_path,
        rows,
        fieldnames=[
            "index",
            "x_le_m",
            "y_m",
            "z_le_m",
            "chord_m",
            "twist_deg",
            "dihedral_deg",
            "airfoil_name",
        ],
    )


def export_geometry_summary(summary: dict[str, Any], output_path: Path) -> None:
    _write_json(output_path, summary)