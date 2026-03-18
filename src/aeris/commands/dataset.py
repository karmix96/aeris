from __future__ import annotations

import json
from pathlib import Path

import typer

from aeris.dataset.inspect import inspect_dataset
from aeris.dataset.dataset_run import run_dataset_generation

dataset_app = typer.Typer(help="Dataset generation commands.")


@dataset_app.callback()
def dataset_callback() -> None:
    """Dataset command group."""
    pass


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
