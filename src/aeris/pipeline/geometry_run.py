from __future__ import annotations

import json
import platform
import shutil
import sys
import traceback
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from aeris.common.config import load_yaml_config
from aeris.common.logging_utils import setup_logger
from aeris.common.paths import create_run_folder
from aeris.geometry.params import build_bwb_generator_config
from aeris.geometry.registry import get_geometry_generator
from aeris.geometry.validation import validate_bwb_generator_config


def _utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _to_jsonable(value: Any) -> Any:
    """
    Convert supported Python objects into JSON-serializable structures.

    This is mainly used so manifests can safely store dataclass-based
    samples/config fragments without exploding at write time.
    """
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}

    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, np.generic):
        return value.item()

    return value


def write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    """Write a manifest JSON file to disk."""
    manifest_path.write_text(
        json.dumps(_to_jsonable(payload), indent=2),
        encoding="utf-8",
    )


def run_geometry_generation(config_path: str | Path) -> int:
    """
    Run a single geometry-generation workflow.

    Architecture rule:
    - RNG is used only to sample one explicit design vector.
    - From that point onward, geometry realization is deterministic.
    """
    resolved_config_path = Path(config_path).expanduser().resolve()
    run_name = resolved_config_path.stem

    run_paths = create_run_folder(prefix=f"geometry_{run_name}")
    logger = setup_logger(run_paths.logs / "app.log")

    manifest_path = run_paths.root / "manifest.json"
    copied_config_path = run_paths.root / "input_config.yaml"

    geometry_dir = run_paths.artifacts / "geometry"

    manifest: dict[str, Any] = {
        "run_id": run_paths.run_id,
        "phase": "geometry_generate",
        "status": "running",
        "config_path": str(resolved_config_path),
        "copied_config_path": str(copied_config_path),
        "run_root": str(run_paths.root),
        "logs_dir": str(run_paths.logs),
        "artifacts_dir": str(run_paths.artifacts),
        "platform": platform.system().lower(),
        "python_version": sys.version.split()[0],
        "created_at_utc": _utc_now_iso(),
        "completed_at_utc": None,
        "error": None,
        "geometry": None,
    }

    write_manifest(manifest_path, manifest)

    try:
        logger.info("Starting geometry generation")
        logger.info("Config path: %s", resolved_config_path)
        logger.info("Run root: %s", run_paths.root)

        raw_config = load_yaml_config(resolved_config_path)
        shutil.copy2(resolved_config_path, copied_config_path)

        geometry_dir.mkdir(parents=True, exist_ok=True)

        # Transitional compatibility path:
        # current configs still map to the validated BWB segmented generator.
        bwb_config = build_bwb_generator_config(raw_config)
        validate_bwb_generator_config(bwb_config)

        generator_id = f"{bwb_config.generator.family}_{bwb_config.generator.version}"
        generator = get_geometry_generator(generator_id)

        design_sampling_seed = bwb_config.generator.seed

        logger.info(
            "Generator selected: family=%s version=%s id=%s",
            bwb_config.generator.family,
            bwb_config.generator.version,
            generator_id,
        )
        logger.info("Design sampling seed: %s", design_sampling_seed)
        logger.info("Geometry realization mode: deterministic from explicit design sample")

        design_sample = generator.sample_one(bwb_config, seed=design_sampling_seed)
        logger.info("Design sample generated successfully")

        if not hasattr(generator, "run_full_case"):
            raise AttributeError(
                f"Generator '{generator_id}' does not implement run_full_case()."
            )

        case_result = generator.run_full_case(
            sample=design_sample,
            config=bwb_config,
            output_dir=geometry_dir,
        )
        logger.info("Geometry case generated successfully")

        manifest["geometry"] = {
            "name": bwb_config.name,
            "generator_family": bwb_config.generator.family,
            "generator_version": bwb_config.generator.version,
            "generator_id": generator_id,
            "design_sampling_seed": design_sampling_seed,
            "geometry_deterministic": True,
            "design_sample": _to_jsonable(design_sample),
            "num_sections": case_result.planform.num_sections,
            "summary_path": str(case_result.artifact_paths.summary_path),
            "control_points_path": str(case_result.artifact_paths.control_points_path),
            "planform_sections_path": str(case_result.artifact_paths.planform_sections_path),
            "section_3d_path": str(case_result.artifact_paths.section_3d_path),
            "plot_path": (
                None
                if case_result.artifact_paths.plot_path is None
                else str(case_result.artifact_paths.plot_path)
            ),
            "aspect_ratio_aerosandbox": (
                None
                if case_result.aerosandbox_result is None
                else case_result.aerosandbox_result.aspect_ratio
            ),
        }
        manifest["status"] = "success"
        manifest["completed_at_utc"] = _utc_now_iso()

        write_manifest(manifest_path, manifest)

        logger.info("Geometry generation completed successfully")
        return 0

    except Exception as exc:
        manifest["status"] = "failed"
        manifest["completed_at_utc"] = _utc_now_iso()
        manifest["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

        write_manifest(manifest_path, manifest)
        logger.exception("Geometry generation failed")
        return 1