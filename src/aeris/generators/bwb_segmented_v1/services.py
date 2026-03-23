"""
Service-layer orchestration for the bwb_segmented_v1 generator.

This module coordinates the deterministic geometry build pipeline from an
explicit design sample:

- planform generation
- section realization
- validation
- optional AeroSandbox conversion
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
    export_control_points_csv,
    export_geometry_summary,
    export_planform_sections_csv,
    export_section_3d_csv,
)
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.planform import PlanformResult, generate_bwb_planform_from_sample
from aeris.generators.bwb_segmented_v1.plotting import save_planform_plot
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult, build_section_geometry_from_sample
from aeris.generators.bwb_segmented_v1.validation import validate_planform_result, validate_section_geometry
from aeris.generators.bwb_segmented_v1.reconstruction_export import export_reconstruction_artifacts


@dataclass(frozen=True)
class GeometryArtifactPaths:
    summary_path: Path
    control_points_path: Path
    planform_sections_path: Path
    section_3d_path: Path
    plot_path: Path | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "summary_path": str(self.summary_path),
            "control_points_path": str(self.control_points_path),
            "planform_sections_path": str(self.planform_sections_path),
            "section_3d_path": str(self.section_3d_path),
            "plot_path": None if self.plot_path is None else str(self.plot_path),
        }


@dataclass(frozen=True)
class GeometryCaseResult:
    sample: BWBDesignSample
    planform: PlanformResult
    section_geometry: SectionGeometryResult
    aerosandbox_result: AeroSandboxGeometryResult | None
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
    )

    summary = build_geometry_summary(
        config=config,
        planform=planform,
        section_geometry=section_geometry,
        aerosandbox_result=aerosandbox_result,
        artifact_paths=artifact_paths.to_dict(),
    )

    if reconstruction_artifacts is not None:
        summary["reconstruction_artifacts"] = reconstruction_artifacts

    export_geometry_summary(summary, summary_path)

    return GeometryCaseResult(
        sample=sample,
        planform=planform,
        section_geometry=section_geometry,
        aerosandbox_result=aerosandbox_result,
        artifact_paths=artifact_paths,
        summary=summary,
    )