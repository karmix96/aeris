"""
CLI commands for geometry generation.

Responsibilities:
    - Expose user-facing geometry subcommands
    - Validate basic CLI inputs
    - Delegate execution to geometry workflows

Notes:
    - This module should remain thin
    - No generator-specific geometry logic should live here
"""

from __future__ import annotations

from pathlib import Path

import typer

from aeris.geometry.visualization import visualize_geometry_from_config
from aeris.pipeline.geometry_run import run_geometry_generation

geometry_app = typer.Typer(help="Geometry-related commands.")


@geometry_app.callback()
def geometry_callback() -> None:
    """Geometry command group."""
    pass


@geometry_app.command("info")
def geometry_info() -> None:
    """Show the current status of geometry tooling."""
    typer.echo(
        "Geometry module is ready. "
        "Use 'aeris geometry generate --config configs/geometry/wing_bwb.yaml' "
        "or 'aeris geometry visualize --config configs/geometry/baseline_bwb.yaml'."
    )


@geometry_app.command("generate")
def geometry_generate(
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
) -> None:
    """
    Generate one deterministic geometry case from a YAML config.

    This is the production single-case geometry entry point.
    The command stays thin: actual orchestration belongs in the geometry
    pipeline, and geometry mathematics belongs in the selected generator.
    """
    exit_code = run_geometry_generation(config)
    raise typer.Exit(code=exit_code)


@geometry_app.command("visualize")
def geometry_visualize(
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
    seed: int | None = typer.Option(
        None,
        "--seed",
        help="Optional seed override for the one-case visualization sample.",
    ),
    save_plot: bool | None = typer.Option(
        None,
        "--save-plot/--no-save-plot",
        help="Override plot saving behavior from config.",
    ),
    build_aerosandbox: bool | None = typer.Option(
        None,
        "--build-aerosandbox/--no-build-aerosandbox",
        help="Override AeroSandbox build behavior from config.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Optional output directory. Defaults to data/debug/visualization_runs/<timestamp>_geometry_<name>/",
    ),
    show_plot: bool = typer.Option(
        False,
        "--show-plot/--no-show-plot",
        help="Display the saved 2D plot image if available.",
    ),
    draw_3d: bool = typer.Option(
        True,
        "--draw-3d/--no-draw-3d",
        help="Open AeroSandbox 3D viewer using airplane.draw().",
    ),
) -> None:
    """
    Generate and visualize one geometry case from config.

    This is an operator/debugging path, not the production dataset hot path.
    For large dataset generation, keep plotting disabled unless explicitly needed.
    """
    viz_result = visualize_geometry_from_config(
        config_path=config,
        seed=seed,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
        output_dir=output_dir,
        show_plot=show_plot,
        draw_3d=draw_3d,
    )
    typer.echo(f"[AERIS] Geometry visualization output: {viz_result.output_dir}")
    if viz_result.plot_path is not None:
        typer.echo(f"[AERIS] Saved plot: {viz_result.plot_path}")
    typer.echo(f"[AERIS] AeroSandbox airplane available: {viz_result.has_aerosandbox_airplane}")