"""
Service-layer orchestration for the bwb_segmented_v1 generator.

This module coordinates the deterministic geometry build pipeline from an
explicit design sample:

- planform generation
- section realization
- validation
- optional AeroSandbox conversion
- optional pyGeo loft, extraction, and CAD realization
- optional artifact export and plotting

It keeps orchestration separate from the generator contract, math modules,
and IO helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import (
    AeroSandboxGeometryResult,
    build_aerosandbox_geometry,
)
from aeris.generators.bwb_segmented_v1.export import (
    build_geometry_summary,
    export_backend_comparison_csv,
    export_control_points_csv,
    export_geometry_summary,
    export_planform_sections_csv,
    export_section_3d_csv,
)
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.planform import (
    PlanformResult,
    generate_bwb_planform_from_sample,
)
from aeris.generators.bwb_segmented_v1.plotting import save_planform_plot
from aeris.generators.bwb_segmented_v1.pygeo_backend import (
    PyGeoGeometryResult,
    build_pygeo_geometry,
    save_backend_comparison_plot,
)
from aeris.generators.bwb_segmented_v1.reconstruction_export import export_reconstruction_artifacts
from aeris.generators.bwb_segmented_v1.sections import (
    SectionGeometryResult,
    build_section_geometry_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (
    validate_planform_result,
    validate_section_geometry,
)
from aeris.generators.bwb_segmented_v1.validators import (
    audit_geometry_result,  # AERIS_PATCH_BATCH3_GEOMETRY_AUDIT_SUMMARY
)

_BACKEND_REFERENCE_FIELDS = (
    "span_m",
    "area_m2",
    "aspect_ratio",
    "mean_aerodynamic_chord_m",
    "volume_m3",
)


def compare_backend_reference_values(
    aerosandbox_values: dict[str, Any],
    pygeo_values: dict[str, Any],
) -> dict[str, Any]:
    """Build a numerical comparison without translating either geometry object."""

    metrics: dict[str, Any] = {}
    for name in _BACKEND_REFERENCE_FIELDS:
        asb_value = aerosandbox_values.get(name)
        pygeo_value = pygeo_values.get(name)
        if asb_value is None or pygeo_value is None:
            continue
        reference = float(asb_value)
        candidate = float(pygeo_value)
        delta = candidate - reference
        metrics[name] = {
            "aerosandbox": reference,
            "pygeo": candidate,
            "delta_pygeo_minus_aerosandbox": delta,
            "relative_delta": None if reference == 0.0 else delta / reference,
            "relative_delta_percent": (None if reference == 0.0 else 100.0 * delta / reference),
        }
    return {
        "reference_backend": "aerosandbox",
        "candidate_backend": "pygeo",
        "geometry_translation_used": False,
        "metrics": metrics,
    }


@dataclass(frozen=True)
class GeometryArtifactPaths:
    summary_path: Path
    control_points_path: Path
    planform_sections_path: Path
    section_3d_path: Path
    plot_path: Path | None
    pygeo_dir: Path | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "summary_path": str(self.summary_path),
            "control_points_path": str(self.control_points_path),
            "planform_sections_path": str(self.planform_sections_path),
            "section_3d_path": str(self.section_3d_path),
            "plot_path": None if self.plot_path is None else str(self.plot_path),
            "pygeo_dir": None if self.pygeo_dir is None else str(self.pygeo_dir),
        }


@dataclass(frozen=True)
class GeometryCaseResult:
    sample: BWBDesignSample
    planform: PlanformResult
    section_geometry: SectionGeometryResult
    aerosandbox_result: AeroSandboxGeometryResult | None
    pygeo_result: PyGeoGeometryResult | None
    artifact_paths: GeometryArtifactPaths
    summary: dict[str, Any]

    @property
    def airplane(self):
        if self.aerosandbox_result is None:
            return None
        return self.aerosandbox_result.airplane

    @property
    def wing(self):
        if self.aerosandbox_result is None:
            return None
        return self.aerosandbox_result.wing

    @property
    def pygeo_geometry(self):
        if self.pygeo_result is None:
            return None
        return self.pygeo_result.pygeo.geometry


def generate_geometry_case_from_sample(
    *,
    config: BWBGeneratorConfig,
    sample: BWBDesignSample,
    output_dir: Path,
    save_plot: bool | None = None,
    build_aerosandbox: bool | None = None,
) -> GeometryCaseResult:
    """
    Generate one deterministic geometry case from an explicit sampled design vector.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    effective_save_plot = config.outputs.save_plot if save_plot is None else save_plot
    effective_build_aerosandbox = (
        config.outputs.build_aerosandbox if build_aerosandbox is None else build_aerosandbox
    )

    planform = generate_bwb_planform_from_sample(sample, config)
    validate_planform_result(planform)

    section_geometry = build_section_geometry_from_sample(planform, sample, config)
    validate_section_geometry(section_geometry)

    # Override control surface geometry with sampled elevon DVs (v3+).
    # Guard on config.elevon_bounds is not None — this is the correct semantic:
    # v1/v2 configs have elevon_bounds=None and must NOT be patched with defaults,
    # even though BWBDesignSample always carries the elevon fields.
    # AERIS_PATCH_G4_APPLIED
    if config.control_surfaces.surfaces and config.elevon_bounds is not None:
        from dataclasses import replace as _dc_replace

        _overridden_surfaces = tuple(
            _dc_replace(
                surf,
                hinge_point=float(sample.elevon_hinge_frac),
                spanwise=_dc_replace(
                    surf.spanwise,
                    start_frac=float(sample.elevon_start_frac),
                    end_frac=float(sample.elevon_end_frac),
                ),
            )
            for surf in config.control_surfaces.surfaces
        )
        config = _dc_replace(
            config,
            control_surfaces=_dc_replace(config.control_surfaces, surfaces=_overridden_surfaces),
        )

    pygeo_result = None
    if config.pygeo.enabled:
        pygeo_result = build_pygeo_geometry(
            section_geometry=section_geometry,
            planform=planform,
            sample=sample,
            config=config,
            output_dir=output_dir / "pygeo",
        )

    aerosandbox_result = None
    if effective_build_aerosandbox:
        aerosandbox_result = build_aerosandbox_geometry(section_geometry, config)

    reconstruction_artifacts = None
    if aerosandbox_result is not None:
        reconstruction_artifacts = export_reconstruction_artifacts(
            airplane=aerosandbox_result.airplane,
            output_dir=output_dir,
        )

    summary_path = output_dir / "geometry_summary.json"
    control_points_path = output_dir / "control_points.csv"
    planform_sections_path = output_dir / "planform_sections.csv"
    section_3d_path = output_dir / "section_3d.csv"

    plot_path: Path | None = None
    if effective_save_plot:
        plots_dir = output_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        plot_path = plots_dir / "planform.png"

    # Write-only inspection CSVs — opt-in (geometry.outputs.save_detail_csv).
    if config.outputs.save_detail_csv:
        export_control_points_csv(planform, control_points_path)
        export_planform_sections_csv(planform, planform_sections_path)
        export_section_3d_csv(section_geometry, section_3d_path)

    if effective_save_plot and plot_path is not None:
        save_planform_plot(planform, section_geometry, config, plot_path)

    artifact_paths = GeometryArtifactPaths(
        summary_path=summary_path,
        control_points_path=control_points_path,
        planform_sections_path=planform_sections_path,
        section_3d_path=section_3d_path,
        plot_path=plot_path,
        pygeo_dir=None if pygeo_result is None else pygeo_result.output_dir,
    )

    summary = build_geometry_summary(
        config=config,
        planform=planform,
        section_geometry=section_geometry,
        aerosandbox_result=aerosandbox_result,
        artifact_paths=artifact_paths.to_dict(),
        sample=sample,
    )

    summary["realization_backends"] = {
        "aerosandbox": {
            "enabled": aerosandbox_result is not None,
            "role": "discrete wing realization and aerodynamic adapter",
        },
        "pygeo": {
            "enabled": pygeo_result is not None,
            "role": "master B-spline loft, section extraction, and CAD utilities",
        },
    }
    if pygeo_result is not None:
        pygeo_summary = pygeo_result.summary_dict()
        summary["pygeo"] = pygeo_summary
        summary["pygeo_reference_values"] = pygeo_result.reference_values
        if aerosandbox_result is not None:
            comparison = compare_backend_reference_values(
                aerosandbox_result.reference_values,
                pygeo_result.reference_values,
            )
            summary["backend_comparison"] = comparison
            comparison_csv = output_dir / "backend_comparison.csv"
            export_backend_comparison_csv(comparison, comparison_csv)
            summary["artifacts"]["backend_comparison_csv"] = str(comparison_csv)

            if config.pygeo.outputs.save_visualization:
                comparison_plot = output_dir / "plots" / "pygeo_vs_aerosandbox.png"
                save_backend_comparison_plot(
                    pygeo_result,
                    aerosandbox_result.wing,
                    comparison_plot,
                    comparison=comparison,
                    dpi=config.pygeo.outputs.visualization_dpi,
                )
                summary["artifacts"]["backend_comparison_plot"] = str(comparison_plot)
        summary["metrics"].update(
            {
                "aspect_ratio_pygeo": pygeo_result.metrics["aspect_ratio_xy"],
                "n_sections_pygeo_extracted": pygeo_result.metrics["n_extracted_sections"],
                "volume_pygeo_m3": pygeo_result.metrics["volume_m3"],
                "wetted_area_pygeo_m2": pygeo_result.metrics["wetted_area_m2"],
            }
        )
        summary["artifacts"]["pygeo"] = pygeo_result.artifacts
        summary["control_surface_summary"]["pygeo"] = pygeo_result.control.to_dict()
        if aerosandbox_result is None:
            summary["reference_values"] = pygeo_result.reference_values
            summary["geometry_info"] = {
                "backend": "pygeo",
                "geometry_id": pygeo_result.geometry_id,
                "n_authored_sections": len(pygeo_result.stations),
                "n_extracted_sections": len(pygeo_result.extracted),
                "symmetric": True,
            }
    else:
        summary["pygeo"] = {"enabled": False}

    if reconstruction_artifacts is not None:
        summary["reconstruction_artifacts"] = reconstruction_artifacts

    audit = audit_geometry_result(planform=planform, section_geometry=section_geometry)
    summary["geometry_audit"] = {
        "passed": bool(audit.passed),
        "errors": list(audit.errors),
        "warnings": list(audit.warnings),
        "metrics": audit.metrics,
    }

    export_geometry_summary(summary, summary_path)

    return GeometryCaseResult(
        sample=sample,
        planform=planform,
        section_geometry=section_geometry,
        aerosandbox_result=aerosandbox_result,
        pygeo_result=pygeo_result,
        artifact_paths=artifact_paths,
        summary=summary,
    )
