from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from aeris.generators.bwb_segmented_v1.case import GeometryCaseResult
from aeris.generators.bwb_segmented_v1.params import BWBGeneratorConfig


def metadata_fieldnames() -> list[str]:
    return [
        "geometry_id",
        "case_index",
        "dataset_name",
        "status",
        "sampler_id",
        "sampler_seed",
        "lhs_seed",
        "realization_seed",
        "realization_mode",
        "generator_family",
        "generator_version",
        "generator_id",
        "config_name",
        "airfoil_name",
        "c1_m",
        "c2_ratio",
        "c3_ratio",
        "c4_ratio",
        "b_total_m",
        "b3_ratio",
        "split_ratio",
        "sw1_deg",
        "sw2_deg",
        "sw3_deg",
        "twist_b0_deg",
        "twist_b1_deg",
        "twist_b2_deg",
        "twist_b3_deg",
        "dihedral_b1_deg",
        "dihedral_b2_deg",
        "dihedral_b3_deg",
        "semi_span_m",
        "full_span_m",
        "approx_area_m2",
        "approx_aspect_ratio_planform",
        "aspect_ratio_aerosandbox",
        "num_sections",
        "n_xsecs_aerosandbox",
        "twist_min_deg",
        "twist_max_deg",
        "twist_mean_deg",
        "dihedral_min_deg",
        "dihedral_max_deg",
        "dihedral_mean_deg",
        "geometry_dir",
        "summary_path",
        "control_points_path",
        "planform_sections_path",
        "section_3d_path",
        "plot_path",
    ]


def failure_fieldnames() -> list[str]:
    return [
        "geometry_id",
        "case_index",
        "dataset_name",
        "sampler_id",
        "sampler_seed",
        "lhs_seed",
        "realization_seed",
        "realization_mode",
        "generator_family",
        "generator_version",
        "generator_id",
        "error_type",
        "error_message",
    ]


def build_metadata_row(
    *,
    dataset_name: str,
    geometry_id: str,
    case_index: int,
    sampler_id: str,
    sampler_seed: int | None,
    lhs_seed: int | None,
    realization_seed: int | None,
    config: BWBGeneratorConfig,
    result: GeometryCaseResult,
    geometry_dir: Path,
) -> dict[str, Any]:
    sample_dict = asdict(result.sample)
    twists = np.asarray(result.section_geometry.twist_array_deg, dtype=float)
    dihedrals = np.asarray(result.section_geometry.dihedral_array_deg, dtype=float)

    return {
        "geometry_id": geometry_id,
        "case_index": case_index,
        "dataset_name": dataset_name,
        "status": "success",
        "sampler_id": sampler_id,
        "sampler_seed": sampler_seed,
        "lhs_seed": lhs_seed,
        "realization_seed": realization_seed,
        "realization_mode": "deterministic_from_sample",
        "generator_family": config.generator.family,
        "generator_version": config.generator.version,
        "generator_id": f"{config.generator.family}_{config.generator.version}",
        "config_name": config.name,
        "airfoil_name": config.section_bounds.airfoil_name,
        **sample_dict,
        "semi_span_m": result.planform.semi_span_m,
        "full_span_m": result.planform.full_span_m,
        "approx_area_m2": result.planform.approx_area_m2,
        "approx_aspect_ratio_planform": result.planform.approx_aspect_ratio,
        "aspect_ratio_aerosandbox": (
            None if result.aerosandbox_result is None else result.aerosandbox_result.aspect_ratio
        ),
        "num_sections": result.planform.num_sections,
        "n_xsecs_aerosandbox": (
            None if result.aerosandbox_result is None else result.aerosandbox_result.n_xsecs
        ),
        "twist_min_deg": float(np.min(twists)),
        "twist_max_deg": float(np.max(twists)),
        "twist_mean_deg": float(np.mean(twists)),
        "dihedral_min_deg": float(np.min(dihedrals)),
        "dihedral_max_deg": float(np.max(dihedrals)),
        "dihedral_mean_deg": float(np.mean(dihedrals)),
        "geometry_dir": str(geometry_dir),
        "summary_path": str(result.artifact_paths.summary_path),
        "control_points_path": str(result.artifact_paths.control_points_path),
        "planform_sections_path": str(result.artifact_paths.planform_sections_path),
        "section_3d_path": str(result.artifact_paths.section_3d_path),
        "plot_path": (
            None if result.artifact_paths.plot_path is None else str(result.artifact_paths.plot_path)
        ),
    }


def build_failure_row(
    *,
    dataset_name: str,
    geometry_id: str,
    case_index: int,
    sampler_id: str,
    sampler_seed: int | None,
    lhs_seed: int | None,
    realization_seed: int | None,
    config: BWBGeneratorConfig,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "geometry_id": geometry_id,
        "case_index": case_index,
        "dataset_name": dataset_name,
        "sampler_id": sampler_id,
        "sampler_seed": sampler_seed,
        "lhs_seed": lhs_seed,
        "realization_seed": realization_seed,
        "realization_mode": "deterministic_from_sample",
        "generator_family": config.generator.family,
        "generator_version": config.generator.version,
        "generator_id": f"{config.generator.family}_{config.generator.version}",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
