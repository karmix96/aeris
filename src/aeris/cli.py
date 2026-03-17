from __future__ import annotations # his line tells Python to treat all type annotations as strings at runtime. 
                                   # It prevents "name not defined" errors and can slightly improve start-up time 
                                   # for large projects.

import typer                       # Python library to build terminal tools - Python CLI (command Line Interface)

from aeris.commands.dataset import dataset_app
from aeris.commands.geometry import geometry_app
from aeris.commands.pipeline import pipeline_app
from aeris.commands.version import register as register_version

app = typer.Typer(help="Aeris command-line interface.")


@app.callback()                      # Without a callback: If you type aeris geometry, Python goes straight into the geometry code.
                                     # With a callback: Before Python enters any "room," it stops at the callback function first.


def app_callback() -> None:          # The callback function explained above - it is for global settings like --verbose or --quiet e.g.
    """Aeris root command group."""
    pass


register_version(app)               # This isn't a Typer-specific command; it's a custom function

app.add_typer(geometry_app, name="geometry") # This is Typer’s way of nesting commands.
app.add_typer(dataset_app, name="dataset")
app.add_typer(pipeline_app, name="pipeline")


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
