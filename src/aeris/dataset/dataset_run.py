from __future__ import annotations

import platform
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aeris.common.config import load_yaml_config
from aeris.common.logging_utils import setup_logger
from aeris.dataset.io import (
    append_csv_row,
    ensure_csv_with_header,
    ensure_dataset_paths,
    write_json,
)
from aeris.dataset.lhs import generate_lhs_samples
from aeris.dataset.metadata import (
    build_failure_row,
    build_metadata_row,
    failure_fieldnames,
    metadata_fieldnames,
)
from aeris.geometry.case import generate_geometry_case_from_sample
from aeris.geometry.params import BWBGeneratorConfig, build_bwb_generator_config
from aeris.geometry.validation import validate_bwb_generator_config


def _utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _default_dataset_name(
    config_path: Path,
    config: BWBGeneratorConfig,
    n_samples: int,
    lhs_seed: int | None,
) -> str:
    """Build a reproducible default dataset name."""
    lhs_part = "none" if lhs_seed is None else str(lhs_seed)
    return (
        f"{config_path.stem}_"
        f"{config.generator.family}_{config.generator.version}_"
        f"n{n_samples}_lhs{lhs_part}"
    )


def _make_effective_dataset_config(
    config: BWBGeneratorConfig,
    *,
    save_plot: bool | None = None,
    build_aerosandbox: bool | None = None,
) -> BWBGeneratorConfig:
    """
    Return the effective dataset config.

    Important:
    - We only override output switches here.
    - We do NOT silently zero geometry-shaping controls.
      If the generator is deterministic from sample, those controls are part
      of the actual geometry definition and should remain intact unless the
      user explicitly changes them in config.
    """
    outputs = config.outputs

    if save_plot is not None or build_aerosandbox is not None:
        from dataclasses import replace

        outputs = replace(
            config.outputs,
            save_plot=config.outputs.save_plot if save_plot is None else save_plot,
            build_aerosandbox=(
                config.outputs.build_aerosandbox
                if build_aerosandbox is None
                else build_aerosandbox
            ),
        )

    if outputs is config.outputs:
        return config

    from dataclasses import replace

    return replace(config, outputs=outputs)


def run_dataset_generation(
    *,
    config_path: str | Path,
    n_samples: int,
    lhs_seed: int | None,
    dataset_name: str | None = None,
    save_plot: bool | None = None,
    build_aerosandbox: bool | None = None,
) -> int:
    """
    Generate a geometry dataset using LHS over the explicit design variables.

    Architecture rule:
    - LHS seed controls only the design-space sampling.
    - Each sampled design is then realized deterministically into geometry.
    """
    resolved_config_path = Path(config_path).expanduser().resolve()

    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")

    raw_config = load_yaml_config(resolved_config_path)
    base_config = build_bwb_generator_config(raw_config)
    validate_bwb_generator_config(base_config)

    effective_config = _make_effective_dataset_config(
        base_config,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
    )

    effective_dataset_name = dataset_name or _default_dataset_name(
        resolved_config_path,
        effective_config,
        n_samples,
        lhs_seed,
    )

    dataset_paths = ensure_dataset_paths(effective_dataset_name)
    logger = setup_logger(
        dataset_paths.logs_dir / "dataset.log",
        logger_name=f"aeris.dataset.{effective_dataset_name}",
    )

    shutil.copy2(resolved_config_path, dataset_paths.input_config_path)
    write_json(dataset_paths.resolved_config_json_path, effective_config.to_dict())

    ensure_csv_with_header(dataset_paths.metadata_csv_path, metadata_fieldnames())
    ensure_csv_with_header(dataset_paths.failures_csv_path, failure_fieldnames())

    manifest: dict[str, Any] = {
        "dataset_name": effective_dataset_name,
        "status": "running",
        "config_path": str(resolved_config_path),
        "copied_config_path": str(dataset_paths.input_config_path),
        "resolved_config_json_path": str(dataset_paths.resolved_config_json_path),
        "dataset_root": str(dataset_paths.root),
        "geometry_dir": str(dataset_paths.geometry_dir),
        "logs_dir": str(dataset_paths.logs_dir),
        "metadata_csv_path": str(dataset_paths.metadata_csv_path),
        "failures_csv_path": str(dataset_paths.failures_csv_path),
        "platform": platform.system().lower(),
        "python_version": sys.version.split()[0],
        "created_at_utc": _utc_now_iso(),
        "completed_at_utc": None,
        "requested_n": n_samples,
        "attempted_n": 0,
        "succeeded_n": 0,
        "failed_n": 0,
        "lhs_seed": lhs_seed,
        "geometry_deterministic": True,
        "generator_family": effective_config.generator.family,
        "generator_version": effective_config.generator.version,
        "generator_id": (
            f"{effective_config.generator.family}_{effective_config.generator.version}"
        ),
        "outputs": {
            "save_plot": effective_config.outputs.save_plot,
            "build_aerosandbox": effective_config.outputs.build_aerosandbox,
        },
        "controls": {
            "n_points": effective_config.controls.n_points,
            "n_spline_inboard": effective_config.controls.n_spline_inboard,
            "n_spline_outboard": effective_config.controls.n_spline_outboard,
            "segment_length_variation": effective_config.controls.segment_length_variation,
            "sweep_variation": effective_config.controls.sweep_variation,
        },
        "error": None,
    }
    write_json(dataset_paths.manifest_path, manifest)

    try:
        logger.info("Starting dataset generation")
        logger.info("Config path: %s", resolved_config_path)
        logger.info("Dataset root: %s", dataset_paths.root)
        logger.info("Requested samples: %d", n_samples)
        logger.info(
            "Generator: family=%s version=%s",
            effective_config.generator.family,
            effective_config.generator.version,
        )
        logger.info("LHS seed: %s", lhs_seed)
        logger.info("Geometry realization mode: deterministic from explicit design sample")

        samples = generate_lhs_samples(
            config=effective_config,
            n_samples=n_samples,
            lhs_seed=lhs_seed,
        )
        logger.info("Generated %d LHS design samples", len(samples))

        for case_index, sample in enumerate(samples, start=1):
            geometry_id = f"geom_{case_index:05d}"
            case_geometry_dir = dataset_paths.geometry_dir / geometry_id

            manifest["attempted_n"] = case_index
            write_json(dataset_paths.manifest_path, manifest)

            try:
                logger.info("Generating %s", geometry_id)

                result = generate_geometry_case_from_sample(
                    config=effective_config,
                    sample=sample,
                    output_dir=case_geometry_dir,
                    save_plot=effective_config.outputs.save_plot,
                    build_aerosandbox=effective_config.outputs.build_aerosandbox,
                )

                row = build_metadata_row(
                    dataset_name=effective_dataset_name,
                    geometry_id=geometry_id,
                    case_index=case_index,
                    lhs_seed=lhs_seed,
                    realization_seed=None,
                    config=effective_config,
                    result=result,
                    geometry_dir=case_geometry_dir,
                )
                append_csv_row(
                    dataset_paths.metadata_csv_path,
                    row,
                    metadata_fieldnames(),
                )

                manifest["succeeded_n"] += 1
                logger.info(
                    "Success %s | span=%.6f area=%.6f AR_planform=%.6f",
                    geometry_id,
                    result.planform.full_span_m,
                    result.planform.approx_area_m2,
                    result.planform.approx_aspect_ratio,
                )

            except Exception as exc:
                failure_row = build_failure_row(
                    dataset_name=effective_dataset_name,
                    geometry_id=geometry_id,
                    case_index=case_index,
                    lhs_seed=lhs_seed,
                    realization_seed=None,
                    config=effective_config,
                    exc=exc,
                )
                append_csv_row(
                    dataset_paths.failures_csv_path,
                    failure_row,
                    failure_fieldnames(),
                )

                manifest["failed_n"] += 1
                logger.exception("Failed %s", geometry_id)

            write_json(dataset_paths.manifest_path, manifest)

        manifest["status"] = "success"
        manifest["completed_at_utc"] = _utc_now_iso()
        write_json(dataset_paths.manifest_path, manifest)

        logger.info(
            "Dataset generation finished | requested=%d attempted=%d succeeded=%d failed=%d",
            manifest["requested_n"],
            manifest["attempted_n"],
            manifest["succeeded_n"],
            manifest["failed_n"],
        )
        return 0

    except Exception as exc:
        manifest["status"] = "failed"
        manifest["completed_at_utc"] = _utc_now_iso()
        manifest["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        write_json(dataset_paths.manifest_path, manifest)
        logger.exception("Dataset generation failed at pipeline level")
        return 1