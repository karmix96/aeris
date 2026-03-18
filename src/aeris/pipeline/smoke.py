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
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator


def _utc_now_iso() -> str:
    """Return the current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()


def write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON manifest to disk."""
    manifest_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _config_to_dict(config: Any) -> dict[str, Any]:
    if hasattr(config, "to_dict"):
        return dict(config.to_dict())
    if isinstance(config, dict):
        return dict(config)
    raise TypeError(f"Unsupported config type for manifest serialization: {type(config)}")


def run_smoke_pipeline(config_path: str | Path) -> int:
    """
    Run a minimal end-to-end smoke workflow that exercises the real geometry path:
    raw config -> generator resolution -> typed config validation -> one sampled design
    -> one geometry case -> manifest/logging.
    """
    resolved_config_path = Path(config_path).expanduser().resolve()
    run_name = resolved_config_path.stem

    run_paths = create_run_folder(prefix=run_name)
    logger = setup_logger(run_paths.logs / "app.log")
    manifest_path = run_paths.root / "manifest.json"
    copied_config_path = run_paths.root / "input_config.yaml"
    case_output_dir = run_paths.artifacts / "smoke_case"

    manifest: dict[str, Any] = {
        "run_id": run_paths.run_id,
        "phase": "smoke",
        "status": "running",
        "config_path": str(resolved_config_path),
        "copied_config_path": str(copied_config_path),
        "run_root": str(run_paths.root),
        "logs_dir": str(run_paths.logs),
        "artifacts_dir": str(run_paths.artifacts),
        "case_output_dir": str(case_output_dir),
        "platform": platform.system().lower(),
        "python_version": sys.version.split()[0],
        "created_at_utc": _utc_now_iso(),
        "completed_at_utc": None,
        "generator_id": None,
        "sample": None,
        "summary_path": None,
        "error": None,
        "config": None,
    }

    write_manifest(manifest_path, manifest)

    try:
        logger.info("Starting smoke pipeline")
        logger.info("Config path: %s", resolved_config_path)
        logger.info("Run root: %s", run_paths.root)
        logger.info("Artifacts path: %s", run_paths.artifacts)

        raw_config = load_yaml_config(resolved_config_path)
        shutil.copy2(resolved_config_path, copied_config_path)
        logger.info("Copied config to: %s", copied_config_path)

        generator_id, generator_config = resolve_generator_and_config(raw_config)
        generator = get_geometry_generator(generator_id)

        logger.info("Generator selected: %s", generator_id)

        sample = generator.sample_one(
            config=generator_config,
            seed=generator_config.generator.seed,
        )
        logger.info("Generated one smoke sample")

        result = generator.run_full_case(
            sample=sample,
            config=generator_config,
            output_dir=case_output_dir,
        )
        logger.info("Generated one smoke geometry case")

        manifest["generator_id"] = generator_id
        manifest["config"] = _config_to_dict(generator_config)
        manifest["sample"] = sample.to_dict() if hasattr(sample, "to_dict") else str(sample)
        manifest["summary_path"] = str(result.artifact_paths.summary_path)
        manifest["status"] = "success"
        manifest["completed_at_utc"] = _utc_now_iso()

        write_manifest(manifest_path, manifest)

        logger.info("Manifest written: %s", manifest_path)
        logger.info("Smoke pipeline completed successfully")
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

        logger.exception("Smoke pipeline failed")
        return 1
