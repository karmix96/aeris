from __future__ import annotations

import typer

from aeris.commands.aero import aero_app
from aeris.commands.dataset import dataset_app
from aeris.commands.dynamics import dynamics_app
from aeris.commands.geometry import geometry_app
from aeris.commands.pipeline import pipeline_app
from aeris.commands.version import version_app
from aeris.commands.ml import ml_app

app = typer.Typer(
    help=(
        "AERIS command-line interface.\n\n"
        "Mental model:\n"
        "- geometry = generate one geometry\n"
        "- dataset = generate or inspect datasets\n"
        "- aero = run or inspect aerodynamic cases and sweeps\n"
        "- pipeline = minimal smoke workflows\n"
        "- dynamics = mass / trim / dynamics workflows\n\n"
        "Use 'aeris <group> --help' for domain-specific options."
    )
)


@app.callback()
def app_callback() -> None:
    """AERIS root command group."""
    pass


app.add_typer(version_app, name="version")
app.add_typer(geometry_app, name="geometry")
app.add_typer(dataset_app, name="dataset")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(aero_app, name="aero")
app.add_typer(dynamics_app, name="dynamics")
app.add_typer(ml_app, name="ml")


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()