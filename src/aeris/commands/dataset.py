"""
CLI commands for dataset generation and inspection.

Responsibilities:
    - Expose dataset-related user commands
    - Validate basic CLI arguments
    - Delegate sampling, generation, and inspection to dataset workflows

Notes:
    - This module should not implement sampling or geometry logic directly
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from aeris.dataset.aero_dataset_run import run_aero_dataset_generation
from aeris.dataset.dataset_run import run_dataset_generation
from aeris.dataset.inspect import inspect_dataset
from aeris.quality.pipeline_api import (
    run_geometry_dataset_qc,
    run_aero_dataset_qc,
    
)

dataset_app = typer.Typer(help="Dataset generation commands.")

@dataset_app.command("qc")
def dataset_qc(
    dataset: Path = typer.Option(..., "--dataset"),
    profile: str = typer.Option("basic", "--profile"),
):
    report = run_geometry_dataset_qc(dataset, profile=profile)

    typer.echo(f"[AERIS] Geometry QC passed: {report['passed']}")
    typer.echo(f"Errors: {len(report['errors'])}")

    if not report["passed"]:
        raise typer.Exit(code=1)

@dataset_app.command("aero-qc")
def dataset_aero_qc(
    dataset: Path = typer.Option(..., "--dataset"),
    profile: str = typer.Option("basic", "--profile"),
):
    report = run_aero_dataset_qc(dataset, profile=profile)

    typer.echo(f"[AERIS] Aero QC passed: {report['passed']}")
    typer.echo(f"Errors: {len(report['errors'])}")

    if not report["passed"]:
        raise typer.Exit(code=1)

@dataset_app.callback()
def dataset_callback() -> None:
    """Dataset command group."""
    pass


def _parse_float_list(value: str, option_name: str) -> list[float]:
    text = value.strip()
    if not text:
        return []

    values: list[float] = []
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError as exc:
            raise typer.BadParameter(
                f"Invalid float value '{token}' for {option_name}. "
                f"Use comma-separated numeric values, e.g. -5,0,5"
            ) from exc
    return values


@dataset_app.command("generate")
def dataset_generate(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the YAML geometry config file.",
    ),
    n: int = typer.Option(
        ...,
        "--n",
        min=1,
        help="Number of geometries to generate.",
    ),
    sampler: str | None = typer.Option(
        None,
        "--sampler",
        help="Dataset sampler (e.g. lhs_v1). Defaults to config or lhs_v1.",
    ),
    sampler_seed: int | None = typer.Option(
        None,
        "--sampler-seed",
        help="Seed for the selected sampler.",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Optional dataset folder name. If omitted, a deterministic name is used.",
    ),
    save_plot: bool | None = typer.Option(
        None,
        "--save-plot/--no-save-plot",
        help="Override config plotting behavior.",
    ),
    build_aerosandbox: bool | None = typer.Option(
        None,
        "--build-aerosandbox/--no-build-aerosandbox",
        help="Override config AeroSandbox behavior.",
    ),
        run_qc: bool = typer.Option(
        False,
        "--run-qc/--no-run-qc",
        help="Run QC checks after geometry dataset generation.",
    ),
    qc_profile: str = typer.Option(
        "basic",
        "--qc-profile",
        help="QC profile name.",
    ),
    fail_on_qc_error: bool = typer.Option(
        False,
        "--fail-on-qc-error/--allow-qc-errors",
        help="Exit nonzero if geometry QC fails.",
    ),
) -> None:
    """Generate a batch geometry dataset using a modular sampling strategy."""
    exit_code = run_dataset_generation(
        config_path=config,
        n_samples=n,
        sampler=sampler,
        sampler_seed=sampler_seed,
        dataset_name=name,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
        run_qc=run_qc,
        qc_profile=qc_profile,
        fail_on_qc_error=fail_on_qc_error,
    )
    raise typer.Exit(code=exit_code)


@dataset_app.command("aero-generate")
def dataset_aero_generate(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the YAML geometry config file.",
    ),
    n: int = typer.Option(
        ...,
        "--n",
        min=1,
        help="Number of geometries to generate before aerodynamic evaluation.",
    ),
    sampler: str | None = typer.Option(
        None,
        "--sampler",
        help="Dataset sampler (e.g. lhs_v1). Defaults to config or lhs_v1.",
    ),
    sampler_seed: int | None = typer.Option(
        None,
        "--sampler-seed",
        help="Seed for the selected sampler.",
    ),
    name: str = typer.Option(
        ...,
        "--name",
        help="Final aero-dataset folder name under data/datasets/.",
    ),
    save_plot: bool | None = typer.Option(
        None,
        "--save-plot/--no-save-plot",
        help="Override geometry plotting behavior during dataset generation.",
    ),
    build_aerosandbox: bool | None = typer.Option(
        True,
        "--build-aerosandbox/--no-build-aerosandbox",
        help="Override config AeroSandbox behavior for geometry generation.",
    ),
    alpha_values: str = typer.Option(
        "",
        "--alpha-values",
        help="Comma-separated alpha sweep values, e.g. -2,0,2,4",
    ),
    beta_values: str = typer.Option(
        "",
        "--beta-values",
        help="Comma-separated beta sweep values, e.g. 0,2,4",
    ),
    velocity_values: str = typer.Option(
        "",
        "--velocity-values",
        help="Comma-separated velocity sweep values, e.g. 20,28,35",
    ),
    altitude_values: str = typer.Option(
        "",
        "--altitude-values",
        help="Comma-separated altitude sweep values, e.g. 0,1500,3000",
    ),
    p_values: str = typer.Option(
        "",
        "--p-values",
        help="Comma-separated p sweep values, e.g. 0,0.05",
    ),
    q_values: str = typer.Option(
        "",
        "--q-values",
        help="Comma-separated q sweep values, e.g. 0,0.05",
    ),
    r_values: str = typer.Option(
        "",
        "--r-values",
        help="Comma-separated r sweep values, e.g. 0,0.05",
    ),
    control_input_values: str = typer.Option(
        "",
        "--control-input-values",
        help="Comma-separated control-input values, e.g. -5,0,5",
    ),
    solver: str = typer.Option(
        "aerosandbox_avl",
        "--solver",
        help="Registered aero solver ID.",
    ),
    avl_command: str = typer.Option(
        "",
        "--avl-command",
        help="Optional AVL executable path/command.",
    ),
    timeout_sec: int = typer.Option(
        180,
        "--timeout-sec",
        help="Solver timeout in seconds.",
    ),
    spanwise_resolution: int = typer.Option(
        4,
        "--spanwise-resolution",
        help="AVL spanwise panel resolution override.",
    ),
    chordwise_resolution: int = typer.Option(
        8,
        "--chordwise-resolution",
        help="AVL chordwise panel resolution override.",
    ),
    spanwise_spacing: str = typer.Option(
        "equal",
        "--spanwise-spacing",
        help="AVL spanwise spacing override.",
    ),
    chordwise_spacing: str = typer.Option(
        "cosine",
        "--chordwise-spacing",
        help="AVL chordwise spacing override.",
    ),
    save_surface_forces: bool = typer.Option(
        False,
        "--save-surface-forces",
        help="Write AVL surface force output files.",
    ),
    save_element_forces: bool = typer.Option(
        False,
        "--save-element-forces",
        help="Write AVL element force output files.",
    ),
    max_cases: int | None = typer.Option(
        None,
        "--max-cases",
        help="Optional safety cap on cases per geometry sweep.",
    ),
    keep_geometry_dataset: bool = typer.Option(
        True,
        "--keep-geometry-dataset/--delete-geometry-dataset",
        help="Keep or delete the intermediate geometry dataset after aero dataset creation.",
    ),
        run_geometry_qc: bool = typer.Option(
        False,
        "--run-geometry-qc/--no-run-geometry-qc",
        help="Run QC checks on the intermediate geometry dataset.",
    ),
    geometry_qc_profile: str = typer.Option(
        "basic",
        "--geometry-qc-profile",
        help="Geometry QC profile name.",
    ),
    fail_on_geometry_qc_error: bool = typer.Option(
        False,
        "--fail-on-geometry-qc-error/--allow-geometry-qc-errors",
        help="Exit nonzero if geometry QC fails.",
    ),
    run_aero_qc: bool = typer.Option(
        False,
        "--run-aero-qc/--no-run-aero-qc",
        help="Run QC checks on the generated aero dataset.",
    ),
    aero_qc_profile: str = typer.Option(
        "basic",
        "--aero-qc-profile",
        help="Aero QC profile name.",
    ),
    fail_on_aero_qc_error: bool = typer.Option(
        False,
        "--fail-on-aero-qc-error/--allow-aero-qc-errors",
        help="Exit nonzero if aero QC fails.",
    ),
) -> None:
    """Generate a geometry dataset and enrich it with aero/control sweeps in one command."""
    parsed_alpha_values = _parse_float_list(alpha_values, "--alpha-values")
    parsed_beta_values = _parse_float_list(beta_values, "--beta-values")
    parsed_velocity_values = _parse_float_list(velocity_values, "--velocity-values")
    parsed_altitude_values = _parse_float_list(altitude_values, "--altitude-values")
    parsed_p_values = _parse_float_list(p_values, "--p-values")
    parsed_q_values = _parse_float_list(q_values, "--q-values")
    parsed_r_values = _parse_float_list(r_values, "--r-values")
    parsed_control_input_values = _parse_float_list(
        control_input_values,
        "--control-input-values",
    )

    if not parsed_alpha_values:
        raise typer.BadParameter("--alpha-values must not be empty.")
    if not parsed_velocity_values:
        raise typer.BadParameter("--velocity-values must not be empty.")
    if not parsed_altitude_values:
        raise typer.BadParameter("--altitude-values must not be empty.")
    if not parsed_control_input_values:
        raise typer.BadParameter("--control-input-values must not be empty.")

    exit_code = run_aero_dataset_generation(
    config_path=config,
    n_samples=n,
    sampler=sampler,
    sampler_seed=sampler_seed,
    dataset_name=name,
    save_plot=save_plot,
    build_aerosandbox=build_aerosandbox,
    alpha_values=parsed_alpha_values,
    beta_values=parsed_beta_values,
    velocity_values=parsed_velocity_values,
    altitude_values=parsed_altitude_values,
    p_values=parsed_p_values,
    q_values=parsed_q_values,
    r_values=parsed_r_values,
    control_input_values=parsed_control_input_values,
    solver=solver,
    avl_command=avl_command,
    timeout_sec=timeout_sec,
    spanwise_resolution=spanwise_resolution,
    chordwise_resolution=chordwise_resolution,
    spanwise_spacing=spanwise_spacing,
    chordwise_spacing=chordwise_spacing,
    save_surface_forces=save_surface_forces,
    save_element_forces=save_element_forces,
    max_cases=max_cases,
    keep_geometry_dataset=keep_geometry_dataset,
    run_geometry_qc=run_geometry_qc,
    geometry_qc_profile=geometry_qc_profile,
    fail_on_geometry_qc_error=fail_on_geometry_qc_error,
    run_aero_qc=run_aero_qc,
    aero_qc_profile=aero_qc_profile,
    fail_on_aero_qc_error=fail_on_aero_qc_error,
    )
        
    raise typer.Exit(code=exit_code)


@dataset_app.command("inspect")
def dataset_inspect(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to a generated dataset root folder.",
    ),
) -> None:
    """Inspect a generated dataset and print QC summary as JSON."""
    summary = inspect_dataset(dataset)
    typer.echo(json.dumps(summary, indent=2))