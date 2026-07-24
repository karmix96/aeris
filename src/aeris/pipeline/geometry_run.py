"""
Pipeline runner for single-case geometry generation.

This module coordinates the end-to-end geometry workflow for one config-driven
run:
- load configuration
- create a reproducible run folder
- resolve the geometry generator
- sample one explicit design vector
- generate one deterministic geometry case
- persist logs, artifacts, and manifest metadata

It acts as the orchestration boundary between CLI commands and generator
implementations.
"""

from __future__ import annotations

import json
import platform
import re
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
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def _get_aeris_version() -> str:
    # Return the installed AERIS package version, or 'unknown'.
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("aeris")
        except PackageNotFoundError:
            return "unknown"
    except Exception:
        return "unknown"


def _to_jsonable(value: Any) -> Any:
    """Convert common Python/project values into JSON-serializable structures."""
    if is_dataclass(value):
        return _to_jsonable(asdict(value))

    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, np.generic):
        return value.item()

    return value


def _write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    """Write the run manifest JSON to disk."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _mark_manifest_failed(
    manifest: dict[str, Any],
    *,
    exc: Exception,
) -> None:
    """Mark a manifest as failed and attach structured error information."""
    manifest["status"] = "failed"
    manifest["completed_at_utc"] = _utc_now_iso()
    manifest["error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }


_PYGEO_EXPORT_KEYS = {
    "iges": ["write_iges"],
    "tecplot": ["write_tecplot"],
    "sections": ["write_section_dat"],
    "npz": ["write_surface_npz", "write_cad_npz"],
    "step": ["write_step"],
    "stl": ["write_stl"],
    "obj": ["write_obj"],
    "vtk": ["write_vtk"],
}
_PYGEO_CAD_EXPORTS = {"step", "stl", "obj", "vtk"}


def _apply_operator_overrides(
    raw_config: dict[str, Any],
    *,
    backend: str | None,
    pygeo_exports: "set[str] | None",
    physical_cad: bool | None,
    plot: bool | None,
    seed: int | None,
    save_detail: bool | None = None,
) -> dict[str, Any]:
    """Patch the raw YAML config with run-time operator overrides (opt-in).

    Keeps the "nothing saved unless requested" policy: exports/CAD/plots are only
    turned ON here when explicitly requested.
    """
    geom = raw_config.setdefault("geometry", {})
    outputs = geom.setdefault("outputs", {})
    pygeo = geom.setdefault("pygeo", {})
    pygeo_outputs = pygeo.setdefault("outputs", {})

    if backend is not None:
        b = backend.strip().lower()
        outputs["build_aerosandbox"] = b in ("aerosandbox", "asb", "both")
        pygeo["enabled"] = b in ("pygeo", "both")
    if seed is not None:
        geom.setdefault("generator", {})["seed"] = int(seed)
    if plot is not None:
        outputs["save_plot"] = bool(plot)
        pygeo_outputs["save_visualization"] = bool(plot)
    if save_detail is not None:
        outputs["save_detail_csv"] = bool(save_detail)
    if physical_cad is not None:
        pygeo.setdefault("physical_cad", {})["enabled"] = bool(physical_cad)
    if pygeo_exports:
        exps = {e.strip().lower() for e in pygeo_exports if e.strip()}
        for name in exps:
            for key in _PYGEO_EXPORT_KEYS.get(name, []):
                pygeo_outputs[key] = True
        # CAD-family exports need the physical CAD stage enabled.
        if (exps & _PYGEO_CAD_EXPORTS) and physical_cad is None:
            pygeo.setdefault("physical_cad", {})["enabled"] = True
    return raw_config


def _write_geometry_metrics(
    case_summary: dict[str, Any], path: Path, sample: Any | None = None
) -> Path | None:
    """Write a concise per-geometry metrics file (the important info) for whichever
    backend(s) actually built. Returns the path, or None if empty."""
    backends = case_summary.get("realization_backends") or {}
    asb_on = bool((backends.get("aerosandbox") or {}).get("enabled"))
    pygeo_on = bool((backends.get("pygeo") or {}).get("enabled"))

    # Taper / root / tip from the design vector (authored; realized differs <0.3%).
    taper_extra: dict[str, float] = {}
    if sample is not None:
        try:
            root = float(sample.c1_m)
            tipr = float(sample.c4_ratio)
            taper_extra = {
                "root_chord_m": root,
                "tip_chord_m": root * tipr,
                "taper_ratio": tipr,
            }
        except Exception:
            taper_extra = {}

    metrics: dict[str, Any] = {}
    if pygeo_on:
        pg = case_summary.get("pygeo_reference_values") or (
            case_summary.get("pygeo") or {}
        ).get("reference_values")
        if isinstance(pg, dict) and pg:
            metrics["pygeo"] = {**pg, **taper_extra}
    if asb_on:
        rv = case_summary.get("reference_values")
        if isinstance(rv, dict) and rv:
            # ASB reports taper_ratio itself; keep it if present, else fill.
            merged = {**taper_extra, **rv}
            metrics["aerosandbox"] = merged
    if not metrics:
        return None
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return path


def run_geometry_generation(
    config_path: str | Path,
    *,
    save_plot: bool | None = None,
    build_aerosandbox: bool | None = None,
    backend: str | None = None,
    pygeo_exports: "set[str] | None" = None,
    physical_cad: bool | None = None,
    save_metrics: bool = False,
    save_detail: bool | None = None,
    seed: int | None = None,
) -> tuple[int, Path | None]:
    """
    Run a single geometry-generation workflow.

    Architecture rule:
    - RNG is used only to sample one explicit design vector.
    - From that point onward, geometry realization is deterministic.
    """
    resolved_config_path = Path(config_path).expanduser().resolve()
    run_name = re.sub(r"[^a-zA-Z0-9_-]", "_", resolved_config_path.stem)

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
        "aeris_version": _get_aeris_version(),
        "created_at_utc": _utc_now_iso(),
        "completed_at_utc": None,
        "error": None,
        "geometry": None,
        "operator_overrides": {
            "save_plot": save_plot,
            "build_aerosandbox": build_aerosandbox,
        },
    }

    _write_manifest(manifest_path, manifest)

    try:
        logger.info("Starting geometry generation")
        logger.info("Config path: %s", resolved_config_path)
        logger.info("Run root: %s", run_paths.root)

        raw_config = load_yaml_config(resolved_config_path)
        _apply_operator_overrides(
            raw_config, backend=backend, pygeo_exports=pygeo_exports,
            physical_cad=physical_cad, plot=save_plot, seed=seed,
            save_detail=save_detail,
        )
        shutil.copy2(resolved_config_path, copied_config_path)

        geometry_dir.mkdir(parents=True, exist_ok=True)

        generator_id, generator_config = resolve_generator_and_config(raw_config)
        generator = get_geometry_generator(generator_id)

        design_sampling_seed = generator_config.generator.seed

        logger.info(
            "Generator selected: family=%s version=%s id=%s",
            generator_config.generator.family,
            generator_config.generator.version,
            generator_id,
        )
        logger.info("Design sampling seed: %s", design_sampling_seed)
        if design_sampling_seed is None:
            logger.warning(
                "design_sampling_seed is None — run is NOT reproducible. "
                "Set geometry.generator.seed in the config to fix this."
            )
        logger.info("Geometry realization mode: deterministic from explicit design sample")

        design_sample = generator.sample_one(generator_config, seed=design_sampling_seed)
        logger.info("Design sample generated successfully")

        run_kwargs: dict[str, Any] = {}
        if save_plot is not None:
            run_kwargs["save_plot"] = save_plot
        if build_aerosandbox is not None:
            run_kwargs["build_aerosandbox"] = build_aerosandbox

        case_result = generator.run_full_case(
            sample=design_sample,
            config=generator_config,
            output_dir=geometry_dir,
            **run_kwargs,
        )
        case_summary = generator.summarize_case(case_result)
        logger.info("Geometry case generated successfully")

        metrics_path = None
        if save_metrics:
            metrics_path = _write_geometry_metrics(
                case_summary, run_paths.root / "geometry_metrics.json",
                sample=design_sample,
            )
            if metrics_path is not None:
                logger.info("Geometry metrics saved: %s", metrics_path)

        manifest["geometry"] = {
            "name": getattr(generator_config, "name", None),
            "generator_family": getattr(
                getattr(generator_config, "generator", None), "family", None
            ),
            "generator_version": getattr(
                getattr(generator_config, "generator", None), "version", None
            ),
            "generator_id": generator_id,
            "design_sampling_seed": design_sampling_seed,
            "geometry_deterministic": True,
            "design_sample": _to_jsonable(design_sample),
            "case_summary": _to_jsonable(case_summary),
            "operator_overrides": {
                "save_plot": save_plot,
                "build_aerosandbox": build_aerosandbox,
                "backend": backend,
                "pygeo_exports": sorted(pygeo_exports) if pygeo_exports else None,
                "physical_cad": physical_cad,
                "save_metrics": save_metrics,
                "seed": seed,
            },
            "metrics_path": str(metrics_path) if metrics_path else None,
        }
        manifest["status"] = "success"
        manifest["completed_at_utc"] = _utc_now_iso()

        _write_manifest(manifest_path, manifest)

        logger.info("Geometry generation completed successfully")
        return 0, run_paths.root

    except Exception as exc:
        logger.exception("Geometry run failed.")
        _mark_manifest_failed(manifest, exc=exc)
        _write_manifest(manifest_path, manifest)
        return 1, run_paths.root
