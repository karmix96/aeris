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
        "Geometry module is ready. Use 'aeris geometry generate --config configs/geometry/wing_bwb.yaml'."
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
    """Generate geometry artifacts from config."""
    exit_code = run_geometry_generation(config)
    raise typer.Exit(code=exit_code)
