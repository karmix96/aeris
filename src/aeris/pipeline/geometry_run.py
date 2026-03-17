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
from aeris.geometry.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.geometry.export import (
    build_geometry_summary,
    export_control_points_csv,
    export_geometry_summary,
    export_planform_sections_csv,
    export_section_3d_csv,
)
from aeris.geometry.params import build_bwb_generator_config
from aeris.geometry.planform import generate_bwb_planform_from_sample
from aeris.geometry.plotting import save_planform_plot
from aeris.geometry.sampling import sample_bwb_design
from aeris.geometry.sections import build_section_geometry_from_sample
from aeris.geometry.validation import (
    validate_bwb_generator_config,
    validate_planform_result,
    validate_section_geometry,
)


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
    plots_dir = geometry_dir / "plots"

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
        plots_dir.mkdir(parents=True, exist_ok=True)

        bwb_config = build_bwb_generator_config(raw_config)
        validate_bwb_generator_config(bwb_config)

        design_sampling_seed = bwb_config.generator.seed
        design_rng = np.random.default_rng(design_sampling_seed)

        logger.info(
            "Generator selected: family=%s version=%s",
            bwb_config.generator.family,
            bwb_config.generator.version,
        )
        logger.info("Design sampling seed: %s", design_sampling_seed)
        logger.info("Geometry realization mode: deterministic from explicit design sample")

        design_sample = sample_bwb_design(bwb_config, design_rng)
        logger.info("Design sample generated successfully")

        planform = generate_bwb_planform_from_sample(design_sample, bwb_config)
        validate_planform_result(planform)
        logger.info("Planform generated and validated")

        section_geometry = build_section_geometry_from_sample(
            planform,
            design_sample,
            bwb_config,
        )
        validate_section_geometry(section_geometry)
        logger.info("Section geometry generated and validated")

        aerosandbox_result = None
        if bwb_config.outputs.build_aerosandbox:
            aerosandbox_result = build_aerosandbox_geometry(section_geometry, bwb_config)
            logger.info(
                "AeroSandbox geometry built successfully (AR=%.6f)",
                aerosandbox_result.aspect_ratio,
            )

        summary_path = geometry_dir / "geometry_summary.json"
        control_points_path = geometry_dir / "control_points.csv"
        planform_sections_path = geometry_dir / "planform_sections.csv"
        section_3d_path = geometry_dir / "section_3d.csv"
        plot_path = plots_dir / "planform.png"

        export_control_points_csv(planform, control_points_path)
        export_planform_sections_csv(planform, planform_sections_path)
        export_section_3d_csv(section_geometry, section_3d_path)

        logger.info("Control points written: %s", control_points_path)
        logger.info("Planform sections written: %s", planform_sections_path)
        logger.info("3D section definitions written: %s", section_3d_path)

        if bwb_config.outputs.save_plot:
            save_planform_plot(planform, section_geometry, bwb_config, plot_path)
            logger.info("Planform plot written: %s", plot_path)

        artifact_paths = {
            "summary_path": str(summary_path),
            "control_points_path": str(control_points_path),
            "planform_sections_path": str(planform_sections_path),
            "section_3d_path": str(section_3d_path),
            "plot_path": str(plot_path) if bwb_config.outputs.save_plot else None,
        }

        summary = build_geometry_summary(
            config=bwb_config,
            planform=planform,
            section_geometry=section_geometry,
            aerosandbox_result=aerosandbox_result,
            artifact_paths=artifact_paths,
        )
        export_geometry_summary(summary, summary_path)
        logger.info("Geometry summary written: %s", summary_path)

        manifest["geometry"] = {
            "name": bwb_config.name,
            "generator_family": bwb_config.generator.family,
            "generator_version": bwb_config.generator.version,
            "design_sampling_seed": design_sampling_seed,
            "geometry_deterministic": True,
            "design_sample": _to_jsonable(design_sample),
            "num_sections": planform.num_sections,
            "summary_path": str(summary_path),
            "control_points_path": str(control_points_path),
            "planform_sections_path": str(planform_sections_path),
            "section_3d_path": str(section_3d_path),
            "plot_path": str(plot_path) if bwb_config.outputs.save_plot else None,
            "aspect_ratio_aerosandbox": (
                None if aerosandbox_result is None else aerosandbox_result.aspect_ratio
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