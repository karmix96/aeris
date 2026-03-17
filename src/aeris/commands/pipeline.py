from __future__ import annotations # Ensures type hints are treated as strings to prevent circular import errors.

from pathlib import Path

import typer

from aeris.pipeline.smoke import run_smoke_pipeline # Imports the core workflow logic to keep the command layer slim.

# Creates a sub-app for grouping all workflow-related commands under 'aeris pipeline'.
pipeline_app = typer.Typer(help="Pipeline workflow commands.")


@pipeline_app.callback() # The entry point for this command group; handles shared settings or help messages.
def pipeline_callback() -> None:
    """Pipeline command group."""
    pass


@pipeline_app.command("smoke") # Defines the 'smoke' command to run quick sanity checks on the system.
def pipeline_smoke(
    config: Path = typer.Option( # Configures the --config/-c argument with strict file validation rules.
        ...,
        "--config",
        "-c",
        exists=True, # Ensures the provided file path actually exists on the disk.
        file_okay=True, # Confirms the input is a file, not a directory.
        dir_okay=False,
        readable=True, # Checks that the user has permissions to read the file.
        resolve_path=True, # Converts relative paths to absolute paths for reliability.
        help="Path to the YAML config file.",
    ),
) -> None:
    """Run the minimal smoke pipeline."""
    # Executes the high-level workflow and captures the outcome.
    exit_code = run_smoke_pipeline(config)
    # Shuts down the CLI with the specific success or failure code from the pipeline.
    raise typer.Exit(code=exit_code)

# It represents the Command Layer of your architecture. Its only job is to take the "Design Brief" (your YAML config) 
# and hand it to the "Production Workflow" (the pipeline logic) to see if the factory can run without "exploding". 
# It is a Wrapper that keeps your user interface separate from your actual math and logic.