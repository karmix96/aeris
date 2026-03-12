from __future__ import annotations

import json
import platform
import shutil
import sys
import traceback
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from aeris.common.config import load_yaml_config
from aeris.common.logging_utils import setup_logger
from aeris.common.paths import create_run_folder
from aeris.geometry.export import export_geometry_summary, export_planform_sections_csv
from aeris.geometry.params import build_wing_geometry_params
from aeris.geometry.validation import validate_wing_geometry_params


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_geometry_generation(config_path: str | Path) -> int:
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

        config = load_yaml_config(resolved_config_path)
        shutil.copy2(resolved_config_path, copied_config_path)
        geometry_dir.mkdir(parents=True, exist_ok=True)

        params = build_wing_geometry_params(config)
        validate_wing_geometry_params(params)

        summary_path = geometry_dir / "geometry_summary.json"
        sections_path = geometry_dir / "planform_sections.csv"

        export_geometry_summary(params, summary_path)
        export_planform_sections_csv(params, sections_path)

        manifest["geometry"] = {
            "parameters": params.to_dict(),
            "summary_path": str(summary_path),
            "sections_path": str(sections_path),
        }
        manifest["status"] = "success"
        manifest["completed_at_utc"] = _utc_now_iso()

        write_manifest(manifest_path, manifest)

        logger.info("Geometry summary written: %s", summary_path)
        logger.info("Planform sections written: %s", sections_path)
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
