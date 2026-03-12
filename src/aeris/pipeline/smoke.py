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


def _utc_now_iso() -> str:
    """Return the current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()


def write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON manifest to disk."""
    manifest_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def run_smoke_pipeline(config_path: str | Path) -> int:
    """Run a minimal end-to-end smoke workflow with failure handling."""
    resolved_config_path = Path(config_path).expanduser().resolve()
    run_name = resolved_config_path.stem

    run_paths = create_run_folder(prefix=run_name)
    logger = setup_logger(run_paths.logs / "app.log")
    manifest_path = run_paths.root / "manifest.json"
    copied_config_path = run_paths.root / "input_config.yaml"

    manifest: dict[str, Any] = {
        "run_id": run_paths.run_id,
        "phase": "smoke",
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
        "config": None,
    }

    write_manifest(manifest_path, manifest)

    try:
        logger.info("Starting smoke pipeline")
        logger.info("Config path: %s", resolved_config_path)
        logger.info("Run root: %s", run_paths.root)
        logger.info("Artifacts path: %s", run_paths.artifacts)

        config = load_yaml_config(resolved_config_path)
        shutil.copy2(resolved_config_path, copied_config_path)
        logger.info("Copied config to: %s", copied_config_path)

        manifest["config"] = config
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
