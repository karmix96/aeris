from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aeris.common.config import load_yaml_config
from aeris.common.logging_utils import setup_logger
from aeris.dataset import sampling as _dataset_sampling_plugins  # noqa: F401
from aeris.dataset.io import (
    append_csv_row,
    ensure_csv_with_header,
    ensure_dataset_paths,
    write_json,
)
from aeris.dataset.metadata import (
    build_failure_row,
    build_metadata_row,
    failure_fieldnames,
    metadata_fieldnames,
)
from aeris.dataset.sampling.registry import get_dataset_sampler
from aeris.dataset.sampling.resolver import resolve_dataset_sampler
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _config_to_dict(config: Any) -> dict[str, Any]:
    if hasattr(config, "to_dict"):
        return dict(config.to_dict())
    if is_dataclass(config):
        return asdict(config)
    if isinstance(config, dict):
        return dict(config)
    raise TypeError(f"Unsupported config type: {type(config)}")


def _default_dataset_name(
    config_path: Path,
    config: Any,
    n_samples: int,
    sampler_id: str,
    sampler_seed: int | None,
) -> str:
    seed_part = "none" if sampler_seed is None else str(sampler_seed)

    if sampler_id == "lhs_v1":
        sampling_suffix = f"lhs{seed_part}"
    else:
        sampling_suffix = f"{sampler_id}_seed{seed_part}"

    return (
        f"{config_path.stem}_"
        f"{config.generator.family}_{config.generator.version}_"
        f"n{n_samples}_{sampling_suffix}"
    )


def _make_effective_dataset_config(
    config: Any,
    *,
    save_plot: bool | None = None,
    build_aerosandbox: bool | None = None,
) -> Any:
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


def _resolve_dataset_request(
    *,
    config_path: str | Path,
    n_samples: int,
    dataset_name: str | None,
    save_plot: bool | None,
    build_aerosandbox: bool | None,
    sampler: str | None,
    sampler_seed: int | None,
) -> dict[str, Any]:
    resolved_config_path = Path(config_path).expanduser().resolve()

    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")

    raw_config = load_yaml_config(resolved_config_path)
    generator_id, base_config = resolve_generator_and_config(raw_config)
    effective_config = _make_effective_dataset_config(
        base_config,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
    )

    sampler_id, resolved_sampler_seed = resolve_dataset_sampler(
        raw_config,
        sampler_override=sampler,
        sampler_seed_override=sampler_seed,
    )

    effective_dataset_name = dataset_name or _default_dataset_name(
        resolved_config_path,
        effective_config,
        n_samples,
        sampler_id,
        resolved_sampler_seed,
    )

    return {
        "resolved_config_path": resolved_config_path,
        "generator_id": generator_id,
        "effective_config": effective_config,
        "sampler_id": sampler_id,
        "sampler_seed": resolved_sampler_seed,
        "dataset_name": effective_dataset_name,
    }


def run_dataset_generation(
    *,
    config_path: str | Path,
    n_samples: int,
    dataset_name: str | None = None,
    save_plot: bool | None = None,
    build_aerosandbox: bool | None = None,
    sampler: str | None = None,
    sampler_seed: int | None = None,
) -> int:
    """
    Generate a geometry dataset using the selected dataset sampler and the
    selected generator's deterministic realization path.
    """
    request = _resolve_dataset_request(
        config_path=config_path,
        n_samples=n_samples,
        dataset_name=dataset_name,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
        sampler=sampler,
        sampler_seed=sampler_seed,
    )

    resolved_config_path = request["resolved_config_path"]
    generator_id = request["generator_id"]
    effective_config = request["effective_config"]
    sampler_id = request["sampler_id"]
    resolved_sampler_seed = request["sampler_seed"]
    effective_dataset_name = request["dataset_name"]

    generator = get_geometry_generator(generator_id)
    sampler_obj = get_dataset_sampler(sampler_id)

    dataset_paths = ensure_dataset_paths(effective_dataset_name)
    logger = setup_logger(
        dataset_paths.logs_dir / "dataset.log",
        logger_name=f"aeris.dataset.{effective_dataset_name}",
    )

    shutil.copy2(resolved_config_path, dataset_paths.input_config_path)
    write_json(dataset_paths.resolved_config_json_path, _config_to_dict(effective_config))

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
        "sampler_id": sampler_id,
        "sampler_seed": resolved_sampler_seed,
        "geometry_deterministic": True,
        "generator_family": effective_config.generator.family,
        "generator_version": effective_config.generator.version,
        "generator_id": generator_id,
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
            "Generator selected: family=%s version=%s id=%s",
            effective_config.generator.family,
            effective_config.generator.version,
            generator_id,
        )
        logger.info("Sampler selected: %s", sampler_id)
        logger.info("Sampler seed: %s", resolved_sampler_seed)
        logger.info("Geometry realization mode: deterministic from explicit design sample")

        samples = sampler_obj.sample(
            config=effective_config,
            n_samples=n_samples,
            sampler_seed=resolved_sampler_seed,
        )
        logger.info("Generated %d batch design samples", len(samples))

        for case_index, sample in enumerate(samples, start=1):
            geometry_id = f"geom_{case_index:05d}"
            case_geometry_dir = dataset_paths.geometry_dir / geometry_id

            manifest["attempted_n"] = case_index
            write_json(dataset_paths.manifest_path, manifest)

            try:
                logger.info("Generating %s", geometry_id)

                result = generator.run_full_case(
                    sample=sample,
                    config=effective_config,
                    output_dir=case_geometry_dir,
                )

                row = build_metadata_row(
                    dataset_name=effective_dataset_name,
                    geometry_id=geometry_id,
                    case_index=case_index,
                    sampler_id=sampler_id,
                    sampler_seed=resolved_sampler_seed,
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
                    sampler_id=sampler_id,
                    sampler_seed=resolved_sampler_seed,
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
