import typer

from aeris.commands.geometry import geometry_app
from aeris.commands.pipeline import pipeline_app
from aeris.commands.version import register as register_version

app = typer.Typer(help="Aeris command-line interface.")


@app.callback()
def app_callback() -> None:
    """Aeris root command group."""
    pass


register_version(app)
app.add_typer(geometry_app, name="geometry")
app.add_typer(pipeline_app, name="pipeline")


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
