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
    """Run the minimal smoke pipeline."""
    exit_code = run_smoke_pipeline(config)
    raise typer.Exit(code=exit_code)
