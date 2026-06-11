"""
Pipeline/orchestration helpers for aerodynamic runs and sweeps.

This module keeps workflow orchestration out of the CLI layer:
- geometry source preparation
- run folder creation
- manifest assembly
- delegation to aero solver / sweep execution
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from aeris.aero import AeroInput, AeroSolverSettings, FlightCondition, create_solver
from aeris.aero.models import FlightConditionSweep
from aeris.aero.sweep_run import run_aero_sweep
from aeris.aero.views import (
    geometry_view_from_case,
    geometry_view_from_dataset_case,
    geometry_view_from_run_dir,
)
from aeris.common.config import file_sha256, load_yaml_config
from aeris.common.logging_utils import setup_logger
from aeris.common.paths import create_run_folder, write_run_manifest
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.aero.io import _write_aero_result_json


def create_aero_run_root(output_name: str, label: str, prefix: str) -> tuple[Any, Path, Path]:
    suffix = output_name.strip() or label.strip()
    run_paths = create_run_folder(prefix=f"{prefix}_{suffix}")
    run_root = run_paths.root
    geometry_dir = run_root / "geometry"
    aero_dir = run_root / "aero"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    aero_dir.mkdir(parents=True, exist_ok=True)
    return run_paths, geometry_dir, aero_dir


def _copy_standard_input_config(config: Path | None, run_root: Path) -> Path | None:
    """Copy the input config to the standard run-root input_config.yaml path."""
    if config is None:
        return None

    resolved = Path(config).expanduser().resolve()
    if not resolved.exists():
        return None

    copied = run_root / "input_config.yaml"
    shutil.copy2(resolved, copied)
    return copied


def _config_manifest_fields(config: Path | None, copied_config_path: Path | None) -> dict[str, Any]:
    """Return generic manifest fields for the source config, if available."""
    fields: dict[str, Any] = {}

    if config is not None:
        resolved = Path(config).expanduser().resolve()
        fields["config_path"] = str(resolved)
        if resolved.exists():
            fields["config_sha256"] = file_sha256(resolved)

    if copied_config_path is not None:
        fields["copied_config_path"] = str(copied_config_path)

    return fields


def sample_one(generator_id: str, typed_config: Any, seed: int) -> Any:
    generator = get_geometry_generator(generator_id)
    return generator.sample_one(typed_config, seed=seed)


def run_full_case(
    generator_id: str,
    sample: Any,
    typed_config: Any,
    output_dir: Path,
    save_plot: bool,
    build_aerosandbox: bool,
) -> Any:
    generator = get_geometry_generator(generator_id)
    return generator.run_full_case(
        sample=sample,
        config=typed_config,
        output_dir=output_dir,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
    )


def summarize_case(generator_id: str, case: Any) -> Any:
    generator = get_geometry_generator(generator_id)
    return generator.summarize_case(case)


def prepare_geometry_for_aero(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
    source_policy: str,
    seed: int,
    geometry_dir: Path,
    generator_id: str | None = None,
    copy_config_to: Path | None = None,
) -> tuple[Any, str, Any]:
    """
    Prepare an AeroGeometryView from one of the supported source modes.

    Returns:
        geometry_view, resolved_generator_id, summary
    """
    summary: Any = {}
    geometry_view = None

    if config is not None:
        raw_config = load_yaml_config(config)
        resolved_generator_id, typed_config = resolve_generator_and_config(raw_config)

        sample = sample_one(
            generator_id=resolved_generator_id,
            typed_config=typed_config,
            seed=seed,
        )
        case = run_full_case(
            generator_id=resolved_generator_id,
            sample=sample,
            typed_config=typed_config,
            output_dir=geometry_dir,
            save_plot=False,
            build_aerosandbox=True,
        )
        summary = summarize_case(generator_id=resolved_generator_id, case=case)

        geometry_view = geometry_view_from_case(
            case=case,
            generator_id=resolved_generator_id,
            case_dir=geometry_dir,
            source_policy=source_policy,
        )

        if copy_config_to is not None and config.exists():
            shutil.copy2(config, copy_config_to / config.name)

        return geometry_view, resolved_generator_id, summary

    # Default to bwb_segmented_v1 when not provided — mirrors the default in
    # geometry_view_from_run_dir and geometry_view_from_dataset_case so that
    # `aeris aero sweep --dataset ...` works without --generator-id.
    _resolved_gen_id = (generator_id or "").strip() or "bwb_segmented_v1"

    if run_dir is not None:
        geometry_view = geometry_view_from_run_dir(
            run_dir=run_dir,
            generator_id=_resolved_gen_id,
        )
        summary = {
            "source_mode": "run_dir",
            "run_dir": str(run_dir.resolve()),
        }
        return geometry_view, _resolved_gen_id, summary

    geometry_view = geometry_view_from_dataset_case(
        dataset_root=dataset,
        geometry_id=geometry_id,
        generator_id=_resolved_gen_id,
    )
    summary = {
        "source_mode": "dataset",
        "dataset_root": str(dataset.resolve()),
        "geometry_id": geometry_id,
    }
    return geometry_view, _resolved_gen_id, summary


def dataclass_or_value(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

def _should_retry_with_finer_paneling(result: Any) -> tuple[bool, str | None]:
    if getattr(result, "status", None) is not None:
        status_value = getattr(result.status, "value", str(result.status))
        if status_value == "invalid_input":
            return False, None

    cd = getattr(result, "cd", None)
    ld = getattr(result, "l_over_d", None)

    try:
        if cd is None:
            return True, "missing_cd"
        if float(cd) <= 0.0:
            return True, f"non_positive_cd:{cd}"
    except Exception:
        return True, "invalid_cd"

    if ld is None:
        return True, "missing_l_over_d"

    if not result.is_success():
        return True, f"status={result.status.value}"

    return False, None


def _inject_retry_metadata(
    final_result: Any,
    *,
    used: bool,
    reason: str | None,
    initial_paneling: dict[str, Any],
    fallback_paneling: dict[str, Any] | None,
    initial_result: Any,
) -> None:
    meta = final_result.solver_metadata or {}
    meta["fallback_retry"] = {
        "used": used,
        "reason": reason,
        "initial_paneling": initial_paneling,
        "fallback_paneling": fallback_paneling,
        "initial_status": initial_result.status.value,
        "initial_cd": initial_result.cd,
        "initial_l_over_d": initial_result.l_over_d,
    }
    final_result.solver_metadata = meta

def execute_aero_run(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
    geometry_source: str,
    generator_id: str | None,
    control_input_deg: float | None,
    alpha: float,
    velocity: float,
    altitude: float,
    beta: float,
    mach: float,
    p: float,
    q: float,
    r: float,
    solver: str,
    avl_command: str,
    timeout_sec: int,
    spanwise_resolution: int,
    chordwise_resolution: int,
    spanwise_spacing: str,
    chordwise_spacing: str,
    save_surface_forces: bool,
    save_element_forces: bool,
    seed: int,
    output_name: str,
) -> tuple[Path, Any]:
    label = (
        config.stem if config is not None
        else run_dir.name if run_dir is not None
        else geometry_id
    )

    run_paths, geometry_dir, aero_dir = create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero",
    )
    run_root = run_paths.root
    logger = setup_logger(run_paths.logs / "app.log")
    logger.info("Starting aero run")
    logger.info("Run root: %s", run_root)
    copied_config_path = _copy_standard_input_config(config, run_root)

    geometry_view, resolved_generator_id, summary = prepare_geometry_for_aero(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=geometry_source,
        seed=seed,
        geometry_dir=geometry_dir,
        generator_id=generator_id,
        copy_config_to=None,  # standard copy is input_config.yaml via _copy_standard_input_config()
    )

    aero_input = AeroInput(
        geometry=geometry_view,
        flight_condition=FlightCondition(
            alpha_deg=alpha,
            beta_deg=beta,
            mach=mach,
            velocity_mps=velocity,
            altitude_m=altitude,
            p_rad_s=p,
            q_rad_s=q,
            r_rad_s=r,
        ),
        settings=AeroSolverSettings(
            avl_command=avl_command or None,
            timeout_sec=timeout_sec,
            verbose=False,
            solver_options={
                "paneling": {
                    "spanwise_resolution": spanwise_resolution,
                    "chordwise_resolution": chordwise_resolution,
                    "spanwise_spacing": spanwise_spacing,
                    "chordwise_spacing": chordwise_spacing,
                },
                "save_surface_forces": save_surface_forces,
                "save_element_forces": save_element_forces,
                "control_input_deg": control_input_deg,
            },
        ),
        provenance={
            "solver": solver,
            "seed": seed,
            "geometry_source": geometry_source,
            "source_label": label,
            "resolved_generator_id": resolved_generator_id,
        },
    )

    solver_instance = create_solver(solver)

    initial_paneling = {
        "spanwise_resolution": spanwise_resolution,
        "chordwise_resolution": chordwise_resolution,
        "spanwise_spacing": spanwise_spacing,
        "chordwise_spacing": chordwise_spacing,
    }

    result = solver_instance.run_case(
        aero_input=aero_input,
        output_dir=aero_dir,
    )

    should_retry, retry_reason = _should_retry_with_finer_paneling(result)

    if should_retry:
        retry_input = AeroInput(
            geometry=aero_input.geometry,
            flight_condition=aero_input.flight_condition,
            settings=AeroSolverSettings(
                avl_command=avl_command or None,
                timeout_sec=timeout_sec,
                verbose=False,
                solver_options={
                    "paneling": {
                        "spanwise_resolution": 8,
                        "chordwise_resolution": 12,
                        "spanwise_spacing": spanwise_spacing,
                        "chordwise_spacing": chordwise_spacing,
                    },
                    "save_surface_forces": save_surface_forces,
                    "save_element_forces": save_element_forces,
                    "control_input_deg": control_input_deg,
                },
            ),
            provenance=dict(aero_input.provenance),
        )

        retry_result = solver_instance.run_case(
            aero_input=retry_input,
            output_dir=aero_dir,
        )

        retry_ok, _ = _should_retry_with_finer_paneling(retry_result)

        if not retry_ok:
            _inject_retry_metadata(
                retry_result,
                used=True,
                reason=retry_reason,
                initial_paneling=initial_paneling,
                fallback_paneling=retry_input.settings.solver_options["paneling"],
                initial_result=result,
            )
            result = retry_result
        else:
            _inject_retry_metadata(
                result,
                used=True,
                reason=retry_reason,
                initial_paneling=initial_paneling,
                fallback_paneling=retry_input.settings.solver_options["paneling"],
                initial_result=result,
            )
    else:
        _inject_retry_metadata(
            result,
            used=False,
            reason=None,
            initial_paneling=initial_paneling,
            fallback_paneling=None,
            initial_result=result,
        )

    # Persist the final post-processed result chosen by the pipeline.
    # The solver writes aero_result.json during each run_case() call, but the
    # pipeline may later inject fallback metadata and/or replace the initial
    # result with a successful retry result. Rewrite the final chosen result so
    # aero_result.json matches what the pipeline is actually returning.
    result.artifact_paths["aero_result_json"] = str(aero_dir / "aero_result.json")
    _write_aero_result_json(result, aero_dir)
    
    manifest = {
        "run_name": run_root.name,
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "flight_condition": to_jsonable(asdict(aero_input.flight_condition)),
        "geometry_summary": to_jsonable(dataclass_or_value(summary)),
        "aero_result": to_jsonable(dataclass_or_value(result)),
    }
    aero_manifest_path = run_root / "aero_manifest.json"
    aero_manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    generic_manifest_extra: dict[str, Any] = {
        "phase": "aero_run",
        "status": getattr(result.status, "value", str(result.status)),
        "domain_manifest": str(aero_manifest_path),
        "aero_result_json": str(aero_dir / "aero_result.json"),
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "run_artifacts": {
            "geometry_dir": str(geometry_dir),
            "aero_dir": str(aero_dir),
        },
    }
    generic_manifest_extra.update(_config_manifest_fields(config, copied_config_path))
    write_run_manifest(run_paths, extra=generic_manifest_extra)
    logger.info("Aero run completed with status=%s", generic_manifest_extra["status"])

    return run_root, result


def execute_aero_sweep(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
    geometry_source: str,
    generator_id: str | None,
    control_input_deg: float | None,
    control_input_values: list[float],
    diff_input_values: list[float] | None = None,
    alpha: float,
    velocity: float,
    altitude: float,
    beta: float,
    mach: float,
    p: float,
    q: float,
    r: float,
    alpha_values: list[float],
    beta_values: list[float],
    velocity_values: list[float],
    altitude_values: list[float],
    p_values: list[float],
    q_values: list[float],
    r_values: list[float],
    solver: str,
    avl_command: str,
    timeout_sec: int,
    spanwise_resolution: int,
    chordwise_resolution: int,
    spanwise_spacing: str,
    chordwise_spacing: str,
    save_surface_forces: bool,
    save_element_forces: bool,
    seed: int,
    output_name: str,
    max_cases: int | None = None,
) -> tuple[Path, Any]:
    label = (
        config.stem if config is not None
        else run_dir.name if run_dir is not None
        else geometry_id
    )

    run_paths, geometry_dir, sweep_dir = create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero_sweep",
    )
    run_root = run_paths.root
    logger = setup_logger(run_paths.logs / "app.log")
    logger.info("Starting aero sweep")
    logger.info("Run root: %s", run_root)
    copied_config_path = _copy_standard_input_config(config, run_root)

    geometry_view, resolved_generator_id, summary = prepare_geometry_for_aero(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=geometry_source,
        seed=seed,
        geometry_dir=geometry_dir,
        generator_id=generator_id,
        copy_config_to=None,  # standard copy is input_config.yaml via _copy_standard_input_config()
    )

    base_fc = FlightCondition(
        alpha_deg=alpha,
        beta_deg=beta,
        mach=mach,
        velocity_mps=velocity,
        altitude_m=altitude,
        p_rad_s=p,
        q_rad_s=q,
        r_rad_s=r,
    )

    sweep = FlightConditionSweep(
        alpha_deg_values=alpha_values,
        beta_deg_values=beta_values,
        velocity_mps_values=velocity_values,
        altitude_m_values=altitude_values,
        p_rad_s_values=p_values,
        q_rad_s_values=q_values,
        r_rad_s_values=r_values,
        control_input_deg_values=control_input_values,
        diff_input_deg_values=diff_input_values or [],
    )

    settings = AeroSolverSettings(
        avl_command=avl_command or None,
        timeout_sec=timeout_sec,
        verbose=False,
        solver_options={
            "paneling": {
                "spanwise_resolution": spanwise_resolution,
                "chordwise_resolution": chordwise_resolution,
                "spanwise_spacing": spanwise_spacing,
                "chordwise_spacing": chordwise_spacing,
            },
            "save_surface_forces": save_surface_forces,
            "save_element_forces": save_element_forces,
            "control_input_deg": control_input_deg,
        },
    )

    sweep_result = run_aero_sweep(
        geometry=geometry_view,
        base_flight_condition=base_fc,
        sweep=sweep,
        solver_id=solver,
        settings=settings,
        output_dir=sweep_dir,
        provenance={
            "solver": solver,
            "seed": seed,
            "geometry_source": geometry_source,
            "source_label": label,
            "resolved_generator_id": resolved_generator_id,
        },
        max_cases=max_cases,
    )

    manifest = {
        "run_name": run_root.name,
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "base_flight_condition": to_jsonable(asdict(base_fc)),
        "flight_condition_sweep": to_jsonable(asdict(sweep)),
        "geometry_summary": to_jsonable(dataclass_or_value(summary)),
        "aero_sweep_result": to_jsonable(dataclass_or_value(sweep_result)),
    }
    aero_sweep_manifest_path = run_root / "aero_sweep_manifest.json"
    aero_sweep_manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    sweep_summary = manifest.get("aero_sweep_result", {}).get("summary", {})
    n_failed_total = int(sweep_summary.get("n_failed_total", 0) or 0)
    sweep_status = "success" if n_failed_total == 0 else "completed_with_failures"

    generic_manifest_extra: dict[str, Any] = {
        "phase": "aero_sweep",
        "status": sweep_status,
        "domain_manifest": str(aero_sweep_manifest_path),
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "requested_n_cases": sweep_summary.get("requested_n_cases"),
        "completed_n_cases": sweep_summary.get("completed_n_cases"),
        "n_success": sweep_summary.get("n_success"),
        "n_failed_total": sweep_summary.get("n_failed_total"),
        "run_artifacts": {
            "geometry_dir": str(geometry_dir),
            "aero_dir": str(sweep_dir),
        },
    }
    generic_manifest_extra.update(_config_manifest_fields(config, copied_config_path))
    write_run_manifest(run_paths, extra=generic_manifest_extra)
    logger.info("Aero sweep completed with status=%s", sweep_status)

    return run_root, sweep_result
