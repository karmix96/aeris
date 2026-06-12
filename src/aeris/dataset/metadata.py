"""
Dataset metadata schema and row builders.

This module defines the CSV column layout used for successful and failed dataset
cases and builds normalized row dictionaries from generator inputs and outputs.

Current implementation is geometry-result aware and assumes the active
generator exposes planform, section-geometry, optional AeroSandbox summary,
and artifact-path fields.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np


def metadata_fieldnames() -> list[str]:
    return [
        "geometry_id",
        "case_index",
        "dataset_name",
        "status",
        "sampler_id",
        "sampler_seed",
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
        "elevon_start_frac",
        "elevon_end_frac",
        "elevon_hinge_frac",
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
        "realization_seed",
        "realization_mode",
        "generator_family",
        "generator_version",
        "generator_id",
        "config_name",
        "error_type",
        "error_message",
    ]


def _sample_to_dict(sample: Any) -> dict[str, Any]:
    if hasattr(sample, "to_dict"):
        return dict(sample.to_dict())
    if is_dataclass(sample):
        return asdict(sample)
    if isinstance(sample, dict):
        return dict(sample)
    raise TypeError(f"Unsupported sample type for metadata: {type(sample)}")


def _require_nonempty_numeric_array(name: str, values: Any) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError(f"{name} must be non-empty for dataset metadata generation.")
    # ISSUE-16: guard against NaN/Inf propagating into twist/dihedral statistics
    if not np.isfinite(array).all():
        bad = array[~np.isfinite(array)]
        raise ValueError(
            f"{name} contains non-finite values: {bad.tolist()!r}. "
            "Check generator output for NaN/Inf in geometry arrays."
        )
    return array


def _validate_row_matches_fieldnames(row: dict[str, Any], fieldnames: list[str], *, context: str) -> None:
    row_keys = set(row.keys())
    expected_keys = set(fieldnames)

    extra = sorted(row_keys - expected_keys)
    missing = sorted(expected_keys - row_keys)

    if extra or missing:
        problems: list[str] = []
        if extra:
            problems.append(f"extra keys: {extra}")
        if missing:
            problems.append(f"missing keys: {missing}")
        # ISSUE-15: include generator/config context so post-hoc log triage is possible
        gen_id   = row.get("generator_id", "<unknown>") if isinstance(row, dict) else "<unknown>"
        cfg_name = row.get("config_name",  "<unknown>") if isinstance(row, dict) else "<unknown>"
        raise ValueError(
            f"{context} does not match schema: " + "; ".join(problems) +
            f" [generator_id={gen_id!r}, config_name={cfg_name!r}]"
        )


def build_metadata_row(
    *,
    dataset_name: str,
    geometry_id: str,
    case_index: int,
    sampler_id: str,
    sampler_seed: int | None,
    realization_seed: int | None,
    generator_id: str,
    config: Any,
    result: Any,
    geometry_dir: Path,
) -> dict[str, Any]:
    sample_dict = _sample_to_dict(result.sample)
    twists = _require_nonempty_numeric_array(
        "result.section_geometry.twist_array_deg",
        result.section_geometry.twist_array_deg,
    )
    dihedrals = _require_nonempty_numeric_array(
        "result.section_geometry.dihedral_array_deg",
        result.section_geometry.dihedral_array_deg,
    )

    row = {
        "geometry_id": geometry_id,
        "case_index": case_index,
        "dataset_name": dataset_name,
        "status": "success",
        "sampler_id": sampler_id,
        "sampler_seed": sampler_seed,
        "realization_seed": realization_seed,
        "realization_mode": "deterministic_from_sample",
        "generator_family": config.generator.family,
        "generator_version": config.generator.version,
        "generator_id": generator_id,
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

    _validate_row_matches_fieldnames(
        row,
        metadata_fieldnames(),
        context="Metadata row",
    )
    return row


def build_failure_row(
    *,
    dataset_name: str,
    geometry_id: str,
    case_index: int,
    sampler_id: str,
    sampler_seed: int | None,
    realization_seed: int | None,
    generator_id: str,
    config: Any,
    exc: Exception,
) -> dict[str, Any]:
    row = {
        "geometry_id": geometry_id,
        "case_index": case_index,
        "dataset_name": dataset_name,
        "sampler_id": sampler_id,
        "sampler_seed": sampler_seed,
        "realization_seed": realization_seed,
        "realization_mode": "deterministic_from_sample",
        "generator_family": config.generator.family,
        "generator_version": config.generator.version,
        "generator_id": generator_id,
        # META-1: include config context in failure rows for post-hoc triage
        "config_name": getattr(config, "name", None),
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }

    _validate_row_matches_fieldnames(
        row,
        failure_fieldnames(),
        context="Failure row",
    )
    return row