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
from aeris.common.config import load_yaml_config
from aeris.common.paths import create_run_folder
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator


def create_aero_run_root(output_name: str, label: str, prefix: str) -> tuple[Path, Path, Path]:
    suffix = output_name.strip() or label.strip()
    run_root = create_run_folder(prefix=f"{prefix}_{suffix}").root
    geometry_dir = run_root / "geometry"
    aero_dir = run_root / "aero"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    aero_dir.mkdir(parents=True, exist_ok=True)
    return run_root, geometry_dir, aero_dir


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

    if generator_id is None or not generator_id.strip():
        raise ValueError(
            "generator_id must be provided for --run-dir and --dataset source modes."
        )

    if run_dir is not None:
        geometry_view = geometry_view_from_run_dir(
            run_dir=run_dir,
            generator_id=generator_id,
        )
        summary = {
            "source_mode": "run_dir",
            "run_dir": str(run_dir.resolve()),
        }
        return geometry_view, generator_id, summary

    geometry_view = geometry_view_from_dataset_case(
        dataset_root=dataset,
        geometry_id=geometry_id,
        generator_id=generator_id,
    )
    summary = {
        "source_mode": "dataset",
        "dataset_root": str(dataset.resolve()),
        "geometry_id": geometry_id,
    }
    return geometry_view, generator_id, summary


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

    run_root, geometry_dir, aero_dir = create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero",
    )

    geometry_view, resolved_generator_id, summary = prepare_geometry_for_aero(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=geometry_source,
        seed=seed,
        geometry_dir=geometry_dir,
        generator_id=generator_id,
        copy_config_to=run_root,
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
    result = solver_instance.run_case(aero_input=aero_input, output_dir=aero_dir)

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
    (run_root / "aero_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

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

    run_root, geometry_dir, sweep_dir = create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero_sweep",
    )

    geometry_view, resolved_generator_id, summary = prepare_geometry_for_aero(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=geometry_source,
        seed=seed,
        geometry_dir=geometry_dir,
        generator_id=generator_id,
        copy_config_to=run_root,
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
    (run_root / "aero_sweep_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    return run_root, sweep_result