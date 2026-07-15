from __future__ import annotations

import logging

import typer

from aeris.commands.aero import aero_app
from aeris.commands.dataset import dataset_app
from aeris.commands.dynamics import dynamics_app
from aeris.commands.geometry import geometry_app
from aeris.commands.gui import gui_app
from aeris.commands.mesh import mesh_app
from aeris.commands.ml import ml_app
from aeris.commands.pipeline import pipeline_app
from aeris.commands.version import version_app
from aeris.commands.airfoil import airfoil_app
from aeris.commands.workflow import workflow_app
from aeris.common.paths import ensure_output_directories_writable


app = typer.Typer(
    help=(
        "AERIS command-line interface.\n\n"
        "Mental model:\n"
        "- geometry = generate or visualize one geometry\n"
        "- gui = launch local Streamlit operator cockpit\n"
        "- dataset = generate, inspect, QC, curate, and promote datasets\n"
        "- aero = run or inspect aerodynamic cases and sweeps\n"
        "- dynamics = mass / CG / trim / dynamics-foundation workflows\n"
        "- mesh = structured CFD mesh generation (surface + pyHyp volume)\n"
        "- ml = train, compare, and predict using promoted aero datasets\n"
        "- pipeline = minimal smoke workflows\n"
        "- workflow = guided workstation stage/status spine\n"
        "- version = show installed package version\n\n"
        "Use 'aeris <group> --help' for domain-specific options."
    )
)


@app.callback()
def app_callback(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable DEBUG-level logging.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Reduce logging to WARNING-level only.",
    ),
    check_writable: bool = typer.Option(
        True,
        "--check-writable/--no-check-writable",
        help="Verify AERIS output directories are writable at startup.",
    ),
) -> None:
    """AERIS — Aerospace + AI conceptual design platform."""
    if verbose and quiet:
        typer.secho(
            "[AERIS] Do not use --verbose and --quiet together.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    logging.getLogger("aeris").setLevel(level)

    if check_writable:
        try:
            ensure_output_directories_writable()
        except PermissionError as exc:
            typer.secho(
                f"[AERIS] Output directory not writable: {exc}",
                err=True,
                fg=typer.colors.RED,
            )
            typer.secho(
                "Set AERIS_DATA_ROOT to a writable location or pass "
                "--no-check-writable to skip this check.",
                err=True,
            )
            raise typer.Exit(code=1)


app.add_typer(version_app, name="version")
app.add_typer(geometry_app, name="geometry")
app.add_typer(gui_app, name="gui")
app.add_typer(dataset_app, name="dataset")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(workflow_app, name="workflow")
app.add_typer(aero_app, name="aero")
app.add_typer(dynamics_app, name="dynamics")
app.add_typer(mesh_app, name="mesh")
app.add_typer(ml_app, name="ml")
app.add_typer(airfoil_app, name="airfoil")


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()