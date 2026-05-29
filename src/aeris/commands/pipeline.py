"""
Pipeline command registration for the AERIS CLI.

Responsibilities:
    - Expose lightweight pipeline-level workflow commands
    - Run smoke checks through pipeline helpers
    - Return pipeline exit codes cleanly to the shell

Notes:
    - This module must remain a thin CLI wrapper.
    - Real workflow logic belongs in aeris.pipeline.*.
    - Smoke workflows are sanity checks, not full production campaigns.
"""

from __future__ import annotations

from pathlib import Path

import typer

from aeris.pipeline.smoke import run_smoke_pipeline

pipeline_app = typer.Typer(help="Pipeline workflow commands.")


@pipeline_app.callback()
def pipeline_callback() -> None:
    """Pipeline command group."""
    pass


@pipeline_app.command("smoke")
def pipeline_smoke(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the YAML config file.",
    ),
) -> None:
    """
    Run the minimal smoke pipeline.

    Use this to check that the basic AERIS execution spine still works.
    It is not a full geometry/aero/dataset/ML validation campaign.
    """
    exit_code = run_smoke_pipeline(config)
    raise typer.Exit(code=exit_code)